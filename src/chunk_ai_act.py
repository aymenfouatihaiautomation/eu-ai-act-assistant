"""T2.4–T2.5 — Découpe tout le règlement (articles et annexes) en chunks, en anglais et en français.

Entrée  : data/raw/ai_act_consolidated_en.html et _fr.html (version consolidée du 27/07/2026)
Sortie  : data/processed/chunks.json

Règles de découpage (décisions G1) :
  - un POINT (a), (b)... = un chunk, sous-points (i), (ii) inclus
  - un paragraphe SANS points = un chunk
  - le texte placé APRÈS les points ("suite") = un chunk à part
  - chaque chunk commence par un EN-TÊTE de contexte :
      "Article 5 (Prohibited AI practices), paragraph 1: The following AI practices
       shall be prohibited: (f) the placing on the market..."

v2 (30/10) : récupère les points posés directement dans l'article (définitions de l'art. 3)
     et coupe aux fins de phrases les textes de plus de 2 000 caractères.

v3 (30/10) : ajoute les annexes (T2.5). Pour l'annexe III : un sous-point = un chunk,
     avec l'intro de l'annexe et l'intitulé du domaine ("4. Employment...: (a) ...").
v4 (30/10) : ids d'annexes uniques et identiques EN/FR ; titres de section gardés dans le contexte.
v5 (30/10) : une phrase courte placée après le dernier point d'une annexe n'est plus perdue.
v6 (01/11) : correctifs issus de l'évaluation T5
     - "Chapter II" devient "Chapter II (Prohibited AI practices)" dans le texte : la recherche
       ratait art113-a, qui parle de "Chapters I and II" sans jamais dire "prohibited practices".
     - ids identiques EN/FR pour les éléments insérés : "b bis)" (FR) = "(ba)" (EN),
       "1 bis" (FR) = "1a" (EN).

Lancement, depuis la racine du projet :
    python src/chunk_ai_act.py
"""
import json
import re
from pathlib import Path

from bs4 import BeautifulSoup, NavigableString

# --- Réglages -----------------------------------------------------------------

FILES = {
    "en": Path("data/raw/ai_act_consolidated_en.html"),
    "fr": Path("data/raw/ai_act_consolidated_fr.html"),
}
OUTPUT = Path("data/processed/chunks.json")
SOURCE = "02024R1689-20260727"  # CELEX de la version consolidée utilisée

# Les mots de l'en-tête changent selon la langue
LABELS = {
    "en": {"article": "Article", "paragraph": "paragraph", "suite": "closing text",
           "annex": "Annex", "point": "point"},
    "fr": {"article": "Article", "paragraph": "paragraphe", "suite": "texte final",
           "annex": "Annexe", "point": "point"},
}

ARTICLE_ID = re.compile(r"art_(\d+[a-z]*)")


# --- Étage 1 : les articles (vient de list_articles.py) -------------------------

def find_articles(soup):
    """Renvoie [(numéro, intitulé, div_article), ...] pour tous les articles."""
    articles = []
    for div in soup.find_all("div", class_="eli-subdivision"):
        match = ARTICLE_ID.fullmatch(div.get("id", ""))
        if not match:
            continue
        title_tag = div.find("p", class_="stitle-article-norm")
        title = clean_title(title_tag.get_text(" ", strip=True)) if title_tag else ""
        articles.append((match.group(1), title, div))
    return articles


def clean_title(title):
    """Retire les guillemets et apostrophes parasites en fin de titre ("Subject matter'")."""
    return title.strip(" '’\"")


# --- Étage 3 : les points (vient de article_points.py) --------------------------

def is_point(tag):
    return tag.name == "div" and "grid-list" in tag.get("class", [])


def read_point(point):
    letter_col = point.find("div", class_="grid-list-column-1")
    text_col = point.find("div", class_="grid-list-column-2")
    if letter_col is None or text_col is None:
        return None
    return letter_col.get_text(strip=True), text_col.get_text(" ", strip=True)


def split_paragraph(container):
    """Range le contenu d'un paragraphe en intro / points / suite, dans l'ordre."""
    intro, points, suite = [], [], []
    for child in container.children:
        if isinstance(child, NavigableString):
            text = child.strip()
        elif is_point(child):
            point = read_point(child)
            if point:
                points.append(point)
            continue
        elif "no-parag" in child.get("class", []):
            continue
        else:
            text = child.get_text(" ", strip=True)
        if text:
            (suite if points else intro).append(text)
    return " ".join(intro), points, " ".join(suite)


# --- Étage 2 : les paragraphes (vient de article_points.py v3) ------------------

def read_paragraphs(article):
    """Renvoie [[numéro, intro, points, suite], ...] pour un article."""
    paragraphs = []
    for child in article.find_all(recursive=False):
        classes = child.get("class", [])
        if child.name == "div" and "norm" in classes:
            number_tag = child.find("span", class_="no-parag")
            number = number_tag.get_text(strip=True).rstrip(".") if number_tag else ""
            container = child.find("div", class_="inline-element", recursive=False) or child
            intro, points, suite = split_paragraph(container)
            paragraphs.append([number, intro, points, suite])
        elif is_point(child):
            # v2 : point posé DIRECTEMENT dans l'article, sans paragraphe numéroté
            # (ex. art. 3 : les 68 définitions "(1) 'AI system' means...").
            # Il appartient au dernier bloc sans numéro, sinon on en crée un.
            point = read_point(child)
            if point is None:
                continue
            if not paragraphs or paragraphs[-1][0] != "":
                paragraphs.append(["", "", [], ""])
            paragraphs[-1][2].append(point)
        elif child.name == "p" and "norm" in classes:
            text = child.get_text(" ", strip=True)
            if not paragraphs:
                # début d'un article sans paragraphes numérotés : c'est l'intro
                # ("For the purposes of this Regulation, the following definitions apply:")
                paragraphs.append(["", text, [], ""])
            elif paragraphs[-1][0] == "" and not paragraphs[-1][2] and not paragraphs[-1][3]:
                # toujours avant les points : l'intro continue
                paragraphs[-1][1] = (paragraphs[-1][1] + " " + text).strip()
            else:
                # alinéa isolé après un paragraphe ou des points : c'est sa suite
                paragraphs[-1][3] = (paragraphs[-1][3] + " " + text).strip()
    return paragraphs


# --- Découpe des chunks trop longs (v2) ------------------------------------------

# multilingual-e5-large ne lit que 512 tokens (≈ 2 000 caractères) : au-delà, il coupe
# sans prévenir. On découpe donc les textes longs AUX FINS DE PHRASES.
MAX_CHARS = 2000

# Une fin de phrase = ". " ou "; " suivi d'une majuscule ou d'une parenthèse.
SENTENCE_END = re.compile(r"(?<=[.;])\s+(?=[A-ZÀ-ÖØ-Þ(‘'«])")


def split_long(body):
    """Renvoie [body] si court, sinon une liste de morceaux de moins de MAX_CHARS environ."""
    if len(body) <= MAX_CHARS:
        return [body]
    sentences = SENTENCE_END.split(body)
    parts, current = [], ""
    for sentence in sentences:
        if current and len(current) + len(sentence) + 1 > MAX_CHARS:
            parts.append(current)
            current = sentence
        else:
            current = f"{current} {sentence}".strip()
    if current:
        parts.append(current)
    return parts


# --- Construction des chunks ---------------------------------------------------

def make_header(lang, article_no, title, paragraph_no):
    """'Article 5 (Prohibited AI practices), paragraph 1:'"""
    words = LABELS[lang]
    header = f"{words['article']} {article_no}"
    if title:
        header += f" ({title})"
    if paragraph_no:
        header += f", {words['paragraph']} {paragraph_no}"
    return header + ":"


def make_chunks(lang, article_no, title, paragraph_no, point, kind, body):
    """Renvoie UN chunk, ou PLUSIEURS si le texte est trop long (v2).
    Un chunk = le texte à vectoriser + les métadonnées qui servent à citer et filtrer."""
    header = make_header(lang, article_no, title, paragraph_no)   # garde "1 bis" pour l'affichage
    point_id = normalize(point) if point else ""                  # v6 : "b bis)" → "ba"
    paragraph_id = normalize(paragraph_no) if paragraph_no else ""  # v6 : "1 bis" → "1a"
    base_id = f"{lang}-art{article_no}"
    if paragraph_id:
        base_id += f"-p{paragraph_id}"
    if point_id:
        base_id += f"-{point_id}"
    if kind == "suite":
        base_id += "-suite"

    parts = split_long(body)
    chunks = []
    for i, part in enumerate(parts, start=1):
        multi = len(parts) > 1
        chunks.append({
            "id": f"{base_id}-part{i}" if multi else base_id,
            "lang": lang,
            "source": SOURCE,
            "article": article_no,
            "annex": "",
            "article_title": title,
            "paragraph": paragraph_id,
            "point": point_id,
            "kind": kind,                     # "point", "paragraph" ou "suite"
            "part": f"{i}/{len(parts)}" if multi else "",
            "text": f"{header} {f'[{i}/{len(parts)}] ' if multi else ''}{part}",
        })
    return chunks


# --- Annexes (v3, T2.5) -----------------------------------------------------------
#
# Structure observée (annexe III) :
#   <div id="anx_III">
#     <p class="title-annex-1">ANNEX III</p>
#     <p class="title-annex-2">High-risk AI systems referred to in Article 6(2)</p>
#     <p class="norm">High-risk AI systems ... are ... listed in any of the following areas:</p>  ← intro
#     <div class="grid-list"> 1. | Biometrics, ...:                                      ← domaine
#                                  <div class="grid-list"> (a) | remote biometric ...     ← sous-point
#     <div class="grid-list"> 2. | Critical infrastructure: AI systems ...               ← domaine sans sous-points
#
# Règle : un sous-point = un chunk ; un domaine sans sous-points = un chunk.
# Chaque chunk reprend l'intro de l'annexe + l'intitulé du domaine.

ANNEX_ID = re.compile(r"anx_([IVXLC]+)")


def roman_to_int(roman):
    """'XIII' → 13. Sert seulement à trier les annexes dans l'ordre."""
    values = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100}
    total = 0
    for i, letter in enumerate(roman):
        value = values[letter]
        # un chiffre plus petit AVANT un plus grand se soustrait : IV = 5 - 1
        if i + 1 < len(roman) and values[roman[i + 1]] > value:
            total -= value
        else:
            total += value
    return total


def find_annexes(soup):
    """Renvoie [(numéro romain, titre, div_annexe), ...]."""
    annexes = []
    for div in soup.find_all("div", id=ANNEX_ID):
        match = ANNEX_ID.fullmatch(div.get("id", ""))
        if not match:
            continue  # ex. "anx_III.pnt_1" : un morceau d'annexe, pas l'annexe entière
        title_tag = div.find("p", class_="title-annex-2")
        title = clean_title(title_tag.get_text(" ", strip=True)) if title_tag else ""
        annexes.append((match.group(1), title, div))
    return annexes


def normalize(label):
    """Rend un numéro ou une lettre identique dans les deux langues.
    '(a)' (anglais) et 'a)' (français) → 'a' ; '4.' → '4' ; '—' reste '—'.
    v6 : 'b bis)' (français) → 'ba', comme '(ba)' en anglais ; '1 bis' → '1a'."""
    label = re.sub(r"[()\s.]", "", label)
    return LATIN_SUFFIX.sub(lambda m: LATIN_TO_LETTER[m.group(1)], label)


# v6 : en français, un élément inséré s'appelle "bis", "ter"... ; en anglais "a", "b"...
#   point "b bis)" = "(ba)", "b ter)" = "(bb)" ; paragraphe "1 bis" = "1a"
LATIN_TO_LETTER = {"bis": "a", "ter": "b", "quater": "c", "quinquies": "d",
                   "sexies": "e", "septies": "f", "octies": "g"}
LATIN_SUFFIX = re.compile(r"(bis|ter|quater|quinquies|sexies|septies|octies)$")


def read_item(item):
    """Lit un domaine '1. Biometrics...' : renvoie (numéro, intitulé, sous-points, suite)."""
    number_col = item.find("div", class_="grid-list-column-1")
    text_col = item.find("div", class_="grid-list-column-2")
    number = number_col.get_text(strip=True) if number_col else ""
    if text_col is None:
        return number, "", [], ""
    heading, subpoints, suite = split_paragraph(text_col)  # même logique intro/points/suite
    return number, heading, subpoints, suite


def make_annex_chunks(lang, annex_no, title, chunk_id, point, kind, body):
    """Comme make_chunks, mais pour une annexe : 'Annex III (titre), point 4(a):'.
    v4 : l'id est fourni par chunk_annex (compteur), pour qu'il soit UNIQUE et
    IDENTIQUE en anglais et en français."""
    words = LABELS[lang]
    header = f"{words['annex']} {annex_no}"
    if title:
        header += f" ({title})"
    if point:
        header += f", {words['point']} {point}"
    header += ":"

    parts = split_long(body)
    chunks = []
    for i, part in enumerate(parts, start=1):
        multi = len(parts) > 1
        chunks.append({
            "id": f"{chunk_id}-part{i}" if multi else chunk_id,
            "lang": lang,
            "source": SOURCE,
            "article": "",
            "annex": annex_no,
            "article_title": title,
            "paragraph": "",
            "point": point,
            "kind": kind,                     # "point" ou "text"
            "part": f"{i}/{len(parts)}" if multi else "",
            "text": f"{header} {f'[{i}/{len(parts)}] ' if multi else ''}{part}",
        })
    return chunks


# Un texte court entre deux listes est un titre de section ("Section A — ...")
SECTION_MAX_CHARS = 200


def chunk_annex(lang, annex_no, title, annex):
    """Découpe une annexe en chunks.

    v4 :
      - id = position de l'élément dans l'annexe (i1, i2...), pas son numéro affiché :
        l'annexe VIII recommence à 1 dans chaque section, l'annexe II utilise des tirets.
        Pour l'annexe III (domaines 1 à 8, dans l'ordre), on retombe sur en-anxIII-4-a.
      - lettres normalisées : '(a)' et 'a)' donnent le même id en anglais et en français.
      - un texte court entre deux listes est un titre de section : il est ajouté au
        contexte des points qui suivent, au lieu d'être rejeté en fin d'annexe."""
    chunks = []
    intro = ""          # texte avant le premier élément
    section = ""        # titre de section en cours (annexes VII, VIII...)
    loose = []          # texte long hors listes
    position = 0        # n° d'ordre de l'élément dans l'annexe
    section_used = True # le titre de section en cours a-t-il servi à au moins un point ?

    def context(number, heading):
        return " ".join(x for x in [intro, section, f"{number} {heading}".strip()] if x)

    for child in annex.find_all(recursive=False):
        classes = child.get("class", [])
        if any(c.startswith("title-annex") for c in classes) or child.name == "hr":
            continue

        if is_point(child):
            position += 1
            section_used = True
            number, heading, subpoints, suite = read_item(child)
            num = normalize(number)
            # identifiant : le numéro affiché s'il suit l'ordre (annexe III), sinon la position
            key = num if num == str(position) else f"i{position}"
            base_id = f"{lang}-anx{annex_no}-{key}"
            shown = num if num not in ("", "—", "-") else ""   # ce qu'on affiche pour citer

            if subpoints:
                for letter, text in subpoints:
                    let = normalize(letter)
                    point = f"{shown}({let})" if shown else f"({let})"
                    body = f"{context(number, heading)} {letter} {text}"
                    chunks.extend(make_annex_chunks(lang, annex_no, title, f"{base_id}-{let}", point, "point", body))
                if suite:
                    body = f"{context(number, heading)} {suite}"
                    chunks.extend(make_annex_chunks(lang, annex_no, title, f"{base_id}-suite", shown, "point", body))
            else:
                body = f"{context(number, heading)} {suite}".strip()
                chunks.extend(make_annex_chunks(lang, annex_no, title, base_id, shown, "point", body))
            continue

        text = child.get_text(" ", strip=True)
        if not text:
            continue
        if position == 0:
            intro = f"{intro} {text}".strip()        # avant toute liste : intro
        elif len(text) <= SECTION_MAX_CHARS:
            if not section_used:
                loose.append(section)                # titre précédent jamais suivi d'un point : on le garde
            section = text                           # texte court entre deux listes : titre de section
            section_used = False
            # Une vraie intro finit par ":" ("...the following areas:"). Sinon, c'était
            # en fait le titre de la PREMIÈRE section : il ne doit pas suivre les suivantes.
            if not intro.endswith(":"):
                intro = ""
        else:
            loose.append(text)                       # texte long : gardé à part

    # v5 : un texte court APRÈS le dernier point n'est pas un titre de section, c'est une
    # phrase finale ("This list may be amended..."). Sans cette ligne, elle disparaissait.
    if not section_used:
        loose.append(section)

    # Annexe sans liste (tout est dans intro) ou textes longs hors listes
    remaining = " ".join(loose) if position else intro
    if remaining:
        for n, block in enumerate(split_long(remaining), start=1):
            chunks.extend(make_annex_chunks(lang, annex_no, title, f"{lang}-anx{annex_no}-text{n}",
                                            "", "text", block))
    return chunks


# --- Titres des chapitres (v6) ------------------------------------------------------
#
# Structure observée :
#   <div id="cpt_II">
#     <p class="title-division-1">CHAPTER II</p>
#     <p class="title-division-2">PROHIBITED AI PRACTICES</p>

CHAPTER_ID = re.compile(r"cpt_([IVXLC]+)")
ACRONYMS = {"AI", "IA", "EU", "UE", "GPAI"}


def sentence_case(title):
    """'PROHIBITED AI PRACTICES' → 'Prohibited AI practices' ;
    'PRATIQUES INTERDITES EN MATIÈRE D’IA' → 'Pratiques interdites en matière d’IA'."""
    text = title.lower()
    # remet en majuscules les sigles, y compris après une apostrophe ("d’ia" → "d’IA")
    text = re.sub(r"(?<![a-zà-ÿ])(" + "|".join(a.lower() for a in ACRONYMS) + r")(?![a-zà-ÿ])",
                  lambda m: m.group(1).upper(), text)
    return text[:1].upper() + text[1:]   # majuscule au premier mot


def find_chapters(soup):
    """Renvoie {"II": "Prohibited AI practices", ...}."""
    chapters = {}
    for div in soup.find_all("div", id=CHAPTER_ID):
        match = CHAPTER_ID.fullmatch(div.get("id", ""))
        if not match:
            continue  # ex. "cpt_III.sct_1" : une section, pas le chapitre
        title_tag = div.find("p", class_="title-division-2", recursive=False)
        if title_tag:
            chapters[match.group(1)] = sentence_case(title_tag.get_text(" ", strip=True))
    return chapters


# "Chapter II", "Chapters I and II", "chapitre III", "chapitres I et II"...
# SAUF quand le chapitre est celui d'un AUTRE texte : "Chapter II of Regulation (EU) 2016/679".
CHAPTER_REF = re.compile(
    r"\b([Cc]hapters?|[Cc]hapitres?)\s+([IVX]+(?:\s*(?:,|and|et)\s*[IVX]+)*)\b"
    r"(?!\s+(?:of|to)\s+(?:Regulation|Directive|Decision)\b|\s+(?:du|de la)\s+(?:règlement|directive|décision)\b)"
)


def enrich_chapters(text, chapters):
    """Ajoute le titre après chaque numéro de chapitre cité dans le texte."""
    def add_titles(match):
        word, numbers = match.group(1), match.group(2)
        numbers = re.sub(r"\b[IVX]+\b",
                         lambda n: f"{n.group(0)} ({chapters[n.group(0)]})" if n.group(0) in chapters else n.group(0),
                         numbers)
        return f"{word} {numbers}"
    return CHAPTER_REF.sub(add_titles, text)


def chunk_file(lang, path):
    soup = BeautifulSoup(path.read_text(encoding="utf-8"), "lxml")

    # On retire les marques d'amendement (▼M1, ▼B) dans tout le document
    for mark in soup.find_all("p", class_="modref"):
        mark.decompose()

    chunks = []
    for article_no, title, article in find_articles(soup):
        for paragraph_no, intro, points, suite in read_paragraphs(article):
            if points:
                for letter, text in points:
                    body = f"{intro} {letter} {text}".strip()
                    chunks.extend(make_chunks(lang, article_no, title, paragraph_no, letter, "point", body))
                if suite:
                    words = LABELS[lang]
                    body = f"({words['suite']}) {suite}"
                    chunks.extend(make_chunks(lang, article_no, title, paragraph_no, "", "suite", body))
            else:
                body = f"{intro} {suite}".strip()
                if body:
                    chunks.extend(make_chunks(lang, article_no, title, paragraph_no, "", "paragraph", body))

    for annex_no, title, annex in find_annexes(soup):
        chunks.extend(chunk_annex(lang, annex_no, title, annex))

    # v6 : on ajoute les titres des chapitres cités, dans le texte de chaque fiche
    chapters = find_chapters(soup)
    enriched = 0
    for chunk in chunks:
        new_text = enrich_chapters(chunk["text"], chapters)
        enriched += new_text != chunk["text"]
        chunk["text"] = new_text
    print(f"[{lang}] {len(chapters)} chapitres trouvés, {enriched} fiches enrichies")
    return chunks


# --- Contrôles automatiques ------------------------------------------------------

def check(chunks):
    """Signale ce qui doit être regardé à la main. Ne corrige rien."""
    ids = [c["id"] for c in chunks]
    duplicates = {i for i in ids if ids.count(i) > 1}
    if duplicates:
        print(f"  ⚠ ids en double : {sorted(duplicates)[:10]}")

    short = [c["id"] for c in chunks if len(c["text"]) < 80]
    if short:
        print(f"  ⚠ {len(short)} chunks très courts (< 80 caractères) : {short[:10]}")

    long_ = [c["id"] for c in chunks if len(c["text"]) > 3000]
    if long_:
        print(f"  ⚠ {len(long_)} chunks très longs (> 3000 caractères) : {long_[:10]}")

    leftovers = [c["id"] for c in chunks if "▼" in c["text"]]
    if leftovers:
        print(f"  ⚠ marques ▼ restantes : {leftovers[:10]}")


def main():
    all_chunks = []
    for lang, path in FILES.items():
        if not path.exists():
            print(f"[{lang}] fichier introuvable : {path}")
            continue
        chunks = chunk_file(lang, path)
        articles = {c["article"] for c in chunks if c["article"]}
        annexes = {c["annex"] for c in chunks if c["annex"]}
        lengths = [len(c["text"]) for c in chunks]
        print(f"[{lang}] {len(chunks)} chunks, {len(articles)} articles, {len(annexes)} annexes, "
              f"longueur min/moy/max = {min(lengths)}/{sum(lengths) // len(lengths)}/{max(lengths)}")
        # Répartition : d'où viennent les chunks ?
        in_articles = [c for c in chunks if c["article"]]
        print(f"     articles : {len(in_articles)} chunks "
              f"(dont {sum(c['article'] == '3' for c in in_articles)} pour l'art. 3, "
              f"{sum(bool(c['part']) for c in in_articles)} morceaux de textes longs)")
        for annex in sorted(annexes, key=roman_to_int):
            print(f"     annexe {annex:>4} : {sum(c['annex'] == annex for c in chunks)} chunks")
        check(chunks)
        all_chunks.extend(chunks)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(all_chunks, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{len(all_chunks)} chunks écrits dans {OUTPUT}")


if __name__ == "__main__":
    main()
