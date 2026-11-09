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

## What it does

Ask a question about the EU AI Act in English, French or Arabic and get a short answer that cites the
exact articles it relies on, with the legal text one click away. When the retrieved text does not
answer the question, the assistant says so instead of guessing. Two rule-based tools complete it: a
risk-level questionnaire (Articles 5 and 6) and a table of application dates.

**Live demo:** https://huggingface.co/spaces/Aymenfou2003/eu-ai-act-assistant

## How it works

The app has three tabs.

### 1. Ask: retrieval-augmented answers with citation checks

```
question (EN / FR / AR)
   │
   ▼
query rewrite (Claude Haiku): translated to English, phrased with the AI Act's own terms;
   │                          leaked drafts and the regulation number are cleaned out in code
   ▼
BGE-M3 embeddings + ChromaDB: 50 nearest chunks
   │   (official EN + FR texts, one chunk per point or paragraph, with its article header)
   ▼
diversity: 10 distinct provisions, at most 2 per article or annex
   + siblings: if the 2 best chunks are points of the same list (e.g. Art. 5(1)),
     the other points of that list are added after the 10 sources
   │
   ▼
Claude Haiku: instructed to answer only from the numbered sources and tag each sentence [S..],
   │          or to refuse
   │
   ▼
citation check (code, no AI): invalid tags, provisions named but not in the sources,
                              provisions named under the wrong source tag
```

The cited legal text is shown under the answer, in the user's language: the official French text for
French questions, and the English text for Arabic questions (there is no official Arabic version).

### 2. My risk level: a coded decision tree, not the LLM

`src/risk.py` follows Articles 5 and 6 step by step: prohibited practice → safety component of an
Annex I product → Annex III area → profiling → Article 6(3) exceptions. It returns the verdict, the
legal basis and the date the obligations apply. Covered by 12 unit tests (`src/test_risk.py`).

### 3. Deadlines: dates verified against Articles 111 and 113

11 application dates after the Digital Omnibus (Regulation (EU) 2026/1744). Each date is linked to the
exact chunk of Article 111 or 113 that sets it, and `python src/dates.py` checks that the date is
written in that chunk, in English and in French (22/22 checks). Dates are a fact, so they are not left
to retrieval.

## Evaluation

For every question, the expected provisions were identified by hand in the law text
(`data/processed/chunks.json`), never with the search system. **Correct provision cited** means the
answer cites at least one expected provision. **Invented citation** means an invalid source tag or a
provision that is not among the sources. Off-topic questions (GDPR, tax, civil liability…) must be refused.

**Tuning set**: 26 questions × 3 languages = 78 runs (16 answerable questions → 48 runs, 10 off-topic
questions → 30 runs). Used to choose every setting. Results: `data/eval/results_answers_claude-haiku-5-5_v3.json`,
commit `4d39393`.

| Metric | Result |
|---|---|
| Correct provision cited | **91.7 %** (44/48): EN 15/16, FR 14/16, AR 15/16 |
| Expected provision present in the 10 sources | 44/48 |
| Off-topic runs refused | **30/30** (10 questions) |
| Answerable runs wrongly refused | 1/48 |
| Invented citations | **0** |
| Citations attributed to the wrong source | 0 |
| Answers with a sentence without a source tag | 3/47 |
| Invalid JSON output | 1/78 |

**Held-out set**: 15 new questions × 3 languages = 45 runs (13 answerable questions → 39 runs, 2 off-topic
questions → 6 runs), written after tuning and **evaluated once, on 9 November 2026, with no change
afterwards**. Results: `data/eval/results_answers_claude-haiku-5-5_v3_heldout.json`, commit `d18e04b`.

| Metric | Result |
|---|---|
| Correct provision cited | **84.6 %** (33/39): 11/13 in each language |
| Expected provision present in the 10 sources | 33/39 (all 6 misses are retrieval misses, on 2 questions) |
| Off-topic runs refused | **3/6** (only 2 questions; the civil-liability question was answered in all 3 languages) |
| Answerable runs wrongly refused | 3/39 (all on the 2 questions whose source was not retrieved) |
| Invented citations | **0** |
| Citations attributed to the wrong source | 1 |
| Answers with a sentence without a source tag | 7/39 |
| Invalid JSON output | 3/45 |

**Why the held-out figure is the reference.** Every setting (query prompt, diversity rule, list
completion, answer prompt) was chosen by looking at the tuning set, so its scores are optimistic. The
held-out questions were never seen during tuning and were scored once, so 84.6 % is the better estimate
for new questions, keeping in mind that it rests on only 13 questions.

Retrieval alone (expected provision in the 10 sources): 44/48 on the tuning set (commit `ce87d52`),
33/39 on the held-out set (commit `d18e04b`).

## Known limitations

- **Lists spread over several areas.** List completion adds the other points of *one* list (all of
  Article 5(1)), not a list spread over several areas. "Which areas are high-risk?" (held-out h13) got only
  1 to 2 of the 8 Annex III areas in its sources.
- **Dates tied to a specific case.** Retrieval can find the rule but miss the article that dates it
  (held-out h12: Article 6(1) found, Article 113(c) not). For dates, use the **3. Deadlines** tab, whose
  dates are verified.
- **Off-topic refusal is less reliable when the topic is close to the AI Act.** Civil liability
  (held-out h15) was answered with loosely related articles instead of being refused.
- **Exclusions written inside Annex III points are not handled by the risk tree** (e.g. point 5(b)
  excludes AI used to detect financial fraud). The tab shows a warning and points to the **1. Ask** tab.
- **Arabic.** There is no official Arabic text: Arabic questions get an Arabic answer, but the cited
  sources are the English text.
- **Small samples.** Both evaluations rest on a few dozen runs; one question more or less moves a
  score by several points.

## Tech stack

- Python 3.12 (Space), Gradio 6.31, hosted on Hugging Face Spaces (CPU basic)
- Embeddings: BGE-M3 via `sentence-transformers` 6.2; vector store: ChromaDB 1.5.9
- LLM: Claude Haiku 5.5 via the `anthropic` SDK 2.4.0 (Groq `gpt-oss-120b` also supported through `LLM_PROVIDER`)
- `torch`, `transformers`, `python-dotenv`; exact versions in `requirements.txt`

## How to run locally

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows  (macOS / Linux: source .venv/bin/activate)
pip install -r requirements.txt gradio==6.31.0
```

`gradio` is not in `requirements.txt` because Hugging Face installs it from `sdk_version` above.
Copy `.env.example` to `.env` at the project root and add your key (`.env` is in `.gitignore`, never
commit it). The variables:

```
ANTHROPIC_API_KEY=your-key
LLM_PROVIDER=anthropic          # or groq, with GROQ_API_KEY=your-key
REWRITE_CACHE=0                 # 0 = do not store visitors' questions; leave it unset for evaluations
LIMIT_PER_VISITOR=10            # optional: questions per visitor per day
LIMIT_PER_DAY=300               # optional: questions per day for the whole site
```

Build the vector index once (`data/index/` is not in git; 10 to 30 minutes on a CPU, and the first run
downloads BGE-M3), then start the app:

```bash
python src/build_index.py
python app.py                     # then open http://127.0.0.1:7860
```

The chunks are already in `data/processed/chunks.json`; run `python src/chunk_ai_act.py` only if the
source text in `data/raw/` changes.

**Reproduce the evaluation** (LLM answers are cached in `data/eval/`, so reruns reuse them):

```bash
python src/evaluate_rewrite.py --strategies rewrite_v2 --expand
python src/evaluate_answers.py --prompt v3
python src/evaluate_answers.py --prompt v3 --questions data/eval/heldout_questions.json
```

Unit tests: `python src/test_evaluate.py`, `test_diversity.py`, `test_query_rewrite.py`,
`test_retrieve.py`, `test_risk.py` (all in `src/`).

## Disclaimer

This is an orientation tool, **not legal advice**. It is based on the consolidated text of
Regulation (EU) 2024/1689 as of **27 July 2026** (after the Digital Omnibus). Always check the
official text in the Official Journal of the European Union before acting.

## Author

Built by Aymen Fouatih, freelance GenAI engineer (RAG, evaluation, AI product).
Contact: [LinkedIn](https://www.linkedin.com/in/aymen-ahmed-fouatih-5790b242a/)
