"""T6.2 — La recherche « de production » : le réglage retenu en T5/T6.1, en une fonction.

    question → réécriture v2 (LLM) → BGE-M3 → 50 plus proches → diversité → 10 fiches
             → chaque fiche est rendue dans la LANGUE de l'utilisateur si elle existe

Utilisé par answer.py (et plus tard par l'interface web).
"""
import re
import threading

from embeddings import encode, get_collection, load_model
from evaluate import POOL, diversify, legal_id
from query_rewrite import transform

MODEL_NAME = "bge-m3"
K = 10

_model = None
_collection = None
_lock = threading.Lock()


def _load():
    """Charge le modèle et l'index UNE seule fois (le chargement prend plusieurs secondes).

    v3 (03/11) : le VERROU (lock). Sans lui, deux questions arrivées en même temps
    chargeaient TOUTES LES DEUX le modèle et ouvraient TOUTES LES DEUX ChromaDB au même
    instant → ChromaDB plantait (« RustBindingsAPI... », « KeyError: 'data\\\\index' »).
    Avec le verrou, la 2e question attend que la 1re ait fini de charger, puis réutilise tout."""
    global _model, _collection
    with _lock:
        if _model is None:
            _model = load_model(MODEL_NAME)
            _collection = get_collection(MODEL_NAME)
    return _model, _collection


def warm_up():
    """Charge tout AU DÉMARRAGE du serveur, pour que le 1er visiteur n'attende pas."""
    _load()


ARABIC = re.compile(r"[؀-ۿ]")
FRENCH_WORDS = {"le", "la", "les", "des", "de", "du", "au", "aux", "est", "une", "un", "pour", "nous",
                "notre", "nos", "vous", "votre", "je", "il", "elle", "que", "qui", "quelle", "quel",
                "quand", "depuis", "dans", "avec", "sont", "pouvons", "devons", "puis", "peut", "doit",
                "comment", "pourquoi", "combien", "faut", "sur", "par", "ou", "et", "si", "ce", "cette"}
FRENCH_ACCENTS = re.compile(r"[éèêëàâçîïôûùœ]")


def detect_lang(text):
    """'ar', 'fr' ou 'en'. Simple, mais suffisant pour nos 3 langues."""
    if ARABIC.search(text):
        return "ar"
    lower = text.lower()
    words = set(re.findall(r"[a-zàâçéèêëîïôûùüÿœ]+", lower))
    # v2 : 2 mots français courants, OU 1 mot + un accent français (l'anglais n'a presque pas d'accents)
    # Ratait : « Depuis quand les interdictions... », « Puis-je breveter une invention créée... »
    hits = len(words & FRENCH_WORDS)
    return "fr" if hits >= 2 or (hits >= 1 and FRENCH_ACCENTS.search(lower)) else "en"


def citation_label(meta, lang="en"):
    """Le libellé à citer : 'Article 5(1)(f)' ou 'Annex III, point 4(a)' ('Annexe' en français)."""
    if meta.get("annex"):
        label = f"{'Annexe' if lang == 'fr' else 'Annex'} {meta['annex']}"
        return f"{label}, point {meta['point']}" if meta.get("point") else label
    label = f"Article {meta['article']}"
    if meta.get("paragraph"):
        label += f"({meta['paragraph']})"
    if meta.get("point"):
        label += f"({meta['point']})"
    return label


def search(question):
    """Renvoie (requête réécrite, langue, [fiches]) ; une fiche = {id, label, text, meta}."""
    model, collection = _load()
    lang = detect_lang(question)
    rewritten = transform([question], "rewrite_v2")[0]

    res = collection.query(query_embeddings=encode(model, MODEL_NAME, [rewritten], kind="query"),
                           n_results=POOL)
    ids, _ = diversify(res["ids"][0], res["distances"][0], K)

    # L'utilisateur francophone lit la version FRANÇAISE officielle de la fiche ;
    # l'arabe n'existe pas au Journal officiel : on donne l'anglais.
    source_lang = "fr" if lang == "fr" else "en"
    wanted = [f"{source_lang}-{chunk_id.split('-', 1)[1]}" for chunk_id in ids]
    stored = collection.get(ids=wanted, include=["documents", "metadatas"])
    by_id = {i: (doc, meta) for i, doc, meta in zip(stored["ids"], stored["documents"], stored["metadatas"])}

    chunks = []
    for original, chunk_id in zip(ids, wanted):
        if chunk_id not in by_id:           # sécurité : si la version traduite manque,
            chunk_id = original             # on garde celle trouvée par la recherche
            got = collection.get(ids=[chunk_id], include=["documents", "metadatas"])
            by_id[chunk_id] = (got["documents"][0], got["metadatas"][0])
        doc, meta = by_id[chunk_id]
        chunks.append({"id": chunk_id, "legal_id": legal_id(chunk_id),
                       "label": citation_label(meta, lang), "text": doc, "meta": meta})
    return rewritten, lang, chunks
