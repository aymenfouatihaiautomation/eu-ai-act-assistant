"""T5 — Évalue la recherche sur toutes les questions de test.

    python src/evaluate.py                  → les deux modèles
    python src/evaluate.py --model bge-m3   → un seul modèle

Pour chaque modèle, chaque langue (en, fr, ar) et chaque question avec réponse :
on cherche les K fiches les plus proches, et on regarde si une fiche attendue est dedans.
C'est le RECALL@K : la part des questions dont la bonne fiche est dans les K premières.

Les résultats détaillés sont enregistrés dans data/eval/results_<modèle>_<stratégie>.json

v2 (01/11) : deux STRATÉGIES de recherche, comparées sur les mêmes questions
  - naive   : les K fiches les plus proches, telles que ChromaDB les renvoie
  - diverse : on prend les 50 plus proches, puis on garde des fiches juridiques DIFFÉRENTES :
              une seule langue par fiche (en-art5-p1-f et fr-art5-p1-f comptent pour une),
              et au plus 2 fiches par article ou annexe.
  Pourquoi : pour "Since when do the bans on prohibited AI practices apply?", les 5 places
  étaient toutes prises par des points de l'article 5 (en ET fr), qui portent tous l'en-tête
  "Prohibited AI practices". L'article 113, qui contient la date, n'avait aucune place.
"""
import argparse
import json
import re
from pathlib import Path

from embeddings import MODELS, encode, get_collection, load_model

QUESTIONS = Path("data/eval/questions.json")
LANGS = ["en", "fr", "ar"]
STRATEGIES = ["naive", "diverse"]
POOL = 50          # nombre de fiches demandées à ChromaDB pour la stratégie "diverse"
MAX_PER_UNIT = 2   # au plus 2 fiches par article ou par annexe


# ============================================================================
# À TOI : les 3 fonctions au cœur de l'évaluation
# ============================================================================

def legal_id(chunk_id):
    """Retire la langue et le numéro de morceau d'un id de fiche.
        "en-art5-p1-f"       → "art5-p1-f"
        "fr-anxIII-4-a"      → "anxIII-4-a"
        "en-art43-p3-part2"  → "art43-p3"
    """
    without_lang = chunk_id.split("-", 1)[1]          # coupe au 1er tiret, garde la 2e partie
    return re.sub(r"-part\d+$", "", without_lang)     # retire "-part2" s'il est à la fin


def is_hit(found_ids, expected):
    """Vrai si AU MOINS UNE fiche attendue est parmi les fiches trouvées.
        found_ids : ids renvoyés par ChromaDB, ex. ["en-art26-p7", "fr-art5-p1-f", ...]
        expected  : ids attendus, sans langue, ex. ["art5-p1-f"]
    """
    found_legal = {legal_id(i) for i in found_ids}
    return any(e in found_legal for e in expected)


def recall(hits):
    """Part des réussites, en pourcentage. hits est une liste de True / False."""
    if not hits:
        return 0.0
    return 100 * sum(hits) / len(hits)


# ============================================================================
# Le reste est fourni
# ============================================================================

def unit(legal):
    """L'article ou l'annexe d'une fiche : "art5-p1-f" → "art5" ; "anxIII-4-a" → "anxIII"."""
    return legal.split("-")[0]


def diversify(ids, distances, k):
    """Parcourt les fiches de la plus proche à la plus lointaine et garde les k premières
    qui apportent quelque chose de NOUVEAU : pas une autre langue d'une fiche déjà gardée,
    et pas plus de MAX_PER_UNIT fiches du même article ou de la même annexe."""
    kept_ids, kept_dist, seen, per_unit = [], [], set(), {}
    for chunk_id, dist in zip(ids, distances):
        legal = legal_id(chunk_id)
        if legal in seen:
            continue                                   # même fiche, autre langue
        if per_unit.get(unit(legal), 0) >= MAX_PER_UNIT:
            continue                                   # déjà assez de fiches de cet article
        seen.add(legal)
        per_unit[unit(legal)] = per_unit.get(unit(legal), 0) + 1
        kept_ids.append(chunk_id)
        kept_dist.append(dist)
        if len(kept_ids) == k:
            break
    return kept_ids, kept_dist


def rank_in_pool(ids, expected):
    """Rang (parmi des fiches juridiques DIFFÉRENTES) de la 1re fiche attendue dans les 50.
    Sert au diagnostic : "raté, mais 7e" n'est pas pareil que "raté, absent des 50"."""
    seen = []
    for chunk_id in ids:
        legal = legal_id(chunk_id)
        if legal not in seen:
            seen.append(legal)
            if legal in expected:
                return len(seen)
    return None


def coverage(found_ids, expected):
    """Part des fiches attendues qui sont présentes (0.0 à 1.0).
    is_hit répond « au moins une ? » ; coverage répond « combien sur tout ce qu'on attendait ? ».
    Sert aux questions qui demandent une LISTE (ex. les 10 points de l'article 5(1)).
        coverage(["en-art5-p1-a", "fr-art5-p1-b"], ["art5-p1-a", "art5-p1-b", "art5-p1-c"]) → 0.667
    """
    if not expected:
        return 0.0
    found_legal = {legal_id(i) for i in found_ids}
    return sum(e in found_legal for e in expected) / len(expected)


def evaluate_model(name, questions, k):
    """Renvoie {"naive": [lignes], "diverse": [lignes]}."""
    print(f"\n=== {name} : chargement du modèle ===")
    model = load_model(name)
    collection = get_collection(name)
    rows = {s: [] for s in STRATEGIES}

    for lang in LANGS:
        texts = [q[f"question_{lang}"] for q in questions]
        vectors = encode(model, name, texts, kind="query")
        # On envoie toutes les questions d'une langue en UNE requête : beaucoup plus rapide.
        # On demande POOL fiches : les K premières servent à "naive", les 50 à "diverse".
        results = collection.query(query_embeddings=vectors, n_results=POOL)

        for q, pool_ids, pool_dist in zip(questions, results["ids"], results["distances"]):
            for strategy in STRATEGIES:
                if strategy == "naive":
                    ids, dist = pool_ids[:k], pool_dist[:k]
                else:
                    ids, dist = diversify(pool_ids, pool_dist, k)
                rows[strategy].append({
                    "model": name,
                    "strategy": strategy,
                    "lang": lang,
                    "id": q["id"],
                    "type": q["type"],
                    "expected": q["expected"],
                    "found": ids,
                    "top_cosine": round(1 - dist[0], 3),    # cosinus de la 1re fiche
                    "hit": is_hit(ids, q["expected"]) if q["expected"] else None,
                    "rank_in_50": rank_in_pool(pool_ids, q["expected"]) if q["expected"] else None,
                })
    return rows


def print_report(name, rows, k):
    answerable = [r for r in rows if r["hit"] is not None]

    print(f"\n--- {name} : recall@{k} par langue ---")
    for lang in LANGS:
        hits = [r["hit"] for r in answerable if r["lang"] == lang]
        print(f"  {lang} : {recall(hits):5.1f} %   ({sum(hits)}/{len(hits)})")
    all_hits = [r["hit"] for r in answerable]
    print(f"  TOTAL : {recall(all_hits):5.1f} %   ({sum(all_hits)}/{len(all_hits)})")

    print(f"\n--- {name} : recall@{k} par type ---")
    for t in sorted({r["type"] for r in answerable}):
        hits = [r["hit"] for r in answerable if r["type"] == t]
        print(f"  {t:<11} : {recall(hits):5.1f} %   ({sum(hits)}/{len(hits)})")

    print(f"\n--- {name} : questions ratées ---")
    for r in answerable:
        if not r["hit"]:
            where = f"rang {r['rank_in_50']}" if r["rank_in_50"] else "absente des 50"
            print(f"  {r['id']} [{r['lang']}] attendu {r['expected']} ({where}) ; 1er trouvé : {r['found'][0]}")

    # Pour le seuil de refus (T6) : les questions SANS réponse ont-elles un cosinus plus bas ?
    with_answer = [r["top_cosine"] for r in answerable]
    no_answer = [r["top_cosine"] for r in rows if r["hit"] is None]
    print(f"\n--- {name} : cosinus de la 1re fiche ---")
    print(f"  questions AVEC réponse : moyenne {sum(with_answer) / len(with_answer):.3f}, "
          f"min {min(with_answer):.3f}")
    print(f"  questions SANS réponse : moyenne {sum(no_answer) / len(no_answer):.3f}, "
          f"max {max(no_answer):.3f}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=None, help="bge-m3 ou e5-large ; par défaut les deux")
    parser.add_argument("-k", type=int, default=5)
    args = parser.parse_args()

    questions = json.loads(QUESTIONS.read_text(encoding="utf-8"))
    names = [args.model] if args.model else list(MODELS)

    summary = []
    for name in names:
        rows = evaluate_model(name, questions, args.k)
        for strategy in STRATEGIES:
            print_report(f"{name} / {strategy}", rows[strategy], args.k)
            out = Path(f"data/eval/results_{name}_{strategy}.json")
            out.write_text(json.dumps(rows[strategy], ensure_ascii=False, indent=2), encoding="utf-8")
            hits = [r["hit"] for r in rows[strategy] if r["hit"] is not None]
            by_lang = [recall([r["hit"] for r in rows[strategy] if r["hit"] is not None and r["lang"] == l])
                       for l in LANGS]
            summary.append((name, strategy, *by_lang, recall(hits)))

    # Le tableau final, celui du README
    print(f"\n=== RÉSUMÉ recall@{args.k} ===")
    print(f"  {'modèle':<10} {'stratégie':<9} {'en':>7} {'fr':>7} {'ar':>7} {'total':>7}")
    for name, strategy, en, fr, ar, total in summary:
        print(f"  {name:<10} {strategy:<9} {en:6.1f}% {fr:6.1f}% {ar:6.1f}% {total:6.1f}%")


if __name__ == "__main__":
    main()
