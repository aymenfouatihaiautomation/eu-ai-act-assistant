"""Vérifie is_date_question() et date_source_ids() de dates.py, sans modèle ni index (quelques secondes).

    python src/test_dates.py

Les phrases de test sont de vraies réécritures de Haiku (data/eval/results_answers_claude-haiku-5-5_v3.json).
"""
from dates import DATE_CHUNKS, date_source_ids, is_date_question

INDEX = ["en-art111-p1", "en-art111-p2", "en-art111-p3", "en-art111-p4", "en-art113-a", "en-art113-b",
         "en-art113-c", "en-art113-d", "fr-art113-a", "fr-art111-p3", "en-art5-p1-ba", "en-art43-p3-part1",
         "en-art43-p3-part2"]

tests = [
    # --- questions de date (q13, q14, q16) : doivent déclencher
    ("« When do the prohibitions … begin to apply? » (q13)",
     lambda: is_date_question("When do the prohibitions on prohibited AI practices under the AI Act begin to apply?")),
    ("« From what date do the prohibitions … apply? » (q13 ar)",
     lambda: is_date_question("From what date do the prohibitions on prohibited artificial intelligence practices apply?")),
    ("« From what date does the regulation prohibit … deep fake intimate images … ? » (q16)",
     lambda: is_date_question("From what date does the regulation prohibit the use of AI systems to generate deep fake intimate images of identifiable natural persons?")),
    ("« … listed in Annex III begin to apply? » (q14)",
     lambda: is_date_question("When do the obligations for high-risk AI systems listed in Annex III begin to apply?")),
    ("« Since when … ? »", lambda: is_date_question("Since when do the bans apply?")),
    # --- « when » au milieu d'une phrase : ne doit PAS déclencher (faux positifs vus sur q05, q08, q10, n04, n06)
    ("q05 : « … a prohibited AI practice … when carried out by a public authority … »",
     lambda: not is_date_question("Is the evaluation of natural persons … a prohibited AI practice under the AI Act when carried out by a public authority such as a city?")),
    ("q08 : « Are we a provider or a deployer …, when our organisation uses … »",
     lambda: not is_date_question("Are we a provider or a deployer under the AI Act, when our organisation uses an AI system that was purchased from another company?")),
    ("n06 : « How much does a CE certificate cost when issued … »",
     lambda: not is_date_question("How much does a CE certificate cost when issued by a notified body?")),
    ("question vide", lambda: not is_date_question("")),
    # --- choix des fiches à ajouter
    ("le tableau désigne 8 fiches (art. 111 et 113)", lambda: len(DATE_CHUNKS) == 8),
    ("rien de gardé → les 8 fiches anglaises, dans l'ordre du texte",
     lambda: date_source_ids([], INDEX) == ["en-art111-p1", "en-art111-p2", "en-art111-p3", "en-art111-p4",
                                            "en-art113-a", "en-art113-b", "en-art113-c", "en-art113-d"]),
    ("toujours des ids anglais (la langue de l'utilisateur est choisie ensuite par retrieve.search)",
     lambda: all(i.startswith("en-") for i in date_source_ids(["fr-art5-p1-ba"], INDEX))),
    ("une fiche déjà gardée (même en français) n'est pas ajoutée 2 fois",
     lambda: "en-art113-a" not in date_source_ids(["fr-art113-a", "en-art5-p1-ba"], INDEX)
     and len(date_source_ids(["fr-art113-a"], INDEX)) == 7),
    ("les fiches hors tableau ne sont jamais ajoutées",
     lambda: not any(i in date_source_ids([], INDEX) for i in ["en-art5-p1-ba", "en-art43-p3-part1"])),
    ("la liste d'entrée n'est pas modifiée",
     lambda: (lambda k: (date_source_ids(k, INDEX), k)[1] == ["en-art113-a"])(["en-art113-a"])),
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
