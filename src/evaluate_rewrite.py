"""T6.1 — La réécriture de la question améliore-t-elle la recherche ?

    python src/evaluate_rewrite.py               → bge-m3, k = 10
    python src/evaluate_rewrite.py -k 5

Compare 5 stratégies sur les MÊMES questions (toutes avec la recherche « diverse ») :
  original  : la question telle quelle (notre référence de T5)
  translate : traduite en anglais par le LLM
  rewrite   : traduite ET reformulée avec le vocabulaire de l'AI Act
  fusion    : on cherche avec l'original ET la version réécrite, puis on fusionne

Réutilise les fonctions de evaluate.py (les tiennes : legal_id, is_hit, recall).
Le 1er lancement fait ~150 appels au LLM (environ 10 à 15 min avec Groq gratuit) ;
les suivants sont instantanés grâce au cache.

v2 (01/11) : ajoute rewrite_v2 (prompt sans liste de vocabulaire) ; la fusion utilise rewrite_v2.
"""
import argparse
import json
from pathlib import Path

from embeddings import encode, get_collection, load_model
from evaluate import LANGS, POOL, QUESTIONS, diversify, is_hit, print_report, rank_in_pool, recall
from query_rewrite import transform

STRATEGIES = ["original", "translate", "rewrite", "rewrite_v2", "fusion"]
FUSION_WITH = "rewrite_v2"   # la fusion combine l'original avec cette réécriture


def fuse(pool_a, pool_b):
    """Fusionne deux listes de résultats (ids, distances) : pour chaque fiche on garde
    sa MEILLEURE distance, puis on retrie. Une fiche trouvée par l'une OU l'autre version
    de la question a sa chance."""
    best = {}
    for ids, distances in (pool_a, pool_b):
        for chunk_id, dist in zip(ids, distances):
            best[chunk_id] = min(dist, best.get(chunk_id, 2.0))
    ranked = sorted(best.items(), key=lambda item: item[1])
    return [i for i, _ in ranked], [d for _, d in ranked]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="bge-m3")
    parser.add_argument("-k", type=int, default=10)
    args = parser.parse_args()

    questions = json.loads(QUESTIONS.read_text(encoding="utf-8"))
    model = load_model(args.model)
    collection = get_collection(args.model)
    rows = {s: [] for s in STRATEGIES}
    examples = []

    for lang in LANGS:
        originals = [q[f"question_{lang}"] for q in questions]
        print(f"\n[{lang}] transformation des {len(originals)} questions par le LLM")
        texts = {
            "original": originals,
            "translate": transform(originals, "translate"),
            "rewrite": transform(originals, "rewrite"),
            "rewrite_v2": transform(originals, "rewrite_v2"),
        }
        pools = {}
        for name, qs in texts.items():
            res = collection.query(query_embeddings=encode(model, args.model, qs, kind="query"),
                                   n_results=POOL)
            pools[name] = list(zip(res["ids"], res["distances"]))

        for n, q in enumerate(questions):
            if q["id"] in ("q02", "q06"):
                examples.append((q["id"], lang, texts["original"][n], texts["rewrite"][n],
                                 texts["rewrite_v2"][n]))
            for strategy in STRATEGIES:
                if strategy == "fusion":
                    pool_ids, pool_dist = fuse(pools["original"][n], pools[FUSION_WITH][n])
                else:
                    pool_ids, pool_dist = pools[strategy][n]
                ids, dist = diversify(pool_ids, pool_dist, args.k)
                rows[strategy].append({
                    "model": args.model, "strategy": strategy, "lang": lang,
                    "id": q["id"], "type": q["type"], "expected": q["expected"],
                    "query": texts[FUSION_WITH if strategy == "fusion" else strategy][n],
                    "found": ids,
                    "top_cosine": round(1 - dist[0], 3),
                    "hit": is_hit(ids, q["expected"]) if q["expected"] else None,
                    "rank_in_50": rank_in_pool(pool_ids, q["expected"]) if q["expected"] else None,
                })

    print("\n=== Exemples : q02 (employés stressés) et q06 (base de visages) ===")
    for qid, lang, original, v1, v2 in examples:
        print(f"  {qid} [{lang}] {original}\n       v1 → {v1}\n       v2 → {v2}")

    summary = []
    for strategy in STRATEGIES:
        print_report(f"{args.model} / {strategy}", rows[strategy], args.k)
        Path(f"data/eval/results_{args.model}_{strategy}_rw.json").write_text(
            json.dumps(rows[strategy], ensure_ascii=False, indent=2), encoding="utf-8")
        answered = [r for r in rows[strategy] if r["hit"] is not None]
        by_lang = [recall([r["hit"] for r in answered if r["lang"] == l]) for l in LANGS]
        no_answer = [r["top_cosine"] for r in rows[strategy] if r["hit"] is None]
        with_answer = [r["top_cosine"] for r in answered]
        summary.append((strategy, *by_lang, recall([r["hit"] for r in answered]),
                        sum(with_answer) / len(with_answer), sum(no_answer) / len(no_answer)))

    print(f"\n=== RÉSUMÉ recall@{args.k} ({args.model}, recherche diverse) ===")
    print(f"  {'stratégie':<10} {'en':>7} {'fr':>7} {'ar':>7} {'total':>7}   cos. avec / sans réponse")
    for strategy, en, fr, ar, total, cos_yes, cos_no in summary:
        print(f"  {strategy:<10} {en:6.1f}% {fr:6.1f}% {ar:6.1f}% {total:6.1f}%   {cos_yes:.3f} / {cos_no:.3f}")


if __name__ == "__main__":
    main()
