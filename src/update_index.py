"""Met à jour un index existant SANS tout revectoriser.

    python src/update_index.py              → bge-m3
    python src/update_index.py e5-large

Compare chunks.json à ce qui est déjà dans ChromaDB :
  - fiche disparue (id absent de chunks.json)   → supprimée de l'index
  - fiche nouvelle ou texte modifié             → vectorisée et (re)rangée
  - fiche identique                             → on n'y touche pas
Après une petite correction de chunk_ai_act.py, ça prend quelques minutes au lieu de 42.
"""
import json
import sys
import time
from pathlib import Path

from embeddings import MODELS, encode, get_collection, load_model

CHUNKS = Path("data/processed/chunks.json")
BATCH = 500


def main():
    name = sys.argv[1] if len(sys.argv) > 1 else "bge-m3"
    if name not in MODELS:
        print(f"Modèle inconnu : {name}. Choix possibles : {list(MODELS)}")
        return

    chunks = json.loads(CHUNKS.read_text(encoding="utf-8"))
    new = {c["id"]: c for c in chunks}

    collection = get_collection(name)
    stored = collection.get(include=["documents"])          # ce que l'index contient déjà
    old = dict(zip(stored["ids"], stored["documents"]))      # id → texte

    to_delete = [i for i in old if i not in new]
    to_add = [c for c in chunks if old.get(c["id"]) != c["text"]]   # absente OU texte différent

    print(f"Index « {name} » : {len(old)} fiches. "
          f"À supprimer : {len(to_delete)}. À (re)vectoriser : {len(to_add)}. "
          f"Inchangées : {len(chunks) - len(to_add)}.")

    if to_delete:
        collection.delete(ids=to_delete)

    if to_add:
        model = load_model(name)
        start = time.time()
        vectors = encode(model, name, [c["text"] for c in to_add], kind="passage", show_progress=True)
        for i in range(0, len(to_add), BATCH):
            part = to_add[i:i + BATCH]
            collection.upsert(                       # upsert = ajoute, ou remplace si l'id existe
                ids=[c["id"] for c in part],
                embeddings=vectors[i:i + BATCH],
                documents=[c["text"] for c in part],
                metadatas=[{k: v for k, v in c.items() if k not in ("id", "text")} for c in part],
            )
        print(f"Vectorisation : {time.time() - start:.0f} s")

    print(f"Index « {name} » à jour : {collection.count()} fiches.")


if __name__ == "__main__":
    main()
