"""T6.3 — Compléter une LISTE légale que diversify() a coupée.

Le problème (diagnostic du 08/11) : pour « Quelles pratiques d'IA sont interdites ? », la recherche
trouve bien les 10 points de l'article 5(1), mais diversify() n'en garde que 2 (MAX_PER_UNIT = 2).
Or cette règle est utile ailleurs : sans elle, un seul article occuperait les 10 places.

La solution : on ne touche PAS à diversify(). Après lui, si la question visait manifestement une liste,
on AJOUTE les autres points de cette liste, après les 10 sources. Les 10 places d'origine ne changent
pas : cette étape ne peut donc rien faire perdre, seulement ajouter.

« Visait manifestement une liste » = les 2 PREMIÈRES fiches gardées sont deux points (a, b, ba...)
du même paragraphe. Exemples :
    art5-p1-ba + art5-p1-a   → même paragraphe art5-p1 → on ajoute les 8 autres points
    art26-p8   + art26-p11   → deux paragraphes différents (pas des points) → rien
"""
import re

from evaluate import legal_id

MAX_EXTRA = 12   # garde-fou : au plus 12 fiches ajoutées (le maximum mesuré sur nos questions est 8)

# Un « point » = un identifiant qui finit par -a, -b, -ba, -bb... : "art5-p1-f" → paragraphe "art5-p1".
POINT = re.compile(r"^(?P<parent>.+)-(?P<point>[a-z]{1,2})$")


def parent_of(legal):
    """Le paragraphe d'un point, ou None si ce n'est pas un point.
        "art5-p1-f" → "art5-p1" ; "anxIII-4-a" → "anxIII-4" ; "art26-p8" → None"""
    match = POINT.match(legal)
    return match.group("parent") if match else None


def expand_siblings(kept_ids, all_ids, max_extra=MAX_EXTRA):
    """Renvoie les fiches À AJOUTER (jamais les fiches déjà gardées).

    kept_ids : les fiches gardées par diversify(), de la plus proche à la plus lointaine
    all_ids  : tous les ids de l'index (ex. collection.get(include=[])["ids"])
    Les fiches ajoutées sont dans la langue de la 1re fiche gardée, rangées dans l'ordre du texte."""
    if len(kept_ids) < 2:
        return []
    parent = parent_of(legal_id(kept_ids[0]))
    if parent is None or parent_of(legal_id(kept_ids[1])) != parent:
        return []

    lang = kept_ids[0].split("-", 1)[0]
    already = {legal_id(i) for i in kept_ids}
    extra = [i for i in all_ids
             if i.split("-", 1)[0] == lang
             and parent_of(legal_id(i)) == parent
             and legal_id(i) not in already]
    extra.sort(key=lambda i: (legal_id(i), i))
    return extra[:max_extra]
