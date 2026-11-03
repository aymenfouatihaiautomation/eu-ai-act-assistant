"""Vérifie le jeu de test : chaque réponse attendue existe-t-elle vraiment ?

    python src/check_questions.py

Pour chaque question :
  ✅  l'id attendu existe dans chunks.json → le début de la fiche est affiché :
      À TOI de lire et de juger si elle répond VRAIMENT à la question.
  ❌  l'id n'existe pas → cherche le bon avec find_chunks.py et corrige questions.json.
"""
import json
from pathlib import Path

chunks = json.loads(Path("data/processed/chunks.json").read_text(encoding="utf-8"))
questions = json.loads(Path("data/eval/questions.json").read_text(encoding="utf-8"))

# On cherche dans les fiches anglaises : l'id sans la langue ("art5-p1-f") + le préfixe "en-".
# Une fiche découpée en morceaux s'appelle "...-part1", "...-part2" : on l'accepte aussi.
by_id = {c["id"]: c for c in chunks if c["lang"] == "en"}

missing = 0
for q in questions:
    print(f"\n{q['id']} [{q['type']}] {q['question_en']}")
    if not q["expected"]:
        print("    (question sans réponse : l'assistant doit refuser)")
        continue
    for ref in q["expected"]:
        chunk = by_id.get(f"en-{ref}") or by_id.get(f"en-{ref}-part1")
        if chunk is None:
            missing += 1
            print(f"    ❌ {ref} : introuvable")
        else:
            body = chunk["text"].split(":", 1)[-1].strip()
            print(f"    ✅ {ref} : {body[:150]}...")

total = sum(len(q["expected"]) for q in questions)
print(f"\n{len(questions)} questions, {total} réponses attendues, {missing} introuvable(s).")
