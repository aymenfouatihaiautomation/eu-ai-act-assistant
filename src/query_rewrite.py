"""T6.1 — Transformer la question AVANT la recherche, avec le LLM.

Deux transformations comparées :
  translate : traduire la question en anglais, c'est tout.
  rewrite   : traduire en anglais ET reformuler avec le vocabulaire de l'AI Act
              ("stressed employees" → "infer emotions of natural persons in the workplace").

CACHE : chaque réponse du LLM est enregistrée dans data/eval/llm_cache.json.
Relancer l'évaluation ne refait donc PAS les appels déjà faits : c'est instantané,
gratuit, et le résultat est identique d'une fois sur l'autre.
"""
import hashlib
import os
import json
from pathlib import Path

from llm import PROVIDER, PROVIDERS, chat

CACHE_FILE = Path("data/eval/llm_cache.json")

# EN LIGNE, on coupe le cache (variable REWRITE_CACHE=0 sur le serveur) :
#   - sinon le fichier garderait la question de CHAQUE visiteur (vie privée : RGPD) ;
#   - deux visiteurs en même temps écriraient le fichier ensemble → JSON abîmé.
# En local (évaluations), le cache reste actif : il évite de repayer les mêmes appels.
USE_CACHE = os.getenv("REWRITE_CACHE", "1") != "0"

PROMPTS = {
    "translate": (
        "Translate the user's question into English. "
        "Output only the translation, nothing else."
    ),
    "rewrite": (
        "You prepare questions for a search engine over the text of the EU AI Act "
        "(Regulation (EU) 2024/1689). Translate the user's question into English and rephrase it "
        "with the legal vocabulary of the AI Act, for example: provider, deployer, placing on the "
        "market, putting into service, emotion recognition, biometric categorisation, high-risk AI "
        "system, prohibited AI practices, general-purpose AI model, transparency obligations. "
        "Keep exactly the same meaning. Do NOT answer the question. Do NOT add article or annex "
        "numbers. Output only the rewritten question, in one sentence."
    ),
    # v2 (01/11) : la v1 donnait une LISTE de termes ; le LLM les ajoutait même hors sujet
    # ("biometric categorisation" dans toutes les réécritures de q02 → régression sur q06).
    "rewrite_v2": (
        "You prepare questions for a search engine over the text of the EU AI Act "
        "(Regulation (EU) 2024/1689). Translate the user's question into English and rephrase it "
        "the way the AI Act itself would describe this specific situation, using the regulation's "
        "own legal term for the practice, system or actor the user is asking about. "
        "Describe ONLY what the question is about: do not add any other practice, system, actor "
        "or obligation that the user did not mention. Keep exactly the same meaning. "
        "Do NOT answer the question. Do NOT add article or annex numbers. "
        "Output only the rewritten question, in one sentence."
    ),
}
# Pourquoi interdire les numéros d'articles : sinon le LLM utiliserait sa MÉMOIRE de la loi
# pour deviner la réponse (et il peut se tromper). On veut mesurer la recherche, pas sa mémoire.


def _load_cache():
    if CACHE_FILE.exists():
        return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    return {}


def _save_cache(cache):
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def transform(questions, mode):
    """Transforme une liste de questions ("translate" ou "rewrite"), en utilisant le cache."""
    if not USE_CACHE:
        return [chat(PROMPTS[mode], q, max_tokens=1000).strip() for q in questions]
    cache = _load_cache()
    model = PROVIDERS[PROVIDER]["model"]
    results = []
    for i, question in enumerate(questions, start=1):
        # v2 : la clé contient une EMPREINTE du prompt. Sans elle, modifier le prompt renverrait
        # les anciennes réponses du cache, et on croirait tester le nouveau prompt.
        prompt_hash = hashlib.sha1(PROMPTS[mode].encode("utf-8")).hexdigest()[:8]
        key = f"{mode}|{model}|{prompt_hash}|{question}"
        if key not in cache:
            print(f"   {mode} {i}/{len(questions)}...", end="\r")
            cache[key] = chat(PROMPTS[mode], question, max_tokens=1000).strip()
            _save_cache(cache)                 # on enregistre après CHAQUE appel : une coupure
        results.append(cache[key])             # au 70e appel ne fait pas perdre les 69 premiers
    return results
