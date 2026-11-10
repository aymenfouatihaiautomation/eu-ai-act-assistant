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

from dates import date_source_ids, is_date_question
from diversity import expand_siblings
from embeddings import encode, get_collection, load_model
from evaluate import (LANGS, POOL, QUESTIONS, coverage, diversify, group_coverage, is_hit, print_report,
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


def finalize(ids, all_ids):
    """Les sources finales : celles de diversify(), plus (si --expand) les frères d'une liste coupée."""
    return ids + expand_siblings(ids, all_ids) if all_ids is not None else ids


def list_score(found_ids, q):
    """(trouvés, total) pour une question « liste » : par domaine si "expected_groups" existe, sinon par fiche."""
    if q.get("expected_groups"):
        groups = q["expected_groups"]
        return round(group_coverage(found_ids, groups) * len(groups)), len(groups)
    return round(coverage(found_ids, q["expected"]) * len(q["expected"])), len(q["expected"])


def list_coverage(args, model, collection, strategies, names, all_ids, items=None):
    """Questions qui demandent une LISTE : on mesure combien des fiches attendues sont dans les k sources.
    items=None → data/eval/list_questions.json (comportement par défaut)."""
    if items is None:
        if not LIST_QUESTIONS.exists():
            return
        items = json.loads(LIST_QUESTIONS.read_text(encoding="utf-8"))
    if not items:
        return
    table = {s: {} for s in strategies}
    for lang in LANGS:
        _, pools = build_pools(collection, model, args.model, [q[f"question_{lang}"] for q in items], names)
        for n, q in enumerate(items):
            for strategy in strategies:
                ids, _ = diversify(*strategy_pool(strategy, pools, n), args.k)
                table[strategy][(q["id"], lang)] = list_score(finalize(ids, all_ids), q)

    extra_note = " + frères ajoutés" if all_ids is not None else ""
    print(f"\n=== COUVERTURE DES LISTES (fiches attendues présentes dans les {args.k} sources{extra_note}) ===")
    print(f"  {'stratégie':<11} {'question':<9} " + " ".join(f"{l:>6}" for l in LANGS))
    for strategy in strategies:
        for q in items:
            cells = ["{}/{}".format(*table[strategy][(q["id"], l)]) for l in LANGS]
            print(f"  {strategy:<11} {q['id']:<9} " + " ".join(f"{c:>6}" for c in cells))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="bge-m3")
    parser.add_argument("-k", type=int, default=10)
    parser.add_argument("--strategies", nargs="+", choices=ALL_STRATEGIES, default=None,
                        help="par défaut : " + " ".join(DEFAULT_STRATEGIES))
    parser.add_argument("--expand", action="store_true",
                        help="ajoute les frères d'une liste coupée par diversify() (voir diversity.py)")
    parser.add_argument("--questions", default=None,
                        help="autre fichier de questions (ex. data/eval/heldout_questions.json) ; "
                             "ses questions de type « list » remplacent list_questions.json")
    parser.add_argument("--dates", action="store_true",
                        help="question de date → ajoute les fiches des art. 111 et 113 du tableau vérifié (voir dates.py)")
    args = parser.parse_args()
    strategies = args.strategies or DEFAULT_STRATEGIES
    names = needed_texts(strategies)
    # Sans --strategies, on garde les noms de fichiers d'origine ; avec, on ajoute le modèle LLM.
    suffix = "" if args.strategies is None else "_" + PROVIDERS[PROVIDER]["model"].split("/")[-1]
    suffix += "_expand" if args.expand else ""
    suffix += "_dates" if args.dates else ""
    # --questions data/eval/heldout_questions.json → suffixe "_heldout" : les résultats de référence ne sont pas écrasés.
    questions_file = Path(args.questions) if args.questions else QUESTIONS
    if args.questions:
        suffix += "_" + questions_file.stem.replace("_questions", "")

    questions = json.loads(questions_file.read_text(encoding="utf-8"))
    model = load_model(args.model)
    collection = get_collection(args.model)
    all_ids = collection.get(include=[])["ids"] if args.expand else None   # None = pas d'ajout
    index_ids = collection.get(include=[])["ids"] if args.dates else None
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
                n_base = len(ids)
                ids = finalize(ids, all_ids)
                n_expanded = len(ids)
                query = texts[FUSION_WITH if strategy == "fusion" else strategy][n]
                # --dates : même étape que retrieve.search(), APRÈS les frères (les 10 places ne changent pas)
                if args.dates and is_date_question(query):
                    ids = ids + date_source_ids(ids, index_ids)
                row = {
                    "extra": n_expanded - n_base,
                    "model": args.model, "strategy": strategy, "lang": lang,
                    "id": q["id"], "type": q["type"], "expected": q["expected"],
                    "query": query,
                    "found": ids,
                    "top_cosine": round(1 - dist[0], 3),
                    "hit": is_hit(ids, q["expected"]) if q["expected"] else None,
                    "rank_in_50": rank_in_pool(pool_ids, q["expected"]) if q["expected"] else None,
                }
                if args.dates:   # champ ajouté seulement avec --dates : le fichier par défaut garde son format
                    row["date_extra"] = len(ids) - n_expanded
                rows[strategy].append(row)

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

    if args.expand:
        print("\n=== FICHES AJOUTÉES (frères d'une liste) ===")
        for strategy in strategies:
            extras = [r["extra"] for r in rows[strategy]]
            fired = [e for e in extras if e]
            print(f"  {strategy:<11} déclenché sur {len(fired)}/{len(extras)} recherches ; "
                  f"+{sum(fired)} fiches au total, max +{max(extras)}")
            lost = [r for r in rows[strategy] if r["extra"] and r["hit"] is False]
            print(f"  {'':<11} (questions ratées malgré l'ajout : {len(lost)})")

    if args.dates:
        print("\n=== FICHES DE DATES AJOUTÉES (tableau vérifié de dates.py) ===")
        for strategy in strategies:
            fired = [r for r in rows[strategy] if r["date_extra"]]
            print(f"  {strategy:<11} déclenché sur {len(fired)}/{len(rows[strategy])} recherches ; "
                  f"+{sum(r['date_extra'] for r in fired)} fiches au total")
            names_fired = [f"{r['id']}[{r['lang']}]" for r in fired]
            no_answer = [f"{r['id']}[{r['lang']}]" for r in fired if r["hit"] is None]
            print(f"  {'':<11} questions : {' '.join(names_fired) or 'aucune'}")
            print(f"  {'':<11} dont questions sans réponse : {' '.join(no_answer) or 'aucune'}")

    list_items = [q for q in questions if q["type"] == "list"] if args.questions else None
    list_coverage(args, model, collection, strategies, names, all_ids, list_items)


if __name__ == "__main__":
    main()
