---
title: EU AI Act Assistant
emoji: ⚖️
colorFrom: indigo
colorTo: gray
sdk: gradio
sdk_version: 6.31.0
python_version: "3.12"
app_file: app.py
pinned: false
short_description: Multilingual EU AI Act assistant citing the exact article
---

# EU AI Act Assistant

Ask questions about the EU AI Act in English, French or Arabic. Every answer cites the exact
article and shows the legal text; when the text is silent, the assistant says so.

- **Ask the AI Act**: retrieval-augmented answers (BGE-M3 + ChromaDB + Claude Haiku), with citation checks.
- **Is it high-risk?**: a rule-based decision tree (Articles 5 and 6), covered by unit tests.
- **Key dates**: application dates after the Digital Omnibus, each one verified against Articles 111 and 113.

Based on the consolidated text of 27 July 2026. Orientation tool, not legal advice.
