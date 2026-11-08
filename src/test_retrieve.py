"""Vérifie detect_lang() de retrieve.py, sans charger le modèle ni l'index (quelques secondes).

    python src/test_retrieve.py
"""
import json
from pathlib import Path

from retrieve import detect_lang

QUESTIONS = json.loads(Path("data/eval/questions.json").read_text(encoding="utf-8"))

tests = [
    ("« Quelles pratiques d'IA sont interdites ? » → fr",
     lambda: detect_lang("Quelles pratiques d'IA sont interdites ?") == "fr"),
    ("« Quelles pratiques sont interdites ? » → fr",
     lambda: detect_lang("Quelles pratiques sont interdites ?") == "fr"),
    ("« Quels systèmes sont interdits ? » → fr",
     lambda: detect_lang("Quels systèmes sont interdits ?") == "fr"),
    ("« Quelles pratiques d'IA sont interdites par l'AI Act ? » → fr (inchangé)",
     lambda: detect_lang("Quelles pratiques d'IA sont interdites par l'AI Act ?") == "fr"),
    ("anglais : « Which AI practices are prohibited? » → en",
     lambda: detect_lang("Which AI practices are prohibited?") == "en"),
    ("anglais : « What is the maximum fine? » → en",
     lambda: detect_lang("What is the maximum fine?") == "en"),
    ("arabe → ar",
     lambda: detect_lang("ما هي ممارسات الذكاء الاصطناعي المحظورة؟") == "ar"),
]
# Aucune des 78 questions de test ne doit changer de langue détectée.
for lang in ("en", "fr", "ar"):
    wrong = [q["id"] for q in QUESTIONS if detect_lang(q[f"question_{lang}"]) != lang]
    tests.append((f"les {len(QUESTIONS)} questions de test [{lang}] sont bien détectées",
                  lambda wrong=wrong: wrong == []))

passed = 0
for name, test in tests:
    try:
        ok = test()
    except Exception as e:
        ok, name = False, f"{name}  (erreur : {type(e).__name__}: {e})"
    passed += ok
    print(("✅ " if ok else "❌ ") + name)

print(f"\n{passed}/{len(tests)} tests réussis")
