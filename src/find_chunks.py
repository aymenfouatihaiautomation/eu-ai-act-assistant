"""Cherche des fiches par mots-clés, pour trouver la bonne réponse d'une question de test.

    python src/find_chunks.py emotion workplace
    python src/find_chunks.py recruitment --lang fr      (cherche dans les fiches françaises)

Une fiche est affichée si elle contient TOUS les mots donnés (majuscules ignorées).
"""
import json
import sys
from pathlib import Path

chunks = json.loads(Path("data/processed/chunks.json").read_text(encoding="utf-8"))

args = sys.argv[1:]
lang = "en"
if "--lang" in args:
    i = args.index("--lang")
    lang = args[i + 1]
    args = args[:i] + args[i + 2:]

words = [w.lower() for w in args]
if not words:
    print("Donne au moins un mot. Exemple : python src/find_chunks.py emotion workplace")
    sys.exit()

found = [c for c in chunks if c["lang"] == lang and all(w in c["text"].lower() for w in words)]

for c in found[:15]:
    # On affiche le début du texte APRÈS l'en-tête (après le premier ":")
    body = c["text"].split(":", 1)[-1].strip()
    print(f"{c['id']:<22} {body[:110]}...")

print(f"\n{len(found)} fiche(s) trouvée(s)" + (" (15 premières affichées)" if len(found) > 15 else ""))
