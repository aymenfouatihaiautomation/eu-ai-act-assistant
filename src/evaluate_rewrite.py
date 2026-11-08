"""T6.1 — La réécriture de la question améliore-t-elle la recherche ?

    python src/evaluate_rewrite.py                          → bge-m3, k = 10, les 5 stratégies
    python src/evaluate_rewrite.py -k 5
    python src/evaluate_rewrite.py --strategies rewrite_v2  → seulement celles-ci (moins d'appels LLM)

Compare 5 stratégies sur les MÊMES questions (toutes avec la recherche « diverse ») :
  original  : la question telle quelle (notre référence de T5)
  translate : traduite en anglais par le LLM
  rewrite   : traduite ET reformulée avec le vocabulaire de l'AI Act
  fusion    : on cherche avec l'original ET la version réécrite, puis on fusionne

Réutilise les fonctions de evaluate.py (les tiennes : legal_id, is_hit, recall).
Le 1er lancement fait ~150 appels au LLM (environ 10 à 15 min avec Groq gratuit) ;
les suivants sont instantanés grâce au cache.

v2 (01/11) : ajoute rewrite_v2 (prompt sans liste de vocabulaire) ; la fusion utilise rewrite_v2.
v3 (08/11) : --strategies (on ne paie que les appels LLM des stratégies demandées) et un tableau
             « couverture des listes » (data/eval/list_questions.json) : combien des 10 points de
             l'article 5(1) arrivent dans les 10 sources ? Le recall seul ne peut pas le voir.
             Avec --strategies, les résultats vont dans des fichiers suffixés par le modèle LLM :
             les anciens results_*_rw.json ne sont pas écrasés.
"""
import argparse
import json
from pathlib import Path

from embeddings import encode, get_collection, load_model
from evaluate import (LANGS, POOL, QUESTIONS, coverage, diversify, is_hit, print_report,
                      rank_in_pool, recall)
from llm import PROVIDER, PROVIDERS
from query_rewrite import PROMPTS, transform

DEFAULT_STRATEGIES = ["original", "translate", "rewrite", "rewrite_v2", "fusion"]
ALL_STRATEGIES = ["original"] + list(PROMPTS) + ["fusion"]   # tout prompt ajouté à PROMPTS est testable
FUSION_WITH = "rewrite_v2"   # la fusion combine l'original avec cette réécriture
LIST_QUESTIONS = Path("data/eval/list_questions.json")


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


def needed_texts(strategies):
    """Quelles versions de la question faut-il fabriquer ? (chaque version = des appels LLM)"""
    names = set()
    for strategy in strategies:
        names |= {"original", FUSION_WITH} if strategy == "fusion" else {strategy}
    return [n for n in ALL_STRATEGIES if n in names]


def build_pools(collection, model, model_name, originals, names):
    """Pour chaque version de la question : le texte, puis les 50 fiches les plus proches."""
    texts = {"original": originals}
    for name in names:
        if name != "original":
            texts[name] = transform(originals, name)
    pools = {}
    for name, qs in texts.items():
        res = collection.query(query_embeddings=encode(model, model_name, qs, kind="query"),
                               n_results=POOL)
        pools[name] = list(zip(res["ids"], res["distances"]))
    return texts, pools


def strategy_pool(strategy, pools, n):
    if strategy == "fusion":
        return fuse(pools["original"][n], pools[FUSION_WITH][n])
    return pools[strategy][n]


def list_coverage(args, model, collection, strategies, names):
    """Questions qui demandent une LISTE : on mesure combien des fiches attendues sont dans les k sources."""
    if not LIST_QUESTIONS.exists():
        return
    items = json.loads(LIST_QUESTIONS.read_text(encoding="utf-8"))
    table = {s: {} for s in strategies}
    for lang in LANGS:
        _, pools = build_pools(collection, model, args.model, [q[f"question_{lang}"] for q in items], names)
        for n, q in enumerate(items):
            for strategy in strategies:
                ids, _ = diversify(*strategy_pool(strategy, pools, n), args.k)
                table[strategy][(q["id"], lang)] = coverage(ids, q["expected"])

    print(f"\n=== COUVERTURE DES LISTES (fiches attendues présentes dans les {args.k} sources) ===")
    print(f"  {'stratégie':<11} {'question':<9} " + " ".join(f"{l:>6}" for l in LANGS))
    for strategy in strategies:
        for q in items:
            cells = [f"{round(table[strategy][(q['id'], l)] * len(q['expected']))}/{len(q['expected'])}"
                     for l in LANGS]
            print(f"  {strategy:<11} {q['id']:<9} " + " ".join(f"{c:>6}" for c in cells))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="bge-m3")
    parser.add_argument("-k", type=int, default=10)
    parser.add_argument("--strategies", nargs="+", choices=ALL_STRATEGIES, default=None,
                        help="par défaut : " + " ".join(DEFAULT_STRATEGIES))
    args = parser.parse_args()
    strategies = args.strategies or DEFAULT_STRATEGIES
    names = needed_texts(strategies)
    # Sans --strategies, on garde les noms de fichiers d'origine ; avec, on ajoute le modèle LLM.
    suffix = "" if args.strategies is None else "_" + PROVIDERS[PROVIDER]["model"].split("/")[-1]

    questions = json.loads(QUESTIONS.read_text(encoding="utf-8"))
    model = load_model(args.model)
    collection = get_collection(args.model)
    rows = {s: [] for s in strategies}
    examples = []

    for lang in LANGS:
        originals = [q[f"question_{lang}"] for q in questions]
        print(f"\n[{lang}] transformation des {len(originals)} questions par le LLM")
        texts, pools = build_pools(collection, model, args.model, originals, names)

        for n, q in enumerate(questions):
            if q["id"] in ("q02", "q06") and "rewrite" in texts and "rewrite_v2" in texts:
                examples.append((q["id"], lang, texts["original"][n], texts["rewrite"][n],
                                 texts["rewrite_v2"][n]))
            for strategy in strategies:
                pool_ids, pool_dist = strategy_pool(strategy, pools, n)
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

    if examples:
        print("\n=== Exemples : q02 (employés stressés) et q06 (base de visages) ===")
        for qid, lang, original, v1, v2 in examples:
            print(f"  {qid} [{lang}] {original}\n       v1 → {v1}\n       v2 → {v2}")

    summary = []
    for strategy in strategies:
        print_report(f"{args.model} / {strategy}", rows[strategy], args.k)
        Path(f"data/eval/results_{args.model}_{strategy}_rw{suffix}.json").write_text(
            json.dumps(rows[strategy], ensure_ascii=False, indent=2), encoding="utf-8")
        answered = [r for r in rows[strategy] if r["hit"] is not None]
        by_lang = [recall([r["hit"] for r in answered if r["lang"] == l]) for l in LANGS]
        no_answer = [r["top_cosine"] for r in rows[strategy] if r["hit"] is None]
        with_answer = [r["top_cosine"] for r in answered]
        summary.append((strategy, *by_lang, recall([r["hit"] for r in answered]),
                        sum(r["hit"] for r in answered),
                        sum(with_answer) / len(with_answer), sum(no_answer) / len(no_answer)))

    print(f"\n=== RÉSUMÉ recall@{args.k} ({args.model}, recherche diverse, LLM : {PROVIDERS[PROVIDER]['model']}) ===")
    print(f"  {'stratégie':<10} {'en':>7} {'fr':>7} {'ar':>7} {'total':>7}  {'':>7}  cos. avec / sans réponse")
    for strategy, en, fr, ar, total, n_hits, cos_yes, cos_no in summary:
        n_answered = len([r for r in rows[strategy] if r["hit"] is not None])
        print(f"  {strategy:<10} {en:6.1f}% {fr:6.1f}% {ar:6.1f}% {total:6.1f}% ({n_hits}/{n_answered})  "
              f"{cos_yes:.3f} / {cos_no:.3f}")

    list_coverage(args, model, collection, strategies, names)


if __name__ == "__main__":
    main()
