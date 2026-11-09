"""T6.3 — Évaluer les RÉPONSES (pas seulement la recherche) sur les 78 questions.

    python src/evaluate_answers.py               → prompt v2 (par défaut)
    python src/evaluate_answers.py --prompt v1   → l'ancien prompt, pour comparer

Trois familles de mesures :
  JUSTESSE  (questions avec réponse) : la réponse cite-t-elle une fiche ATTENDUE ?
            On distingue deux causes d'échec :
              - recherche : la fiche attendue n'était même pas dans les 10 sources ;
              - lecture   : elle y était, mais le LLM ne l'a pas citée (ou a refusé).
  FIDÉLITÉ  (toutes les réponses non refusées) : balises invalides, citations fantômes,
            citations mal attribuées, phrases sans aucune source.
  REFUS     : refuse-t-il les 30 questions sans réponse ? Et SEULEMENT celles-là ?

CACHE : les réponses du LLM sont enregistrées dans data/eval/answer_cache.json.
1er lancement : ~78 appels (comptez 20 à 40 min avec Groq gratuit). Les suivants : instantanés.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path

from answer import PROMPTS, REFUSAL, build_user_message, check_citations, parse_json
from evaluate import LANGS, QUESTIONS, recall
from llm import PROVIDER, PROVIDERS, chat
from retrieve import detect_lang, search

CACHE_FILE = Path("data/eval/answer_cache.json")


def matches(legal, expected):
    """v2 : un attendu terminé par '*' accepte toute fiche qui commence ainsi.
    "anxXI*" = n'importe quel point de l'annexe XI (corrigé de q11 trop étroit)."""
    def one(e):
        if not e.endswith("*"):
            return legal == e
        base = e[:-1]
        # le tiret évite qu'"anxXI*" accepte aussi "anxXII-..." (qui commence par "anxXI")
        return legal == base or legal.startswith(base + "-")
    return any(one(e) for e in expected)
PROMPT = "v2"   # remplacé par l'option --prompt
QUESTIONS_FILE = QUESTIONS   # remplacé par l'option --questions
SUFFIX = ""                  # "_heldout" avec --questions data/eval/heldout_questions.json


def cached_chat(user_message, system):
    """Comme chat(), mais avec cache : même modèle + même prompt + même message = même réponse."""
    cache = json.loads(CACHE_FILE.read_text(encoding="utf-8")) if CACHE_FILE.exists() else {}
    model = PROVIDERS[PROVIDER]["model"]
    key = hashlib.sha1(f"{model}|{system}|{user_message}".encode("utf-8")).hexdigest()
    if key not in cache:
        cache[key] = chat(system, user_message, max_tokens=2000)
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    return cache[key]


def untagged_sentences(text):
    """Les phrases qui affirment quelque chose SANS balise [S..]."""
    sentences = [s.strip() for s in re.split(r"(?<=[.!?؟])\s+", text) if len(s.strip()) > 25]
    return [s for s in sentences if not re.search(r"\[S\d+\]", s)]


def run():
    questions = json.loads(QUESTIONS_FILE.read_text(encoding="utf-8"))
    rows = []
    total = len(questions) * len(LANGS)
    n = 0
    for lang in LANGS:
        for q in questions:
            n += 1
            question = q[f"question_{lang}"]
            print(f"   {n}/{total} {q['id']} [{lang}]...", end="\r")
            rewritten, detected, chunks = search(question)
            raw = cached_chat(build_user_message(question, chunks, detected), PROMPTS[PROMPT])
            result = parse_json(raw)
            refused = bool(result.get("refused"))
            text = REFUSAL[detected] if refused else result.get("answer", "")
            checks = check_citations(text, chunks) if not refused else \
                {"used": [], "invalid_tags": [], "phantom_refs": [], "mismatched": []}
            source_ids = [c["legal_id"] for c in chunks]
            cited = [chunks[i - 1]["legal_id"] for i in checks["used"]]
            rows.append({
                "id": q["id"], "type": q["type"], "lang": lang, "detected_lang": detected,
                "expected": q["expected"], "rewritten": rewritten, "sources": source_ids,
                "refused": refused, "answer": text, "cited": cited,
                "retrieved": any(matches(s, q["expected"]) for s in source_ids),
                "correct": any(matches(c, q["expected"]) for c in cited),
                "invalid_tags": checks["invalid_tags"], "phantom_refs": checks["phantom_refs"],
                "mismatched": checks["mismatched"],
                "untagged": [] if refused else untagged_sentences(text),
                "format_error": result.get("format_error", False),
            })
    out_file().write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    return rows


def out_file():
    model = PROVIDERS[PROVIDER]["model"].split("/")[-1]
    return Path(f"data/eval/results_answers_{model}_{PROMPT}{SUFFIX}.json")


def pct(part, whole):
    return f"{recall([True] * part + [False] * (whole - part)):5.1f} %  ({part}/{whole})"


def report(rows):
    answerable = [r for r in rows if r["expected"]]
    no_answer = [r for r in rows if not r["expected"]]
    answered = [r for r in rows if not r["refused"]]

    print("\n\n=== JUSTESSE (questions avec réponse) ===")
    for lang in LANGS + ["total"]:
        sub = answerable if lang == "total" else [r for r in answerable if r["lang"] == lang]
        print(f"  {lang:<6} bonne fiche citée : {pct(sum(r['correct'] for r in sub), len(sub))}")
    retrieval_miss = [r for r in answerable if not r["retrieved"]]
    reading_miss = [r for r in answerable if r["retrieved"] and not r["correct"]]
    print(f"\n  causes d'échec : recherche {len(retrieval_miss)}, lecture {len(reading_miss)}")
    for r in retrieval_miss:
        print(f"    [recherche] {r['id']} [{r['lang']}] attendu {r['expected']}")
    for r in reading_miss:
        why = "REFUS à tort" if r["refused"] else f"cite {r['cited'] or 'rien'}"
        print(f"    [lecture]   {r['id']} [{r['lang']}] attendu {r['expected']} ; {why}")

    print("\n=== REFUS ===")
    good_refusals = sum(r["refused"] for r in no_answer)
    false_refusals = sum(r["refused"] for r in answerable)
    print(f"  questions SANS réponse refusées    : {pct(good_refusals, len(no_answer))}")
    print(f"  questions AVEC réponse refusées    : {pct(false_refusals, len(answerable))}  (doit être bas)")
    for r in no_answer:
        if not r["refused"]:
            print(f"    a répondu au lieu de refuser : {r['id']} [{r['lang']}] → {r['answer'][:90]}...")

    print(f"\n=== FIDÉLITÉ (sur les {len(answered)} réponses non refusées) ===")
    for name, key in [("balises invalides", "invalid_tags"), ("citations fantômes", "phantom_refs"),
                      ("mal attribuées", "mismatched"), ("phrases sans source", "untagged")]:
        bad = [r for r in answered if r[key]]
        print(f"  réponses avec {name:<20}: {len(bad)}")
        for r in bad[:5]:
            print(f"      {r['id']} [{r['lang']}] {r[key] if key != 'untagged' else r[key][0][:80]}")
    print(f"  réponses sans aucune citation      : {sum(1 for r in answered if not r['cited'])}")
    print(f"  JSON invalide                      : {sum(r['format_error'] for r in rows)}")

    wrong_lang = [r for r in rows if r["detected_lang"] != r["lang"]]
    print(f"\n=== LANGUE détectée incorrectement : {len(wrong_lang)} / {len(rows)}")
    for r in wrong_lang:
        print(f"    {r['id']} [{r['lang']}] détectée comme {r['detected_lang']}")
    print(f"\nModèle : {PROVIDERS[PROVIDER]['model']} — prompt : {PROMPT}")
    print(f"Détails dans {out_file()}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt", default="v2", choices=sorted(PROMPTS))
    parser.add_argument("--questions", default=None,
                        help="autre fichier de questions (ex. data/eval/heldout_questions.json)")
    args = parser.parse_args()
    PROMPT = args.prompt
    if args.questions:   # résultats séparés (suffixe "_heldout") : la référence n'est pas écrasée
        QUESTIONS_FILE = Path(args.questions)
        SUFFIX = "_" + QUESTIONS_FILE.stem.replace("_questions", "")
    report(run())
