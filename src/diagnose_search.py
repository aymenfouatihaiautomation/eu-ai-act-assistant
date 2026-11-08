"""Diagnostic de la recherche — NE MODIFIE RIEN, il regarde seulement.

Pour chaque question, il affiche les 50 fiches trouvées par BGE-M3 (le « pool »), dans
l'ordre, et pour chacune ce que la règle de diversité en a fait :
    GARDÉE   → elle fait partie des 10 sources envoyées au LLM
    coupée   → refusée parce que son article a déjà 2 fiches (MAX_PER_UNIT)
    doublon  → la même fiche dans l'autre langue
    (rien)   → arrivée trop loin : les 10 places étaient déjà prises
La fiche ATTENDUE est marquée ★.

Lancement, depuis la racine du projet :
    python src/diagnose_search.py
"""
import sys

sys.path.insert(0, "src")

from embeddings import encode
from evaluate import MAX_PER_UNIT, POOL, legal_id, unit
from query_rewrite import transform
from retrieve import K, MODEL_NAME, _load

CASES = [
    ("Which AI practices are prohibited under the AI Act?", "art5-p1-"),
    ("Quelles pratiques d'IA sont interdites par l'AI Act ?", "art5-p1-"),
    ("Nous utilisons un logiciel d'IA pour trier les CV des candidats. "
     "Quelles sont nos obligations en tant qu'entreprise utilisatrice ?", "anxIII-4-a"),
]


def explain(ids, distances):
    """Rejoue diversify() pas à pas, en notant le sort de chaque fiche."""
    seen, per_unit, kept, rows = set(), {}, 0, []
    for chunk_id, dist in zip(ids, distances):
        legal = legal_id(chunk_id)
        if legal in seen:
            fate = "doublon"
        elif kept >= K:
            fate = ""
        elif per_unit.get(unit(legal), 0) >= MAX_PER_UNIT:
            fate = "coupée"
        else:
            fate = "GARDÉE"
            seen.add(legal)
            per_unit[unit(legal)] = per_unit.get(unit(legal), 0) + 1
            kept += 1
        rows.append((chunk_id, legal, dist, fate))
    return rows


def main():
    model, collection = _load()
    for question, expected in CASES:
        rewritten = transform([question], "rewrite_v2")[0]
        res = collection.query(query_embeddings=encode(model, MODEL_NAME, [rewritten], kind="query"),
                               n_results=POOL)
        rows = explain(res["ids"][0], res["distances"][0])

        print("=" * 90)
        print(f"QUESTION   : {question}")
        print(f"RÉÉCRITE   : {rewritten}")
        print(f"ATTENDUE   : fiches commençant par « {expected} »")
        print("-" * 90)
        for rank, (chunk_id, legal, dist, fate) in enumerate(rows, 1):
            star = "★" if legal.startswith(expected) else " "
            print(f"{rank:>3} {star} {chunk_id:<28} distance {dist:.3f}  {fate}")

        hits = [r for r in rows if r[1].startswith(expected)]
        distinct = {r[1] for r in hits}
        kept = {r[1] for r in hits if r[3] == "GARDÉE"}
        cut = {r[1] for r in hits if r[3] == "coupée"}
        print("-" * 90)
        print(f"BILAN : {len(distinct)} fiche(s) attendue(s) dans les {POOL} | "
              f"{len(kept)} gardée(s) | {len(cut)} coupée(s) par la règle des {MAX_PER_UNIT}")
    print("=" * 90)


if __name__ == "__main__":
    main()
