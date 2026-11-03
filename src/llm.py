"""Appeler un LLM, quel que soit le fournisseur. Utilisé par T6 (réécriture et réponse).

Changer de fournisseur = changer UNE ligne dans le fichier .env : LLM_PROVIDER=anthropic (ou groq).
  - "groq"      : gratuit, sans carte bancaire (gpt-oss-120b, modèle ouvert d'OpenAI).
                  Limites gratuites par minute : on attend et on réessaie automatiquement.
  - "anthropic" : payant, Claude Haiku 5.5 (~0,35 $ pour 1 000 questions). Pour la production
                  si la qualité de Groq ne suffit pas.

Les clés d'API ne sont JAMAIS écrites dans le code : elles sont lues dans le fichier .env
(qui n'est jamais envoyé sur GitHub, grâce à .gitignore).
"""
import os
import time

from dotenv import load_dotenv

load_dotenv()  # lit le fichier .env et met ses lignes dans les variables d'environnement

# v5 : le fournisseur se choisit dans le fichier .env (ligne LLM_PROVIDER=anthropic ou groq),
# PAS dans le code. Ainsi, une nouvelle version de llm.py n'écrase jamais ton réglage.
PROVIDER = (os.getenv("LLM_PROVIDER") or "anthropic").strip().lower()   # vide ou absent → anthropic

PROVIDERS = {
    "groq": {
        "model": "openai/gpt-oss-120b",   # choisi le 01/11 dans la liste renvoyée par list_models.py
        "key_env": "GROQ_API_KEY",
        "base_url": "https://api.groq.com/openai/v1",   # Groq parle le même « langage » que l'API OpenAI
    },
    "anthropic": {
        "model": "claude-haiku-5-5",
        "key_env": "ANTHROPIC_API_KEY",
    },
}


if PROVIDER not in PROVIDERS:
    raise RuntimeError(f"LLM_PROVIDER={PROVIDER} inconnu dans .env. Choix possibles : {list(PROVIDERS)}")


def get_key(provider):
    name = PROVIDERS[provider]["key_env"]
    key = os.getenv(name)
    if not key:
        raise RuntimeError(f"Clé absente : ajoute la ligne {name}=... dans le fichier .env")
    return key


class DailyQuotaError(RuntimeError):
    """Le quota JOURNALIER de l'offre gratuite est épuisé : réessayer dans 1 minute ne sert à rien."""


def is_daily_quota(error):
    text = str(error).lower()
    return "per day" in text or "tpd" in text or "rpd" in text


def is_temporary(error):
    """Vrai si l'erreur vaut la peine de réessayer : limite PAR MINUTE dépassée (429),
    serveur surchargé (5xx) ou coupure réseau (timeout, connexion)."""
    if is_daily_quota(error):
        return False
    text = f"{type(error).__name__} {error}".lower()
    return any(s in text for s in ("429", "rate", "timeout", "timed out", "connection",
                                   "500", "502", "503", "overloaded"))


def chat(system, user, provider=PROVIDER, max_tokens=1500, retries=6):
    """Envoie une consigne (system) et un message (user), renvoie la réponse en texte.
    temperature=0 (Groq) : le modèle choisit la réponse la plus probable, pour des réponses
    stables. Anthropic ne l'accepte plus : là, c'est le cache qui garantit la stabilité.
    Erreur temporaire (limite gratuite, coupure réseau) : on attend et on réessaie.
    max_tokens=1500 : gpt-oss « réfléchit » avant de répondre, et sa réflexion compte
    dans ce budget ; avec trop peu, la réponse finale peut être vide."""
    config = PROVIDERS[provider]
    for attempt in range(retries):
        try:
            if provider == "anthropic":
                import anthropic
                client = anthropic.Anthropic(api_key=get_key(provider))
                # La bibliothèque anthropic actuelle n'a plus de paramètre "temperature" :
                # la reproductibilité de nos évaluations repose sur le CACHE, pas sur le modèle.
                response = client.messages.create(
                    model=config["model"], max_tokens=max_tokens,
                    system=system, messages=[{"role": "user", "content": user}],
                    timeout=60,
                )
                # La réponse peut contenir plusieurs blocs (réflexion, texte...) : on garde le texte.
                answer = "".join(block.text for block in response.content
                                 if getattr(block, "type", "") == "text")
                if not answer.strip():
                    # v6 (03/11) : on écrit POURQUOI la réponse est vide (stop_reason) et ce
                    # qu'elle contenait (types de blocs) : sans ça, impossible de diagnostiquer.
                    #   max_tokens → budget trop petit ; refusal → le modèle refuse ; autre → à voir
                    types = [getattr(b, "type", "?") for b in response.content]
                    raise RuntimeError(f"réponse vide — stop_reason={response.stop_reason}, blocs={types}")
                return answer
            else:
                from openai import OpenAI
                client = OpenAI(api_key=get_key(provider), base_url=config["base_url"])
                extra = {}
                if "gpt-oss" in config["model"]:
                    # modèle qui raisonne : effort de réflexion FAIBLE, notre tâche est de lire
                    # et citer, pas de résoudre un problème ; ça économise tokens et temps
                    extra["reasoning_effort"] = "low"
                response = client.chat.completions.create(
                    model=config["model"], max_tokens=max_tokens, temperature=0,
                    messages=[{"role": "system", "content": system},
                              {"role": "user", "content": user}],
                    timeout=60,
                    **extra,
                )
                answer = response.choices[0].message.content or ""
                if not answer.strip():
                    raise RuntimeError("réponse vide (budget max_tokens épuisé par la réflexion ?)")
                return answer
        except Exception as error:
            if is_daily_quota(error):
                raise DailyQuotaError(
                    f"Quota journalier épuisé chez {provider} ({config['model']}). "
                    "Les réponses déjà obtenues sont dans le cache : relance plus tard, "
                    "ou passe PROVIDER à \"anthropic\".\nDétail : " + str(error)[:300]
                ) from None
            if is_temporary(error) and attempt < retries - 1:
                wait = 10 * (attempt + 1)
                print(f"   ({type(error).__name__} : on attend {wait} s et on réessaie...)")
                time.sleep(wait)
                continue
            raise
