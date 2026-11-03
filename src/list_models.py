"""Demande à Groq la liste des modèles disponibles pour ta clé.

    python src/list_models.py

On ne devine pas un nom de modèle : on le demande au fournisseur, parce que les
fournisseurs ajoutent et retirent des modèles régulièrement.
"""
from openai import OpenAI

from llm import PROVIDERS, get_key

config = PROVIDERS["groq"]
client = OpenAI(api_key=get_key("groq"), base_url=config["base_url"])

# On ne garde que les modèles de texte (pas la transcription audio, ni les modèles de filtrage)
skip = ("whisper", "guard", "tts", "playai", "orpheus", "prompt")
models = sorted(m.id for m in client.models.list().data if not any(s in m.id.lower() for s in skip))

print("Modèles de texte disponibles chez Groq pour ta clé :\n")
for model_id in models:
    print(f"  {model_id}")
