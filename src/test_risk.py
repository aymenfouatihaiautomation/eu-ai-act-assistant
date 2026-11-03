"""Tests de classify() — 12 cas réels. Objectif : 12/12.

Lancement, depuis la racine du projet :
    python src/test_risk.py

Chaque cas = des réponses au questionnaire + le verdict attendu + la raison juridique.
Si un test échoue, lis la RAISON : elle te dit quelle case du schéma est mal codée.
"""
from risk import classify

NO = {"prohibited": False, "annex_i_product": False, "third_party_assessment": False,
      "annex_iii_area": None, "profiling": False, "exception": None}


def case(**changes):
    """Part de « non à tout » et change seulement ce qui est indiqué."""
    return {**NO, **changes}


TESTS = [
    ("Notation sociale des citoyens",
     case(prohibited=True),
     ("prohibited", "art5"),
     "Art. 5 : une pratique interdite s'arrête à la case 1."),

    ("Pratique interdite ET domaine de l'annexe III",
     case(prohibited=True, annex_iii_area="4"),
     ("prohibited", "art5"),
     "L'art. 5 passe AVANT tout le reste : l'ordre des cases compte."),

    ("IA de sécurité dans un dispositif médical, évaluée par un organisme notifié",
     case(annex_i_product=True, third_party_assessment=True),
     ("high_risk", "annex_i"),
     "Art. 6(1) : les deux conditions a) ET b) sont remplies."),

    ("Produit de l'annexe I, mais SANS évaluation par un tiers, hors annexe III",
     case(annex_i_product=True),
     ("not_high_risk", "none"),
     "Art. 6(1) exige les DEUX conditions : une seule ne suffit pas."),

    ("Produit de l'annexe I sans tiers, MAIS utilisé pour le recrutement",
     case(annex_i_product=True, annex_iii_area="4"),
     ("high_risk", "annex_iii"),
     "Raté à la case 2, on CONTINUE vers la case 3 : on ne s'arrête pas."),

    ("Tri automatique de CV",
     case(annex_iii_area="4"),
     ("high_risk", "annex_iii"),
     "Annexe III point 4, pas de profilage, pas d'exception → haut risque."),

    ("Outil de recrutement qui ne fait que classer des fichiers (tâche procédurale)",
     case(annex_iii_area="4", exception="a"),
     ("not_high_risk", "art6_3_exception"),
     "Art. 6(3) a) : exception valable car SANS profilage."),

    ("Correcteur de style d'une lettre de refus déjà rédigée, MAIS avec profilage",
     case(annex_iii_area="4", exception="b", profiling=True),
     ("high_risk", "annex_iii"),
     "Art. 6(3) : le profilage rend TOUJOURS haut risque, l'exception ne compte plus."),

    ("Score de crédit avec profilage",
     case(annex_iii_area="5", profiling=True),
     ("high_risk", "annex_iii"),
     "Annexe III point 5 + profilage."),

    ("Chatbot de service client",
     case(),
     ("not_high_risk", "none"),
     "Ni art. 5, ni annexe I, ni annexe III. (L'art. 50 — transparence — peut s'appliquer, mais ce n'est pas du haut risque.)"),

    ("Composant de sécurité d'une machine évalué par un tiers, avec une exception de l'art. 6(3)",
     case(annex_i_product=True, third_party_assessment=True, annex_iii_area="2", exception="d"),
     ("high_risk", "annex_i"),
     "Les exceptions de l'art. 6(3) valent pour l'annexe III SEULEMENT, jamais pour l'annexe I."),

    ("Profilage, mais hors de tout domaine de l'annexe III",
     case(profiling=True),
     ("not_high_risk", "none"),
     "Le profilage seul ne rend pas haut risque : il ne compte QUE dans un domaine de l'annexe III."),
]


def main():
    passed = 0
    for name, answers, expected, reason in TESTS:
        try:
            got = classify(answers)
        except NotImplementedError:
            print("classify() n'est pas encore écrite : ouvre src/risk.py.")
            return
        if got == expected:
            passed += 1
            print(f"✅ {name}")
        else:
            print(f"❌ {name}\n     attendu {expected}, obtenu {got}\n     → {reason}")
    print(f"\n{passed}/{len(TESTS)} tests réussis")


if __name__ == "__main__":
    main()
