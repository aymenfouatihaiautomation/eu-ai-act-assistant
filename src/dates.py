"""T7.1 — Tableau des dates d'application de l'AI Act, après le Digital Omnibus
(Règlement (UE) 2026/1744, entré en vigueur le 27/07/2026).

POURQUOI UN TABLEAU CODÉ, ET PAS LE LLM ?
  Les 3 échecs de q16 (« quand s'applique... ? ») viennent de la RECHERCHE : la bonne
  fiche de l'article 113 n'arrive pas dans les 10 sources. Une date, c'est un fait
  précis : on ne la laisse pas au hasard d'une recherche. On la code, et on la VÉRIFIE
  contre le texte de loi (voir check() plus bas).

RÈGLE D'OR : chaque ligne du tableau donne
  - la date,
  - la FICHE PRÉCISE qui la fixe (chunk, ex. "art113-c"),
  - la date telle qu'elle est écrite dans cette fiche (evidence en / fr).
  check() vérifie que la date est bien écrite DANS CETTE FICHE-LÀ, en anglais et en
  français. Aucune date n'entre dans le produit sans ✅.

v2 (03/11) : le contrôle v1 cherchait la date dans TOUT l'article → faux ✅
  - « 2 August 2026 » était trouvé dans les 4 fiches de l'art. 113 (l'en-tête de
    chaque fiche répète « It shall apply from 2 August 2026 ») ;
  - « 2 August 2027 » était trouvé dans l'art. 111 § 1, qui parle d'AUTRE CHOSE
    (les grands systèmes informatiques de l'annexe X).
  On vérifie maintenant fiche par fiche. Et 5 dates lues dans la loi ont été ajoutées.

Lancement, depuis la racine du projet :
    python src/dates.py            → vérifie le tableau contre le texte de loi
    python src/dates.py --show     → affiche TOUTES les fiches des articles 111 et 113
    python src/dates.py 2027-01-15 → ce qui s'applique (ou pas encore) à cette date
"""
import json
import sys
from datetime import date
from pathlib import Path

CHUNKS = Path("data/processed/chunks.json")

# Une entrée = une obligation (ou un groupe d'obligations) et sa date.
# "chunk" = l'id de la fiche SANS la langue : on vérifie en-<chunk> et fr-<chunk>.
# "label" est en 3 langues : c'est ce que verra le client dans l'interface (T8).
DATES = [
    {
        "key": "prohibitions",
        "applies": date(2025, 2, 2),
        "chunk": "art113-a",
        "label": {
            "en": "Prohibited AI practices (Art. 5), definitions and AI literacy (Chapters I and II)",
            "fr": "Pratiques d'IA interdites (art. 5), définitions et maîtrise de l'IA (chapitres I et II)",
            "ar": "ممارسات الذكاء الاصطناعي المحظورة (المادة 5) والتعاريف ومحو الأمية في الذكاء الاصطناعي (الفصلان الأول والثاني)",
        },
        "evidence": {"en": "2 February 2025", "fr": "2 février 2025"},
    },
    {
        "key": "gpai_governance_penalties",
        "applies": date(2025, 8, 2),
        "chunk": "art113-b",
        "label": {
            "en": "General-purpose AI models (Chapter V), notified bodies, governance, penalties and confidentiality (Art. 78), except fines on GPAI providers (Art. 101)",
            "fr": "Modèles d'IA à usage général (chapitre V), organismes notifiés, gouvernance, sanctions et confidentialité (art. 78), sauf les amendes des fournisseurs de modèles à usage général (art. 101)",
            "ar": "نماذج الذكاء الاصطناعي للأغراض العامة (الفصل الخامس) والهيئات المُخطَرة والحوكمة والعقوبات والسرية (المادة 78)، باستثناء غرامات مزوّدي النماذج للأغراض العامة (المادة 101)",
        },
        "evidence": {"en": "2 August 2025", "fr": "2 août 2025"},
    },
    {
        "key": "amendments_other_acts",
        "applies": date(2026, 7, 27),
        "chunk": "art113-d",
        "label": {
            "en": "Amendments to other EU acts (Articles 102 to 110)",
            "fr": "Modifications d'autres actes de l'UE (articles 102 à 110)",
            "ar": "تعديلات على تشريعات أخرى للاتحاد الأوروبي (المواد 102 إلى 110)",
        },
        "evidence": {"en": "27 July 2026", "fr": "27 juillet 2026"},
    },
    {
        "key": "general",
        "applies": date(2026, 8, 2),
        "chunk": "art113-a",
        "label": {
            "en": "General application of the Regulation, including transparency obligations (Art. 50) and fines on GPAI providers (Art. 101)",
            "fr": "Application générale du règlement, dont la transparence (art. 50) et les amendes des fournisseurs de modèles à usage général (art. 101)",
            "ar": "التطبيق العام للائحة، بما في ذلك التزامات الشفافية (المادة 50) وغرامات مزوّدي النماذج للأغراض العامة (المادة 101)",
        },
        "evidence": {"en": "2 August 2026", "fr": "2 août 2026"},
    },
    {
        "key": "new_prohibitions",
        "applies": date(2026, 12, 2),
        "chunk": "art113-a",
        "label": {
            "en": "New prohibitions added by the Omnibus: Art. 5(1), points (ba) and (bb), and Art. 5(1a) and (1b)",
            "fr": "Nouvelles interdictions ajoutées par l'Omnibus : art. 5, § 1, points b bis) et b ter), et art. 5, § 1 bis et 1 ter",
            "ar": "المحظورات الجديدة التي أضافها الأومنيبوس: المادة 5(1)، النقطتان (ba) و(bb)، والمادة 5(1a) و(1b)",
        },
        "evidence": {"en": "2 December 2026", "fr": "2 décembre 2026"},
    },
    {
        "key": "art50_2_legacy",
        "applies": date(2026, 12, 2),
        "chunk": "art111-p4",
        "label": {
            "en": "Marking of AI-generated content (Art. 50(2)) for systems already on the market before 2 August 2026",
            "fr": "Marquage des contenus générés par IA (art. 50, § 2) pour les systèmes déjà sur le marché avant le 2 août 2026",
            "ar": "وسم المحتوى المُولَّد بالذكاء الاصطناعي (المادة 50، الفقرة 2) للأنظمة المطروحة في السوق قبل 2 أغسطس 2026",
        },
        "evidence": {"en": "2 December 2026", "fr": "2 décembre 2026"},
    },
    {
        "key": "gpai_legacy",
        "applies": date(2027, 8, 2),
        "chunk": "art111-p3",
        "label": {
            "en": "General-purpose AI models already on the market before 2 August 2025",
            "fr": "Modèles d'IA à usage général déjà sur le marché avant le 2 août 2025",
            "ar": "نماذج الذكاء الاصطناعي للأغراض العامة المطروحة في السوق قبل 2 أغسطس 2025",
        },
        "evidence": {"en": "2 August 2027", "fr": "2 août 2027"},
    },
    {
        "key": "high_risk_annex_iii",
        "applies": date(2027, 12, 2),
        "chunk": "art113-c",
        "label": {
            "en": "High-risk AI systems listed in Annex III (Art. 6(2)): employment, education, credit, etc.",
            "fr": "Systèmes d'IA à haut risque de l'annexe III (art. 6, § 2) : emploi, éducation, crédit, etc.",
            "ar": "أنظمة الذكاء الاصطناعي عالية المخاطر المدرجة في الملحق الثالث (المادة 6، الفقرة 2): التوظيف والتعليم والائتمان وغيرها",
        },
        "evidence": {"en": "2 December 2027", "fr": "2 décembre 2027"},
    },
    {
        "key": "high_risk_annex_i",
        "applies": date(2028, 8, 2),
        "chunk": "art113-c",
        "label": {
            "en": "High-risk AI systems that are safety components of products under Annex I (Art. 6(1))",
            "fr": "Systèmes d'IA à haut risque, composants de sécurité de produits de l'annexe I (art. 6, § 1)",
            "ar": "أنظمة الذكاء الاصطناعي عالية المخاطر التي تُعدّ مكوّنات أمان لمنتجات الملحق الأول (المادة 6، الفقرة 1)",
        },
        "evidence": {"en": "2 August 2028", "fr": "2 août 2028"},
    },
    {
        "key": "public_authorities_legacy",
        "applies": date(2030, 8, 2),
        "chunk": "art111-p2",
        "label": {
            "en": "High-risk AI systems already on the market and used by public authorities: full compliance deadline",
            "fr": "Systèmes à haut risque déjà sur le marché et utilisés par des autorités publiques : date limite de mise en conformité",
            "ar": "الأنظمة عالية المخاطر المطروحة مسبقًا والتي تستخدمها السلطات العامة: الموعد النهائي للامتثال",
        },
        "evidence": {"en": "2 August 2030", "fr": "2 août 2030"},
    },
    {
        "key": "annex_x_legacy",
        "applies": date(2030, 12, 31),
        "chunk": "art111-p1",
        "label": {
            "en": "AI components of large-scale EU IT systems (Annex X) placed on the market before 2 August 2027",
            "fr": "Composants d'IA des grands systèmes d'information de l'UE (annexe X) mis sur le marché avant le 2 août 2027",
            "ar": "مكوّنات الذكاء الاصطناعي في أنظمة المعلومات الأوروبية واسعة النطاق (الملحق العاشر) المطروحة قبل 2 أغسطس 2027",
        },
        "evidence": {"en": "31 December 2030", "fr": "31 décembre 2030"},
    },
]


def load_chunks():
    return json.loads(CHUNKS.read_text(encoding="utf-8"))


def find_evidence(entry, lang, chunks):
    """Vrai si la date est écrite dans LA fiche indiquée (en-<chunk> ou fr-<chunk>).
    EUR-Lex met parfois une espace insécable (\\xa0) dans les dates : on la remplace."""
    wanted = f"{lang}-{entry['chunk']}"
    for c in chunks:
        if c["id"] == wanted:
            return entry["evidence"][lang] in c["text"].replace("\xa0", " ")
    return False  # fiche inexistante → forcément faux


def check(chunks):
    """Vérifie CHAQUE ligne du tableau contre sa fiche, en anglais ET en français."""
    ok = True
    for e in DATES:
        for lang in ("en", "fr"):
            found = find_evidence(e, lang, chunks)
            ok &= found
            print(f"{'✅' if found else '❌'} {e['key']:<26} {lang}  « {e['evidence'][lang]} » dans {lang}-{e['chunk']}")
    print("\nTableau VÉRIFIÉ ✅" if ok else "\n⚠ Des lignes ne sont pas prouvées par le texte : NE PAS les utiliser.")
    return ok


def status(on):
    """Ce qui s'applique déjà, et ce qui ne s'applique pas encore, à la date `on`."""
    ordered = sorted(DATES, key=lambda e: e["applies"])
    applied = [e for e in ordered if e["applies"] <= on]
    pending = [e for e in ordered if e["applies"] > on]
    return applied, pending


def show_articles(chunks):
    """Affiche toutes les fiches EN des articles 111 et 113 (pour contrôler le tableau)."""
    for c in chunks:
        if c["lang"] == "en" and c.get("article") in ("111", "113"):
            print("=" * 80)
            print(c["id"])
            print(c["text"])
    print("=" * 80)


def main():
    chunks = load_chunks()
    if "--show" in sys.argv:
        show_articles(chunks)
    elif len(sys.argv) > 1:
        on = date.fromisoformat(sys.argv[1])
        applied, pending = status(on)
        print(f"Au {on:%d/%m/%Y} :\n\nS'applique déjà :")
        for e in applied:
            print(f"  ✔ depuis le {e['applies']:%d/%m/%Y}  {e['label']['fr']}")
        print("\nPas encore :")
        for e in pending:
            print(f"  … à partir du {e['applies']:%d/%m/%Y}  {e['label']['fr']}")
    else:
        check(chunks)


if __name__ == "__main__":
    main()
