"""Vérifie expand_siblings() de diversity.py, sans modèle ni index (2 secondes).

    python src/test_diversity.py
"""
from diversity import MAX_EXTRA, expand_siblings, parent_of

POINTS = ["a", "b", "ba", "bb", "c", "d", "e", "f", "g", "h"]
INDEX = ([f"en-art5-p1-{p}" for p in POINTS] + [f"fr-art5-p1-{p}" for p in POINTS]
         + ["en-art5-p1a-a", "en-art5-p8", "en-art26-p8", "en-art26-p11", "fr-art26-p8",
            "en-art113-a", "en-art113-b", "en-art113-c", "fr-art113-a", "fr-art113-b", "fr-art113-c",
            "en-anxIII-4-a", "en-anxIII-4-b", "en-art43-p3-part1", "en-art43-p3-part2"])


def legal(ids):
    return sorted(i.split("-", 1)[1] for i in ids)


tests = [
    ("parent_of : un point", lambda: parent_of("art5-p1-f") == "art5-p1"),
    ("parent_of : point à 2 lettres", lambda: parent_of("art5-p1-ba") == "art5-p1"),
    ("parent_of : annexe", lambda: parent_of("anxIII-4-a") == "anxIII-4"),
    ("parent_of : un paragraphe n'est pas un point", lambda: parent_of("art26-p8") is None),
    ("parent_of : article seul", lambda: parent_of("art3") is None),

    ("art. 5(1) : top-2 = 2 points → les 8 autres ajoutés",
     lambda: len(expand_siblings(["en-art5-p1-ba", "en-art5-p1-a", "en-art1-p2-b"], INDEX)) == 8),
    ("art. 5(1) : on ajoute les 8 autres points, dans l'ordre du texte",
     lambda: legal(expand_siblings(["en-art5-p1-ba", "en-art5-p1-a"], INDEX))
     == ["art5-p1-b", "art5-p1-bb", "art5-p1-c", "art5-p1-d", "art5-p1-e", "art5-p1-f", "art5-p1-g", "art5-p1-h"]),
    ("art. 5(1) : une fiche déjà gardée plus bas n'est pas ajoutée 2 fois",
     lambda: "en-art5-p1-h" not in expand_siblings(["en-art5-p1-ba", "en-art5-p1-a", "en-art26-p8", "en-art5-p1-h"], INDEX)),
    ("langue : top-2 en français → fiches françaises seulement",
     lambda: all(i.startswith("fr-") for i in expand_siblings(["fr-art5-p1-ba", "fr-art5-p1-a"], INDEX))),
    ("langue : top-2 en anglais → fiches anglaises seulement",
     lambda: all(i.startswith("en-") for i in expand_siblings(["en-art5-p1-ba", "en-art5-p1-a"], INDEX))),
    ("art. 113 : a + b → c ajoutée (la date reste présente)",
     lambda: legal(expand_siblings(["en-art113-a", "en-art113-b"], INDEX)) == ["art113-c"]),
    ("annexe : a + b → rien d'autre à ajouter",
     lambda: expand_siblings(["en-anxIII-4-a", "en-anxIII-4-b"], INDEX) == []),

    ("paragraphes (pas des points) : rien ajouté",
     lambda: expand_siblings(["en-art26-p8", "en-art26-p11"], INDEX) == []),
    ("le 1er est un point, pas le 2e : rien",
     lambda: expand_siblings(["en-art5-p1-a", "en-art26-p8"], INDEX) == []),
    ("2 points de paragraphes différents : rien",
     lambda: expand_siblings(["en-art5-p1-a", "en-art5-p1a-a"], INDEX) == []),
    ("une seule fiche gardée : rien", lambda: expand_siblings(["en-art5-p1-a"], INDEX) == []),
    ("aucune fiche gardée : rien", lambda: expand_siblings([], INDEX) == []),
    ("une fiche coupée en -part1 / -part2 compte pour une seule",
     lambda: expand_siblings(["en-art43-p3-part1", "en-art43-p3-part2"], INDEX) == []),
    ("garde-fou : jamais plus de MAX_EXTRA fiches",
     lambda: len(expand_siblings(["en-art9-p1-a", "en-art9-p1-b"],
                                 [f"en-art9-p1-{c}{d}" for c in "abcd" for d in "abcdef"], max_extra=MAX_EXTRA)) == MAX_EXTRA),
    ("expand_siblings ne modifie pas la liste d'entrée",
     lambda: (lambda k: (expand_siblings(k, INDEX), k)[1] == ["en-art5-p1-ba", "en-art5-p1-a"])(["en-art5-p1-ba", "en-art5-p1-a"])),
]

passed = 0
for name, test in tests:
    try:
        ok = test()
    except Exception as e:
        ok, name = False, f"{name}  (erreur : {type(e).__name__}: {e})"
    passed += ok
    print(("✅ " if ok else "❌ ") + name)

print(f"\n{passed}/{len(tests)} tests réussis")
