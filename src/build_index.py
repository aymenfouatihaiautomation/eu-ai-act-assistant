"""T4 — Vectorise toutes les fiches et les range dans ChromaDB.

    python src/build_index.py              → modèle bge-m3 (par défaut)
    python src/build_index.py e5-large     → l'autre modèle

À lancer UNE fois par modèle (et à relancer si chunks.json change).
Sur un ordinateur sans carte graphique : compter 10 à 30 minutes.
"""
import json
import sys
import time
from pathlib import Path

from embeddings import MODELS, encode, get_collection, load_model

CHUNKS = Path("data/processed/chunks.json")
BATCH = 500  # ChromaDB accepte les ajouts par paquets : on envoie 500 fiches à la fois


def main():
    name = sys.argv[1] if len(sys.argv) > 1 else "bge-m3"
    if name not in MODELS:
        print(f"Modèle inconnu : {name}. Choix possibles : {list(MODELS)}")
        return

    chunks = json.loads(CHUNKS.read_text(encoding="utf-8"))
    print(f"{len(chunks)} fiches à vectoriser avec {name}")

    print("Chargement du modèle...")
    model = load_model(name)

    start = time.time()
    texts = [c["text"] for c in chunks]
    vectors = encode(model, name, texts, kind="passage", show_progress=True)
    print(f"Vectorisation : {time.time() - start:.0f} s, {len(vectors[0])} nombres par vecteur")

    # Les métadonnées = tous les champs de la fiche sauf le texte (rangé à part dans "documents")
    metadatas = [{k: v for k, v in c.items() if k not in ("id", "text")} for c in chunks]

    collection = get_collection(name, reset=True)  # on repart de zéro à chaque construction
    for i in range(0, len(chunks), BATCH):
        collection.add(
            ids=[c["id"] for c in chunks[i:i + BATCH]],
            embeddings=vectors[i:i + BATCH],
            documents=texts[i:i + BATCH],
            metadatas=metadatas[i:i + BATCH],
        )
    print(f"Index « {name} » prêt : {collection.count()} fiches dans data/index/")


if __name__ == "__main__":
    main()
