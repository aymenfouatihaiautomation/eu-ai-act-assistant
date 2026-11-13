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

**HTTP API:** https://api.aymenahmedfouatih.com (**coming soon**, not online yet). Endpoints: `GET /health`, `POST /ask`, `POST /risk`, `GET /deadlines`. See [Run the HTTP API](#run-the-http-api).

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
   + dates: if the rewritten question asks for a date, the Art. 111 / 113 chunks of the
     verified date table are added too
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
provision that is not among the sources. Off-topic questions (GDPR, copyright, NIS2, tax…) must be refused.

### Held-out set v2: the reference figure

16 new questions × 3 languages = 48 runs: **12 questions inside the AI Act** (36 runs, including 1 date
question and 2 Annex III questions) and **4 off-topic questions** (12 runs, 3 of them on neighbouring
regulations: NIS2, Data Act, DORA; the fourth is unrelated). It has no list-type question. The French
questions were written by the author outside Claude Code (the EN and AR versions are translations); the
expected provisions were checked in the law text, not with the search system. It was **evaluated once,
on 11 November 2026, with the code frozen at commit `ff222e3`**, and nothing was changed afterwards.
Results: `data/eval/results_answers_claude-haiku-5-5_v3_heldout_v2.json`, commit `840a3b4`.

| Metric | Result |
|---|---|
| Correct provision cited | **94.4 %** (34/36): EN 11/12, FR 11/12, AR 12/12 |
| Expected provision present in the sources sent to the model | 34/36 (both misses are retrieval misses, on one question) |
| Off-topic runs refused | **12/12** (4 questions) |
| Answerable runs wrongly refused | 1/36 |
| Invented citations | **0** |
| Citations attributed to the wrong source | **0** |
| Answers with a sentence without a source tag | 2/35 |
| Invalid JSON output | 2/48 (both in Arabic) |

**Why this is the reference figure.** Every setting (query prompt, diversity rule, list completion, date
chunks, answer prompt) was chosen by looking at the tuning set, so its scores are optimistic, whereas the
v2 questions were written separately and scored once with the code frozen. It remains an **estimate**: it
rests on 12 answerable questions, so one question more or less moves the score by about 8 points.

### Tuning set (used to choose every setting)

29 questions × 3 languages = 87 runs (16 answerable questions → 48 runs, 13 off-topic questions → 39 runs).
Results: `data/eval/results_answers_claude-haiku-5-5_v3.json`, commit `dede157`.

| Metric | Result |
|---|---|
| Correct provision cited | 47/48 |
| Off-topic runs refused | 38/39 (the miss: GDPR erasure, in Arabic) |
| Answerable runs wrongly refused | 0/48 |
| Invented citations | 0 |
| Citations attributed to the wrong source | 0 |
| Answers with a sentence without a source tag | 2/49 |
| Invalid JSON output | 0/87 |

### History: held-out v1

The first held-out set (15 questions, evaluated once on 9 November 2026, commit `d18e04b`) scored **84.6 %**
(33/39). It was run before the date correction of 10 November and uses different questions, so it is
**not comparable** with the figures above.

Retrieval alone (expected provision in the sources sent to the model): 47/48 on the tuning set (commit
`dbe80d0`), 34/36 on held-out v2 (commit `840a3b4`).

## Known limitations

- **Lists spread over several Annex III areas.** List completion adds the other points of *one* list (all
  of Article 5(1)), not a list spread over several areas. Such a question gets only 1 to 2 of the areas in
  its sources (held-out v1: "which areas are high-risk?"). For the full list of areas, use the
  **2. My risk level** tab.
- **Neighbouring regulations outside the AI Act (GDPR, copyright, NIS2…).** One failure on the tuning set:
  a GDPR erasure question in Arabic was answered with the AI Act's deletion rules for regulatory sandboxes
  and real-world tests, instead of being refused. On held-out v2, the 4 off-topic questions (3 on
  neighbouring regulations) were refused 12/12; on held-out v1, a civil-liability question was answered
  in all 3 languages.
- **A specific letter of Article 5(1) can be missing.** On held-out v2, question v02 (a toy that exploits
  children's vulnerabilities) expects Article 5(1)(b). In English and French the search ranked it 8th and
  5th among the distinct provisions of the 50 nearest chunks, but it was not among the sources sent to the
  model: the rule that keeps at most 2 chunks per article had already kept two other Article 5
  provisions, and list completion did not trigger because those two were not points of the same paragraph.
  The assistant then answered from other provisions (English) or refused (French). In Arabic the chunk was
  ranked 1st and cited. The same "2 per article" rule explains question h04 of held-out v1 (Article 5(1)(h),
  cited as Article 5(2) instead). Both cases (h04, v02) are the known target of the next version (v1.5).
- **Dates.** For a date question, the verified Article 111 and 113 chunks are added to the sources. The
  detector of date questions was tuned on the tuning set, and the citation check does not verify dates.
- **Output format.** 2/48 answers were invalid JSON (both in Arabic) and 2/35 answers contain a sentence
  without a source tag, on held-out v2.
- **Exclusions written inside Annex III points are not handled by the risk tree** (e.g. point 5(b)
  excludes AI used to detect financial fraud). The tab shows a warning and points to the **1. Ask** tab.
- **Arabic.** There is no official Arabic text: Arabic questions get an Arabic answer, but the cited
  sources are the English text.
- **Small samples.** The figures above rest on a few dozen runs: they are estimates, not guarantees.

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

**Reproduce the evaluation** (LLM answers are cached locally in `data/eval/`, so reruns reuse them; the answer cache `answer_cache.json` is not published, so a first run calls the LLM and needs your API key):

```bash
python src/evaluate_rewrite.py --strategies rewrite_v2 --expand --dates
python src/evaluate_answers.py --prompt v3
python src/evaluate_answers.py --prompt v3 --questions data/eval/heldout_v2.json
```

Unit tests: `python src/test_evaluate.py`, `test_diversity.py`, `test_dates.py`, `test_query_rewrite.py`,
`test_retrieve.py`, `test_risk.py` (all in `src/`).

## Run the HTTP API

`api.py` exposes the same engine over HTTP (FastAPI), with per-visitor and per-day limits. After building
`data/index/` (see above):

```bash
pip install -r requirements-api.txt
uvicorn api:app --host 127.0.0.1 --port 8000
curl http://127.0.0.1:8000/health
```

For deployment, the `Dockerfile` builds the image (the index is copied in, so build it first), and
`deploy/` holds `env.example`, the `Caddyfile` (HTTPS reverse proxy) and `run.md` (server setup steps).
Set `BEHIND_PROXY=1` only behind the proxy; otherwise `X-Forwarded-For` is ignored.

## Disclaimer

This is an orientation tool, **not legal advice**. It is based on the consolidated text of
Regulation (EU) 2024/1689 as of **27 July 2026** (after the Digital Omnibus). Always check the
official text in the Official Journal of the European Union before acting.

## Author

Built by Aymen Fouatih, freelance GenAI engineer (RAG, evaluation, AI product).
Contact: [LinkedIn](https://www.linkedin.com/in/aymen-ahmed-fouatih-5790b242a/)
