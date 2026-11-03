"""Outils partagés pour T4 et T5 : charger un modèle d'embeddings, vectoriser, ouvrir l'index.

Ce fichier ne se lance pas tout seul : build_index.py, search.py (et plus tard evaluate.py)
l'importent. Comme ça, les réglages des modèles sont écrits à UN seul endroit (DRY).
"""
from pathlib import Path

import chromadb

INDEX_DIR = Path("data/index")   # là où ChromaDB enregistre l'index sur le disque

# Les deux modèles comparés dans G1.
#   prefix : e5 a été entraîné avec "query: " devant les questions et "passage: " devant
#            les textes. Sans ces préfixes, il marche nettement moins bien. BGE-M3 n'en veut pas.
#   max_len : longueur maximale lue, en tokens. Nos fiches font au plus ~600 tokens.
MODELS = {
    "bge-m3": {
        "hf_name": "BAAI/bge-m3",
        "query_prefix": "",
        "passage_prefix": "",
        "max_len": 1024,
    },
    "e5-large": {
        "hf_name": "intfloat/multilingual-e5-large",
        "query_prefix": "query: ",
        "passage_prefix": "passage: ",
        "max_len": 512,
    },
}


def load_model(name):
    """Charge le modèle (depuis le cache local s'il a déjà été téléchargé)."""
    from sentence_transformers import SentenceTransformer  # import ici : il est lent à charger
    model = SentenceTransformer(MODELS[name]["hf_name"])
    model.max_seq_length = MODELS[name]["max_len"]
    return model


def encode(model, name, texts, kind, show_progress=False):
    """Vectorise une liste de textes.
    kind = "query" (une question) ou "passage" (une fiche) : choisit le bon préfixe.
    normalize_embeddings=True : tous les vecteurs ont une longueur de 1,
    donc seule leur DIRECTION compte (c'est la similarité cosinus de la leçon 1)."""
    prefix = MODELS[name][f"{kind}_prefix"]
    vectors = model.encode(
        [prefix + t for t in texts],
        batch_size=16,
        normalize_embeddings=True,
        show_progress_bar=show_progress,
    )
    return vectors.tolist()


def get_collection(name, reset=False):
    """Ouvre (ou crée) la collection ChromaDB d'un modèle.
    Une collection par modèle : leurs vecteurs ne sont pas comparables entre eux."""
    client = chromadb.PersistentClient(path=str(INDEX_DIR))
    if reset:
        try:
            client.delete_collection(name)
        except Exception:
            pass  # elle n'existait pas encore
    # space = cosine : ChromaDB classe par similarité cosinus et renvoie distance = 1 - cosinus
    return client.get_or_create_collection(name, configuration={"hnsw": {"space": "cosine"}})
