"""Step 2 - HTTP API over the existing engine (FastAPI). Same behaviour as app.py, no engine change.

    GET  /health      200 only once the model and the index are loaded (503 before)
    POST /ask         one question -> sourced answer, or the refusal
    POST /risk        questionnaire answers -> risk level (same tree as tab 2 of app.py)
    GET  /deadlines   verified dates table (same content as tab 3 of app.py)

Run from the project root (engine paths are relative: data/index, data/processed):
    uvicorn api:app

Environment variables (same names and defaults as app.py where they exist):
    LIMIT_PER_VISITOR=10   questions per visitor (IP) and per day
    LIMIT_PER_DAY=300      questions per day for the whole API
    MAX_QUESTION_CHARS=1000
    MAX_CONCURRENT=2       simultaneous engine calls (like Gradio's default_concurrency_limit=2)
    CORS_ORIGINS=          comma-separated origins; empty = no CORS; "*" = any origin

The few "glue" pieces below (quota counting, the 2b guard of the risk questionnaire, the English
notes of tab 2) mirror app.py, which cannot be imported without building the whole Gradio UI.
Keep the two aligned.
"""
import logging
import os
import sys
import threading
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from typing import Literal, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))  # answer, risk, dates, retrieve

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, create_model

from answer import answer
from dates import DATES, status
from retrieve import warm_up
from risk import ANNEX_III_AREAS, EXCEPTIONS, explain

log = logging.getLogger("g1-api")

LIMIT_MESSAGE = ("Daily limit reached for this free demo. Please come back tomorrow, "
                 "or contact me for a full version.")
UNAVAILABLE_MESSAGE = "The service is temporarily unavailable. Please try again in a few minutes."
RISK_DISCLAIMER = "This is an orientation tool, not legal advice."
DATES_NOTE = ("Each date is checked against the exact text of Articles 111 and 113 "
              "(consolidated version after the Digital Omnibus).")

AreaKey = Literal[tuple(ANNEX_III_AREAS)]     # "1".."8"
ExceptionKey = Literal[tuple(EXCEPTIONS)]     # "a".."d"


def today():
    """Separate function so tests can change the day."""
    return date.today()


class RiskAnswers(BaseModel):
    """Same questions as tab 2. Unasked questions mean "no" / "none"."""
    prohibited: bool = False
    annex_i_product: bool = False
    third_party_assessment: bool = False
    annex_iii_area: Optional[AreaKey] = None
    profiling: bool = False
    exception: Optional[ExceptionKey] = None


def visitor_ip(request: Request):
    """First address of x-forwarded-for (the server sits behind a proxy), like app.py."""
    forwarded = request.headers.get("x-forwarded-for", "")
    ip = forwarded.split(",")[0].strip()
    return ip or (request.client.host if request.client else "unknown")


def create_app():
    per_visitor = int(os.getenv("LIMIT_PER_VISITOR", "10"))
    per_day = int(os.getenv("LIMIT_PER_DAY", "300"))
    max_chars = int(os.getenv("MAX_QUESTION_CHARS", "1000"))
    max_concurrent = int(os.getenv("MAX_CONCURRENT", "2"))
    origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]

    AskBody = create_model(
        "AskBody",
        __config__=ConfigDict(str_strip_whitespace=True),
        question=(str, Field(min_length=1, max_length=max_chars)),
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Load the model ONCE, in the background: the port opens at once and /health tells the truth.
        def load():
            try:
                warm_up()
                app.state.status = "ready"
            except Exception:
                log.exception("[startup] model/index loading failed")
                app.state.status = "error"
            finally:
                app.state.loaded.set()

        threading.Thread(target=load, name="warm-up", daemon=True).start()
        yield

    app = FastAPI(title="EU AI Act Assistant API", lifespan=lifespan)
    app.state.status = "loading"            # loading -> ready | error
    app.state.loaded = threading.Event()    # set when loading is over (success or failure)
    usage = {"day": None, "total": 0, "by_ip": {}}
    usage_lock = threading.Lock()           # routes run in a thread pool: protect the counters
    engine_slots = threading.BoundedSemaphore(max_concurrent)

    if origins:
        app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=False,
                           allow_methods=["GET", "POST"], allow_headers=["Content-Type"])

    def allowed(ip):
        """True if this visitor may still ask today (and counts the question), like app.py."""
        with usage_lock:
            day = today()
            if usage["day"] != day:
                usage.update(day=day, total=0, by_ip={})
            if usage["total"] >= per_day or usage["by_ip"].get(ip, 0) >= per_visitor:
                return False
            usage["total"] += 1
            usage["by_ip"][ip] = usage["by_ip"].get(ip, 0) + 1
            return True

    @app.get("/health")
    def health():
        st = app.state.status
        return JSONResponse({"status": "ok" if st == "ready" else st}, status_code=200 if st == "ready" else 503)

    @app.post("/ask")
    def ask(body: AskBody, request: Request):
        if app.state.status != "ready":
            return JSONResponse({"detail": UNAVAILABLE_MESSAGE}, status_code=503)
        if not allowed(visitor_ip(request)):
            return JSONResponse({"detail": LIMIT_MESSAGE}, status_code=429)
        try:
            with engine_slots:
                r = answer(body.question)
        except Exception as e:  # quota, network...: never a Python trace in the response
            log.error("[ask] %s: %s", type(e).__name__, e)
            return JSONResponse({"detail": UNAVAILABLE_MESSAGE}, status_code=503)

        # Only the cited sources, with the exact text of the law (like the "Verify" accordion).
        by_tag = {s["tag"]: s for s in r["sources"]}
        sources = []
        for n, legal_id in zip(r.get("used", []), r.get("cited", [])):
            s = by_tag.get(f"S{n}")
            if s:
                sources.append({"tag": s["tag"], "legal_id": legal_id, "label": s["label"], "text": s["text"]})
        return {
            "question": r["question"], "lang": r["lang"],
            "refused": r["refused"], "format_error": bool(r.get("format_error")),
            "answer": r["answer"], "disclaimer": r["disclaimer"],
            "sources": sources,
            "checks": {"invalid_tags": r["invalid_tags"], "phantom_refs": r["phantom_refs"],
                       "mismatched": r["mismatched"]},
        }

    @app.post("/risk")
    def risk(body: RiskAnswers):
        answers = {
            "prohibited": body.prohibited,
            "annex_i_product": body.annex_i_product,
            # 2b only makes sense if 2a = yes (same guard as app.check_risk)
            "third_party_assessment": body.annex_i_product and body.third_party_assessment,
            "annex_iii_area": body.annex_iii_area,
            "profiling": body.profiling,
            "exception": body.exception,
        }
        r = explain(answers)
        notes = []
        if r["route"] == "art6_3_exception":
            notes.append("The provider must document this assessment before placing the system on the market (Art. 6(4)).")
        if answers["annex_iii_area"]:
            notes.append("Some Annex III points contain their own exclusions (e.g. point 5: AI used to detect "
                         "financial fraud). Check the exact wording of the point.")
        notes.append("Whatever the verdict, transparency obligations (Art. 50) may apply, e.g. to chatbots "
                     "or AI-generated content.")
        return {
            "verdict": r["verdict"], "route": r["route"],
            "basis": r["basis"].replace("Annexe", "Annex"),   # risk.py writes French; the API is English
            "applies": r["applies"].isoformat() if r["applies"] else None,
            "notes": notes, "disclaimer": RISK_DISCLAIMER,
        }

    @app.get("/deadlines")
    def deadlines(on: Optional[date] = None):
        on = on or today()   # recomputed at every call, never frozen at server start

        def row(e):
            return {"key": e["key"], "applies": e["applies"].isoformat(), "label": e["label"], "chunk": e["chunk"]}

        applied, pending = status(on)
        return {"on": on.isoformat(), "applied": [row(e) for e in applied],
                "pending": [row(e) for e in pending], "note": DATES_NOTE}

    return app


app = create_app()
