"""T6.2 — Répondre à une question sur l'AI Act, avec des citations VÉRIFIÉES.

    python src/answer.py "Can we use AI to detect if our employees are stressed?"

Étapes :
  1. retrieve.search()  : réécriture + recherche → 10 fiches numérotées [S1]...[S10]
  2. le LLM répond SEULEMENT à partir de ces fiches, et met [S3] après chaque affirmation
  3. vérification AUTOMATIQUE, sans LLM :
       - chaque balise [S..] renvoie-t-elle à une fiche vraiment fournie ?
       - chaque article ou annexe NOMMÉ dans la réponse apparaît-il dans les fiches ?
         Sinon, c'est une citation « fantôme » : le LLM l'a tirée de sa mémoire.
       - dans chaque phrase, l'article nommé est-il dans une des fiches de SES balises ?
         Sinon, c'est une citation « mal attribuée » : bon article, mauvaise source.
"""
import json
import re
import sys

from llm import chat
from retrieve import search

# v1 : le prompt de la 1re évaluation (81 %). Gardé pour comparer les deux sur le MÊME modèle.
SYSTEM_V1 = """You are a compliance assistant for the EU Artificial Intelligence Act \
(Regulation (EU) 2024/1689, consolidated version of 27 July 2026).

Answer ONLY from the numbered sources given by the user. Rules:
1. Answer in the language given on the "Answer language" line.
2. After each statement of a rule, add the tags of the sources it relies on, like [S2] or [S2][S5].
3. When you name a provision, write its label exactly as given in the source list \
(for example "Article 5(1)(f)" or "Annex III, point 4(a)").
4. If the sources do not contain the answer, do NOT use your own knowledge: set "refused" to true \
and leave "answer" empty.
5. Be concise: at most 6 sentences. Do not give legal advice beyond what the sources say.

Return ONLY a JSON object, with no text before or after it:
{"refused": true or false, "answer": "your answer with [S..] tags"}"""

# v2 (02/11) : chaque phrase balisée ; refuser si les sources ne traitent qu'un sujet voisin.
SYSTEM = """You are a compliance assistant for the EU Artificial Intelligence Act \
(Regulation (EU) 2024/1689, consolidated version of 27 July 2026).

Answer ONLY from the numbered sources given by the user. Rules:
1. Answer in the language given on the "Answer language" line.
2. EVERY sentence must end with the tags of the sources it relies on, like [S2] or [S2][S5],
   including the first sentence that states your conclusion.
3. When you name a provision, write its label exactly as given in the source list \
(for example "Article 5(1)(f)" or "Annex III, point 4(a)").
4. If the sources do not contain the answer, do NOT use your own knowledge: set "refused" to true \
and leave "answer" empty. Also refuse when the sources only deal with a neighbouring subject and not \
the exact thing asked: never apply a rule written for one kind of data, system or actor to another one.
5. Be concise: at most 6 sentences. Do not give legal advice beyond what the sources say.

Return ONLY a JSON object, with no text before or after it:
{"refused": true or false, "answer": "your answer with [S..] tags"}"""
# v3 (02/11) : la v2 SANS la règle du « sujet voisin ». Mesuré sur Haiku :
#   - « chaque phrase balisée » (v2)  : phrases sans source 16 → 0        → on GARDE
#   - « refuser si sujet voisin » (v2) : refus à tort 1 → 3, aucun gain   → on RETIRE
NEIGHBOUR_RULE = (
    " Also refuse when the sources only deal with a neighbouring subject and not "
    "the exact thing asked: never apply a rule written for one kind of data, system or actor to another one."
)
# Garde-fou : si quelqu'un modifie SYSTEM, on le saura tout de suite au lieu
# d'avoir une v3 identique à la v2 sans s'en rendre compte.
assert NEIGHBOUR_RULE in SYSTEM, "règle du « sujet voisin » introuvable dans SYSTEM"
SYSTEM_V3 = SYSTEM.replace(NEIGHBOUR_RULE, "")

PROMPTS = {"v1": SYSTEM_V1, "v2": SYSTEM, "v3": SYSTEM_V3}

DISCLAIMER = {
    "en": "Information based on the consolidated text of 27/07/2026, not legal advice.",
    "fr": "Information basée sur la version consolidée du 27/07/2026, pas un conseil juridique.",
    "ar": "معلومات مبنية على النص الموحد بتاريخ 27/07/2026، وليست استشارة قانونية.",
}

# "Article 5", "article 26", "المادة 5" ; "Annex III", "Annexe III"
ARTICLE_REF = re.compile(r"(?:[Aa]rticle|المادة)\s+(\d+[a-z]?)")
ANNEX_REF = re.compile(r"[Aa]nnexe?\s+([IVXL]+)\b")


LANG_NAMES = {"en": "English", "fr": "French", "ar": "Arabic"}

# v2 : en cas de refus, c'est le CODE qui écrit le message, dans la langue détectée.
# (Lors des premiers tests, le LLM refusait en français à des questions posées en anglais.)
REFUSAL = {
    "en": "The text of the AI Act provided does not answer this question.",
    "fr": "Le texte de l'AI Act fourni ne répond pas à cette question.",
    "ar": "نص قانون الذكاء الاصطناعي المتوفر لا يجيب عن هذا السؤال.",
}


def build_user_message(question, chunks, lang):
    # v2 : la langue de réponse est donnée EXPLICITEMENT, au lieu de laisser le LLM la deviner
    lines = [f"Answer language: {LANG_NAMES[lang]}", f"Question: {question}", "", "Sources:"]
    for n, c in enumerate(chunks, start=1):
        lines.append(f"[S{n}] {c['label']} — {c['text']}")
    return "\n".join(lines)


def parse_json(text):
    """Le LLM peut entourer son JSON de ```json ... ``` : on extrait le premier {...}."""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return {"refused": False, "answer": text.strip(), "format_error": True}
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return {"refused": False, "answer": text.strip(), "format_error": True}


def check_citations(answer_text, chunks):
    """Vérification automatique des citations. Ne fait PAS appel au LLM."""
    tags = [int(n) for n in re.findall(r"\[S(\d+)\]", answer_text)]
    invalid_tags = sorted({t for t in tags if not 1 <= t <= len(chunks)})
    used = sorted({t for t in tags if 1 <= t <= len(chunks)})

    # Tout ce que les fiches fournies permettent de citer : leurs propres numéros
    # + les articles et annexes MENTIONNÉS dans leur texte (ex. une fiche qui renvoie à l'article 6).
    allowed_articles, allowed_annexes = set(), set()
    for c in chunks:
        if c["meta"].get("article"):
            allowed_articles.add(c["meta"]["article"])
        if c["meta"].get("annex"):
            allowed_annexes.add(c["meta"]["annex"])
        allowed_articles |= set(ARTICLE_REF.findall(c["text"]))
        allowed_annexes |= set(ANNEX_REF.findall(c["text"]))

    phantom = sorted({f"Article {a}" for a in ARTICLE_REF.findall(answer_text) if a not in allowed_articles} |
                     {f"Annex {a}" for a in ANNEX_REF.findall(answer_text) if a not in allowed_annexes})

    # Phrase par phrase : l'article nommé doit se trouver dans une des fiches BALISÉES de la phrase.
    mismatched = []
    for sentence in re.split(r"(?<=[.!?؟])\s+", answer_text):
        sentence_tags = [int(n) for n in re.findall(r"\[S(\d+)\]", sentence) if 1 <= int(n) <= len(chunks)]
        if not sentence_tags:
            continue
        tagged = [chunks[t - 1] for t in sentence_tags]
        ok_articles = {c["meta"].get("article") for c in tagged} | {a for c in tagged for a in ARTICLE_REF.findall(c["text"])}
        ok_annexes = {c["meta"].get("annex") for c in tagged} | {a for c in tagged for a in ANNEX_REF.findall(c["text"])}
        for a in ARTICLE_REF.findall(sentence):
            if a not in ok_articles and a in allowed_articles:      # réel, mais pas dans CES fiches
                mismatched.append(f"Article {a} → [S{'][S'.join(map(str, sentence_tags))}]")
        for a in ANNEX_REF.findall(sentence):
            if a not in ok_annexes and a in allowed_annexes:
                mismatched.append(f"Annex {a} → [S{'][S'.join(map(str, sentence_tags))}]")

    return {"used": used, "invalid_tags": invalid_tags, "phantom_refs": phantom,
            "mismatched": sorted(set(mismatched))}


# Message montré à l'utilisateur si le LLM renvoie deux fois un JSON cassé :
# mieux vaut avouer une erreur que d'afficher du JSON brut ou une réponse non vérifiée.
FORMAT_ERROR = {
    "en": "Technical error: the answer could not be generated. Please try again.",
    "fr": "Erreur technique : la réponse n'a pas pu être générée. Merci de réessayer.",
    "ar": "خطأ تقني: تعذّر إنشاء الإجابة. يرجى المحاولة مرة أخرى.",
}


def ask_llm(system, user_message, tries=2):
    """Appelle le LLM ; si le JSON est invalide, on redemande UNE fois.
    (02/11 : 1 JSON invalide sur 78 en évaluation → en production, ce serait
    une réponse cassée affichée au client.)"""
    for _ in range(tries):
        result = parse_json(chat(system, user_message, max_tokens=4000))
        if not result.get("format_error"):
            break
    return result


# v3 = prompt par défaut depuis le 02/11 (Haiku : 91,7 % justesse, 100 % refus justes,
# 1/48 refus à tort, 0 mal attribuée, 3 phrases sans source).
def answer(question, prompt="v3"):
    rewritten, lang, chunks = search(question)
    result = ask_llm(PROMPTS[prompt], build_user_message(question, chunks, lang))
    refused = bool(result.get("refused"))
    if result.get("format_error"):
        text = FORMAT_ERROR[lang]
    elif refused:
        text = REFUSAL[lang]
    else:
        text = result.get("answer", "")
    checks = check_citations(text, chunks)
    return {
        "question": question, "lang": lang, "rewritten": rewritten,
        "refused": refused, "answer": text,
        "format_error": result.get("format_error", False),
        # "text" = le texte EXACT de la loi : l'interface l'affiche pour le bouton « Vérifier ».
        "sources": [{"tag": f"S{n}", "id": c["id"], "label": c["label"], "text": c["text"]}
                    for n, c in enumerate(chunks, 1)],
        "cited": [chunks[n - 1]["legal_id"] for n in checks["used"]],
        **checks,
        "disclaimer": DISCLAIMER[lang],
    }


def show(r):
    print(f"\nQuestion  : {r['question']}")
    print(f"Réécrite  : {r['rewritten']}")
    print("\nSources fournies au LLM :")
    for s in r["sources"]:
        print(f"  [{s['tag']}] {s['label']:<24} ({s['id']})")
    print(f"\n{'REFUS' if r['refused'] else 'RÉPONSE'} :\n{r['answer']}\n")
    print(f"  ⓘ {r['disclaimer']}")
    print("\nVérification automatique :")
    print(f"  fiches citées      : {r['cited'] or 'aucune'}")
    print(f"  balises invalides  : {r['invalid_tags'] or 'aucune ✅'}")
    print(f"  citations fantômes : {r['phantom_refs'] or 'aucune ✅'}")
    print(f"  mal attribuées     : {r['mismatched'] or 'aucune ✅'}")
    if r["format_error"]:
        print("  ⚠ le LLM n'a pas renvoyé de JSON valide")
    if not r["refused"] and not r["cited"]:
        print("  ⚠ réponse SANS aucune citation")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print('Usage : python src/answer.py "ta question"')
    else:
        show(answer(" ".join(sys.argv[1:])))
