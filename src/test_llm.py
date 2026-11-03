"""Vérifie que la clé fonctionne et que le LLM répond (5 secondes, coût nul avec Groq).

    python src/test_llm.py
"""
from llm import PROVIDER, PROVIDERS, chat

print(f"Fournisseur : {PROVIDER} — modèle : {PROVIDERS[PROVIDER]['model']}\n")

answer = chat(
    system="You are a helpful assistant. Answer in the same language as the question, in one sentence.",
    user="ما هي عاصمة الجزائر؟",
)
print(f"Réponse : {answer}")
