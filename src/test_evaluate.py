"""Vérifie TES 3 fonctions de evaluate.py, sans modèle ni index (2 secondes).

    python src/test_evaluate.py

Chaque ligne affiche ✅ ou ❌. Quand tout est ✅, lance la vraie évaluation.
"""
from evaluate import coverage, group_coverage, is_hit, legal_id, recall

tests = [
    ("legal_id : langue retirée",          lambda: legal_id("en-art5-p1-f") == "art5-p1-f"),
    ("legal_id : annexe, en français",     lambda: legal_id("fr-anxIII-4-a") == "anxIII-4-a"),
    ("legal_id : morceau -part2 retiré",   lambda: legal_id("en-art43-p3-part2") == "art43-p3"),
    ("legal_id : article 3 inchangé",      lambda: legal_id("en-art3") == "art3"),
    ("is_hit : trouvé dans une autre langue", lambda: is_hit(["en-art26-p7", "fr-art5-p1-f"], ["art5-p1-f"]) is True),
    ("is_hit : pas trouvé",                lambda: is_hit(["en-art26-p7", "en-art50-p3"], ["art5-p1-f"]) is False),
    ("is_hit : 1 attendu sur 2 suffit",    lambda: is_hit(["en-art3-4"], ["art3-3", "art3-4"]) is True),
    ("is_hit : morceau d'une fiche",       lambda: is_hit(["en-art43-p3-part1"], ["art43-p3"]) is True),
    ("recall : 3 sur 4",                   lambda: recall([True, False, True, True]) == 75.0),
    ("recall : liste vide",                lambda: recall([]) == 0.0),
    ("recall : tout faux",                 lambda: recall([False, False]) == 0.0),
    ("coverage : 2 attendus sur 3",        lambda: abs(coverage(["en-art5-p1-a", "fr-art5-p1-b"], ["art5-p1-a", "art5-p1-b", "art5-p1-c"]) - 2 / 3) < 1e-9),
    ("coverage : une fiche en 2 langues compte 1 fois", lambda: coverage(["en-art5-p1-a", "fr-art5-p1-a"], ["art5-p1-a", "art5-p1-b"]) == 0.5),
    ("coverage : rien attendu",            lambda: coverage(["en-art5-p1-a"], []) == 0.0),
    ("group_coverage : 2 domaines sur 3 (point et domaine sans point)",
     lambda: abs(group_coverage(["en-anxIII-4-a", "fr-anxIII-2"], ["anxIII-2", "anxIII-4", "anxIII-5"]) - 2 / 3) < 1e-9),
    ("group_coverage : 2 points du même domaine comptent 1 fois",
     lambda: group_coverage(["en-anxIII-6-d", "en-anxIII-6-e"], ["anxIII-6", "anxIII-7"]) == 0.5),
    ("group_coverage : « anxIII-1 » n'attrape pas « anxIII-10 »",
     lambda: group_coverage(["en-anxIII-10-a"], ["anxIII-1"]) == 0.0),
    ("group_coverage : aucun groupe",      lambda: group_coverage(["en-anxIII-1-a"], []) == 0.0),
]

passed = 0
for name, test in tests:
    try:
        ok = test()
    except NotImplementedError:
        ok, name = False, name + "  (fonction pas encore écrite)"
    except Exception as e:
        ok, name = False, f"{name}  (erreur : {type(e).__name__}: {e})"
    passed += ok
    print(("✅ " if ok else "❌ ") + name)

print(f"\n{passed}/{len(tests)} tests réussis")
