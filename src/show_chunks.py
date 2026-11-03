"""Affiche des chunks pour les vérifier à la main.

    python src/show_chunks.py                 → 5 chunks au hasard
    python src/show_chunks.py en-art5-p1-f    → un chunk précis, par son id
"""
import json
import random
import sys
from pathlib import Path

chunks = json.loads(Path("data/processed/chunks.json").read_text(encoding="utf-8"))

if len(sys.argv) > 1:
    selected = [c for c in chunks if c["id"] == sys.argv[1]]
    if not selected:
        print(f"Aucun chunk avec l'id {sys.argv[1]}")
else:
    selected = random.sample(chunks, 5)

for c in selected:
    print("=" * 80)
    where = f"annexe {c['annex']}" if c.get("annex") else f"article {c['article']} | § {c['paragraph']}"
    print(f"{c['id']}  | {where} | point {c['point']} | {c['kind']}")
    print("-" * 80)
    print(c["text"])
print("=" * 80)
