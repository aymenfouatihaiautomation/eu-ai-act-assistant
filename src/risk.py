"""T7.2 — « Mon système d'IA est-il à haut risque ? »

L'ARBRE DE DÉCISION (articles 5 et 6 de l'AI Act) — à lire dans l'ordre :

    ┌─────────────────────────────────────────┐
    │ 1. Pratique interdite (art. 5) ?        │── oui ──▶ INTERDIT            (route "art5")
    └─────────────────────────────────────────┘
                    │ non
    ┌─────────────────────────────────────────┐
    │ 2. Annexe I (art. 6, § 1) : les DEUX    │
    │    conditions sont-elles remplies ?     │
    │    a) composant de sécurité d'un        │── oui ──▶ HAUT RISQUE         (route "annex_i")
    │       produit de l'annexe I (ou le      │           (les exceptions du § 3 NE s'appliquent PAS ici)
    │       produit lui-même), ET             │
    │    b) évaluation par un TIERS exigée ?  │
    └─────────────────────────────────────────┘
                    │ non (une seule condition ne suffit pas)
    ┌─────────────────────────────────────────┐
    │ 3. Domaine de l'annexe III (art. 6 § 2)?│── non ──▶ PAS HAUT RISQUE     (route "none")
    └─────────────────────────────────────────┘
                    │ oui
    ┌─────────────────────────────────────────┐
    │ 4. Profilage de personnes physiques ?   │── oui ──▶ HAUT RISQUE         (route "annex_iii")
    │    (art. 6 § 3 : TOUJOURS haut risque)  │           (le profilage bloque toute exception)
    └─────────────────────────────────────────┘
                    │ non
    ┌─────────────────────────────────────────┐
    │ 5. Une exception de l'art. 6 § 3 ?      │── oui ──▶ PAS HAUT RISQUE     (route "art6_3_exception")
    │    a) tâche procédurale étroite         │           (mais le fournisseur doit DOCUMENTER
    │    b) améliore un travail humain fini   │            son évaluation : art. 6 § 4)
    │    c) détecte des écarts, sans remplacer│
    │       l'évaluation humaine              │
    │    d) tâche préparatoire                │
    └─────────────────────────────────────────┘
                    │ non
                    ▼
               HAUT RISQUE                                                  (route "annex_iii")

CE QUI EST À TOI : la fonction classify(). Tout le reste est fourni.
Vérifie-toi avec :  python src/test_risk.py      (objectif : 12/12)
Essaie-le avec   :  python src/risk.py           (questionnaire dans le terminal)
"""
from dates import DATES

# Les 8 domaines de l'annexe III (la clé est le numéro du point de l'annexe).
ANNEX_III_AREAS = {
    "1": "Biométrie (identification à distance, catégorisation, reconnaissance des émotions)",
    "2": "Infrastructures critiques (eau, gaz, électricité, trafic routier, numérique)",
    "3": "Éducation et formation professionnelle (admission, notation, surveillance des examens)",
    "4": "Emploi et gestion des travailleurs (recrutement, tri de CV, promotion, licenciement)",
    "5": "Accès aux services essentiels (crédit, assurance vie/santé, prestations sociales, urgences)",
    "6": "Répression / police",
    "7": "Migration, asile et contrôle aux frontières",
    "8": "Justice et processus démocratiques (élections)",
}

# Les 4 exceptions de l'article 6, paragraphe 3.
EXCEPTIONS = {
    "a": "Le système exécute une tâche procédurale étroite",
    "b": "Il améliore le résultat d'une activité humaine déjà terminée",
    "c": "Il détecte des schémas de décision ou des écarts, sans remplacer ni influencer l'évaluation humaine sans contrôle humain",
    "d": "Il exécute une tâche préparatoire à une évaluation",
}

# Ce que le code affiche pour chaque route : la base légale et la date (tirée de dates.py, déjà vérifiée).
ROUTES = {
    "art5":             {"basis": "Art. 5",                           "date_key": "prohibitions"},
    "annex_i":          {"basis": "Art. 6(1) + Annexe I",             "date_key": "high_risk_annex_i"},
    "annex_iii":        {"basis": "Art. 6(2) + Annexe III",           "date_key": "high_risk_annex_iii"},
    "art6_3_exception": {"basis": "Art. 6(3) (exception) + Art. 6(4)", "date_key": None},
    "none":             {"basis": "Ni art. 5, ni art. 6",             "date_key": None},
}


def classify(answers):
    """LE CŒUR DE L'ARBRE — À ÉCRIRE PAR AYMEN.

    answers est un dict :
        "prohibited"             : bool       — fait-il une pratique de l'art. 5 ?
        "annex_i_product"        : bool       — composant de sécurité / produit de l'annexe I ?
        "third_party_assessment" : bool       — évaluation de conformité par un TIERS exigée ?
        "annex_iii_area"         : str | None — "1" à "8" (clé de ANNEX_III_AREAS), ou None
        "profiling"              : bool       — fait-il du profilage de personnes physiques ?
        "exception"              : str | None — "a" à "d" (clé de EXCEPTIONS), ou None

    Renvoie un tuple (verdict, route) :
        verdict ∈ "prohibited", "high_risk", "not_high_risk"
        route   ∈ "art5", "annex_i", "annex_iii", "art6_3_exception", "none"

    Chaque case du schéma = un `if` qui RENVOIE (return) ou laisse passer à la suivante.
    Comme un `return` arrête la fonction, l'ORDRE des `if` EST l'ordre juridique.
    """
    # Case 1 — Art. 5 : une pratique interdite l'emporte sur TOUT le reste.
    if answers["prohibited"]:
        return ("prohibited", "art5")

    # Case 2 — Art. 6(1) : il faut les DEUX conditions (and), pas une seule.
    # Si une seule est vraie, on ne renvoie rien : on CONTINUE vers la case 3.
    if answers["annex_i_product"] and answers["third_party_assessment"]:
        return ("high_risk", "annex_i")

    # Case 3 — Art. 6(2) : hors annexe III, ce n'est pas du haut risque.
    # (None = « aucun domaine » ; `not None` vaut True.)
    if not answers["annex_iii_area"]:
        return ("not_high_risk", "none")

    # À partir d'ici, on est FORCÉMENT dans un domaine de l'annexe III.

    # Case 4 — Art. 6(3), dernier alinéa : le profilage rend TOUJOURS haut risque.
    # Il est testé AVANT les exceptions, sinon une exception pourrait l'emporter.
    if answers["profiling"]:
        return ("high_risk", "annex_iii")

    # Case 5 — Art. 6(3) a) à d) : une exception sort du haut risque.
    if answers["exception"]:
        return ("not_high_risk", "art6_3_exception")

    # Annexe III, sans profilage ni exception : haut risque.
    return ("high_risk", "annex_iii")


def explain(answers):
    """Transforme le verdict en un résultat complet : verdict, base légale, date."""
    verdict, route = classify(answers)
    info = ROUTES[route]
    entry = next((d for d in DATES if d["key"] == info["date_key"]), None)
    return {
        "verdict": verdict,
        "route": route,
        "basis": info["basis"],
        "applies": entry["applies"] if entry else None,
    }


# ---------- Questionnaire dans le terminal (pour essayer) ----------

def ask_yes_no(question):
    while True:
        reply = input(f"{question} (o/n) : ").strip().lower()
        if reply in ("o", "n"):
            return reply == "o"


def ask_choice(question, choices):
    print(question)
    for key, label in choices.items():
        print(f"   {key}) {label}")
    while True:
        reply = input("Ton choix (ou Entrée pour « aucun ») : ").strip().lower()
        if reply == "":
            return None
        if reply in choices:
            return reply


def main():
    answers = {"prohibited": ask_yes_no("1. Le système fait-il une pratique interdite par l'art. 5 ?")}
    if not answers["prohibited"]:
        answers["annex_i_product"] = ask_yes_no("2a. Est-ce un composant de sécurité d'un produit de l'annexe I (ou ce produit lui-même) ?")
        answers["third_party_assessment"] = ask_yes_no("2b. Ce produit doit-il passer une évaluation de conformité par un TIERS ?")
        answers["annex_iii_area"] = ask_choice("3. Dans quel domaine de l'annexe III est-il utilisé ?", ANNEX_III_AREAS)
        if answers["annex_iii_area"]:
            answers["profiling"] = ask_yes_no("4. Fait-il du profilage de personnes physiques ?")
            if not answers["profiling"]:
                answers["exception"] = ask_choice("5. Une de ces exceptions s'applique-t-elle ?", EXCEPTIONS)
    # Les questions non posées valent « non » / « aucun ».
    defaults = {"annex_i_product": False, "third_party_assessment": False,
                "annex_iii_area": None, "profiling": False, "exception": None}
    answers = {**defaults, **answers}

    r = explain(answers)
    print(f"\nVerdict : {r['verdict']}  —  base légale : {r['basis']}")
    if r["applies"]:
        print(f"Obligations applicables à partir du : {r['applies']:%d/%m/%Y}")


if __name__ == "__main__":
    main()
