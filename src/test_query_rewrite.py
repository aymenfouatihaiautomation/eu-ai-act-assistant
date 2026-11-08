"""Vérifie clean_rewrite() de query_rewrite.py, sans appel au LLM (2 secondes).

    python src/test_query_rewrite.py

Les 4 textes « fuite » sont de vraies réponses de Haiku (rewrite_v2, data/eval/llm_cache.json).
"""
from query_rewrite import CLEANED_MODES, PROMPTS, _finish, clean_rewrite, strip_regulation_number

FALLBACK = "QUESTION D'ORIGINE"

LEAK_DOCS = (
    'The user is a provider of a general-purpose AI model supplying it to downstream companies. '
    'The AI Act terms: "provider of a general-purpose AI model", "downstream providers". '
    'Rewrite in one sentence, no added obligations beyond what\'s asked (documentation).\n\n'
    'Rewritten question:\n\nWhat technical documentation and information must a provider of a '
    'general-purpose AI model draw up and make available to downstream providers?'
)
LEAK_WAIT = (
    'Which cloud service provider should a deployer or provider choose to host data within the '
    'European Union?\n\nWait, that adds actors the user did not mention. Correcting to stay '
    'faithful:\n\nWhich cloud computing service provider should be selected to host data within '
    'the European Union?'
)
LEAK_NOTE = (
    'Before deploying a high-risk AI system in the workplace, must the deployer inform the '
    'workers\' representatives and the affected employees?\n\nNote: I\'ve kept the question\'s '
    'meaning, but "workers\' representatives" adds an actor the user did not mention, so here is '
    'the corrected version:\n\nBefore putting into service a high-risk AI system in the workplace, '
    'must the deployer inform the affected workers?'
)
LEAK_CV = (
    'The user asks in French about obligations of a deployer using AI software to screen CVs. '
    'Only one sentence, no article numbers, no answer.\n\n'
    'What obligations does a deployer of a high-risk AI system used for recruitment have under the EU AI Act?'
)

tests = [
    ("une ligne propre : inchangée",
     lambda: clean_rewrite("Which AI practices are prohibited?", FALLBACK) == "Which AI practices are prohibited?"),
    ("espaces autour : retirés",
     lambda: clean_rewrite("  Which AI practices are prohibited?\n", FALLBACK) == "Which AI practices are prohibited?"),
    ("fuite « Rewritten question: » → dernière ligne",
     lambda: clean_rewrite(LEAK_DOCS, FALLBACK).startswith("What technical documentation")),
    ("fuite « Wait, that adds... » → dernière ligne",
     lambda: clean_rewrite(LEAK_WAIT, FALLBACK) == "Which cloud computing service provider should be selected to host data within the European Union?"),
    ("fuite « Note: I've kept... » → dernière ligne",
     lambda: clean_rewrite(LEAK_NOTE, FALLBACK).startswith("Before putting into service")),
    ("fuite CV → dernière ligne",
     lambda: clean_rewrite(LEAK_CV, FALLBACK).startswith("What obligations does a deployer")),
    ("plusieurs lignes sans aucune question → question d'origine",
     lambda: clean_rewrite("Here is my reasoning.\n\nThe answer is yes.", FALLBACK) == FALLBACK),
    ("réponse vide → question d'origine",
     lambda: clean_rewrite("  \n ", FALLBACK) == FALLBACK),
    ("point d'interrogation arabe reconnu",
     lambda: clean_rewrite("Note.\n\nما هي الممارسات المحظورة؟", FALLBACK) == "ما هي الممارسات المحظورة؟"),
    ("rewrite_v2 est resté identique (son cache reste valable)",
     lambda: "Regulation (EU) 2024/1689" in PROMPTS["rewrite_v2"]),
    ("rewrite_v3 abandonné : plus dans PROMPTS",
     lambda: "rewrite_v3" not in PROMPTS and "rewrite_v2" in CLEANED_MODES),
    ("numéro du règlement : remplacé par « the AI Act »",
     lambda: strip_regulation_number("Which practices are prohibited under Regulation (EU) 2024/1689?")
     == "Which practices are prohibited under the AI Act?"),
    ("numéro du règlement : « the Regulation (EU) ... » sans doublon",
     lambda: strip_regulation_number("Does the Regulation (EU) 2024/1689 apply?") == "Does the AI Act apply?"),
    ("numéro absent : texte inchangé",
     lambda: strip_regulation_number("When do the prohibitions of this Regulation apply?")
     == "When do the prohibitions of this Regulation apply?"),
    ("nettoyage complet (fuite + numéro) via _finish",
     lambda: _finish("rewrite_v2", "Draft.\n\nWhat is banned under Regulation (EU) 2024/1689?", FALLBACK)
     == "What is banned under the AI Act?"),
    ("autres modes (translate, rewrite) : non touchés",
     lambda: _finish("translate", "  Line one.\nLine two  ", FALLBACK) == "Line one.\nLine two"),
]

passed = 0
for name, test in tests:
    try:
        ok = test()
    except Exception as e:
        ok, name = False, f"{name}  (erreur : {type(e).__name__}: {e})"
    passed += ok
    print(("✅ " if ok else "❌ ") + name)

print(f"\n{passed}/{len(tests)} tests réussis")
