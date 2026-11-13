"""Tests of api.py. No network, no model, no paid call: warm_up() and answer() are faked.

    python -m pytest tests/test_api.py -q      (from the project root)
"""
import itertools
import sys
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import api  # noqa: E402  (also puts src/ on sys.path)
from dates import DATES, status  # noqa: E402
from risk import ANNEX_III_AREAS, EXCEPTIONS, explain  # noqa: E402


# ------------------------------------------------------------------ helpers

class Calls:
    def __init__(self):
        self.warm = 0
        self.ask = []


@pytest.fixture
def calls(monkeypatch):
    c = Calls()

    def fake_warm_up():
        c.warm += 1

    def fake_answer(question):
        c.ask.append(question)
        if question.startswith("refuse"):
            return fake_result(question, refused=True)
        return fake_result(question)

    monkeypatch.setattr(api, "warm_up", fake_warm_up)
    monkeypatch.setattr(api, "answer", fake_answer)
    return c


def fake_result(question, refused=False):
    sources = [{"tag": f"S{n}", "id": f"en-art{n}", "label": f"Article {n}", "text": f"Exact text {n}"}
               for n in (1, 2, 3)]
    if refused:
        return {"question": question, "lang": "en", "rewritten": "x", "refused": True,
                "answer": "The text of the AI Act provided does not answer this question.",
                "format_error": False, "sources": sources, "cited": [], "used": [],
                "invalid_tags": [], "phantom_refs": [], "mismatched": [], "disclaimer": "not legal advice"}
    return {"question": question, "lang": "en", "rewritten": "x", "refused": False,
            "answer": "Yes [S2].", "format_error": False, "sources": sources,
            "cited": ["art2"], "used": [2],
            "invalid_tags": [], "phantom_refs": [], "mismatched": [], "disclaimer": "not legal advice"}


@pytest.fixture(autouse=True)
def behind_proxy(monkeypatch):
    """Tests simulate visitors with x-forwarded-for, as behind Caddy."""
    monkeypatch.setenv("BEHIND_PROXY", "1")


def ready_client(**env_unused):
    """A started app whose loading is over. Use as: with ready_client() as client."""
    app = api.create_app()
    client = TestClient(app, headers={"x-forwarded-for": "1.1.1.1"})

    class Ctx:
        def __enter__(self):
            client.__enter__()
            assert app.state.loaded.wait(5)
            return client

        def __exit__(self, *a):
            client.__exit__(*a)

    return Ctx()


# ------------------------------------------------------------------ /health

def test_health_503_before_startup(calls):
    client = TestClient(api.create_app())  # no `with` -> lifespan not started
    r = client.get("/health")
    assert r.status_code == 503 and r.json() == {"status": "loading"}


def test_health_ok_once_loaded_and_warm_up_called_once(calls):
    with ready_client() as client:
        for _ in range(3):
            assert client.get("/health").json() == {"status": "ok"}
    assert calls.warm == 1


def test_health_error_when_loading_fails(monkeypatch):
    def boom():
        raise RuntimeError("no index")

    monkeypatch.setattr(api, "warm_up", boom)
    app = api.create_app()
    with TestClient(app) as client:
        assert app.state.loaded.wait(5)
        r = client.get("/health")
        assert r.status_code == 503 and r.json() == {"status": "error"}
        assert client.post("/ask", json={"question": "hi"}).status_code == 503


# ------------------------------------------------------------------ /ask

def test_ask_returns_answer_and_only_cited_sources(calls):
    with ready_client() as client:
        r = client.post("/ask", json={"question": "Is CV screening high-risk?"})
    assert r.status_code == 200
    body = r.json()
    assert body["refused"] is False and body["answer"] == "Yes [S2]."
    assert body["sources"] == [{"tag": "S2", "legal_id": "art2", "label": "Article 2", "text": "Exact text 2"}]
    assert body["checks"] == {"invalid_tags": [], "phantom_refs": [], "mismatched": []}
    assert body["disclaimer"] and body["lang"] == "en"


def test_ask_refusal_has_no_sources(calls):
    with ready_client() as client:
        body = client.post("/ask", json={"question": "refuse me"}).json()
    assert body["refused"] is True and body["sources"] == []


@pytest.mark.parametrize("q", ["", "   ", "\n\t"])
def test_ask_empty_question_422(calls, q):
    with ready_client() as client:
        assert client.post("/ask", json={"question": q}).status_code == 422
    assert calls.ask == []


def test_ask_length_limit(calls):
    with ready_client() as client:
        assert client.post("/ask", json={"question": "a" * 1000}).status_code == 200
        assert client.post("/ask", json={"question": "a" * 1001}).status_code == 422
        assert client.post("/ask", json={"question": "  " + "a" * 1000 + "  "}).status_code == 200  # stripped


def test_ask_length_limit_from_env(calls, monkeypatch):
    monkeypatch.setenv("MAX_QUESTION_CHARS", "20")
    with ready_client() as client:
        assert client.post("/ask", json={"question": "a" * 20}).status_code == 200
        assert client.post("/ask", json={"question": "a" * 21}).status_code == 422


def test_ask_missing_field_422(calls):
    with ready_client() as client:
        assert client.post("/ask", json={}).status_code == 422


def test_ask_503_before_ready(calls):
    client = TestClient(api.create_app())
    assert client.post("/ask", json={"question": "hi"}).status_code == 503
    assert calls.ask == []


def test_ask_engine_error_503_without_trace(monkeypatch, calls):
    def boom(question):
        raise RuntimeError("secret internal detail")

    monkeypatch.setattr(api, "answer", boom)
    with ready_client() as client:
        r = client.post("/ask", json={"question": "hi"})
    assert r.status_code == 503
    assert "secret" not in r.text and "Traceback" not in r.text
    assert r.json()["detail"] == api.UNAVAILABLE_MESSAGE


def test_ask_per_visitor_limit(calls):
    with ready_client() as client:
        for _ in range(10):
            assert client.post("/ask", json={"question": "hi"}).status_code == 200
        assert client.post("/ask", json={"question": "hi"}).status_code == 429
        # another visitor is not affected
        other = client.post("/ask", json={"question": "hi"}, headers={"x-forwarded-for": "2.2.2.2, 9.9.9.9"})
        assert other.status_code == 200
    assert len(calls.ask) == 11   # the refused one never reached the engine


def test_ip_from_proxy_header(calls, monkeypatch):
    """Behind the proxy: last entry (added by Caddy); forged leading entries are ignored."""
    monkeypatch.setenv("LIMIT_PER_VISITOR", "1")
    with ready_client() as client:
        ok = lambda h: client.post("/ask", json={"question": "hi"}, headers=h).status_code
        assert ok({"x-forwarded-for": "5.5.5.5"}) == 200
        assert ok({"x-forwarded-for": "5.5.5.5"}) == 429
        # forged first entry changes nothing: still visitor 5.5.5.5
        assert ok({"x-forwarded-for": "6.6.6.6, 5.5.5.5"}) == 429
        # a different real (last) address is a different visitor
        assert ok({"x-forwarded-for": "5.5.5.5, 7.7.7.7"}) == 200


def test_ip_without_header_uses_client_host(calls, monkeypatch):
    monkeypatch.setenv("LIMIT_PER_VISITOR", "1")
    with api_client_no_header() as client:
        assert client.post("/ask", json={"question": "hi"}).status_code == 200
        assert client.post("/ask", json={"question": "hi"}).status_code == 429


def test_ip_header_ignored_without_proxy(calls, monkeypatch):
    """API exposed directly (no BEHIND_PROXY): a forged header must not bypass the limit."""
    monkeypatch.delenv("BEHIND_PROXY")
    monkeypatch.setenv("LIMIT_PER_VISITOR", "1")
    with api_client_no_header() as client:
        assert client.post("/ask", json={"question": "hi"}, headers={"x-forwarded-for": "8.8.8.1"}).status_code == 200
        assert client.post("/ask", json={"question": "hi"}, headers={"x-forwarded-for": "8.8.8.2"}).status_code == 429


def api_client_no_header():
    """A client without the default x-forwarded-for header, loading already finished."""
    app = api.create_app()
    client = TestClient(app)
    ctx = ready_wait(app, client)
    return ctx


class ready_wait:
    def __init__(self, app, client):
        self.app, self.client = app, client

    def __enter__(self):
        self.client.__enter__()
        assert self.app.state.loaded.wait(5)
        return self.client

    def __exit__(self, *a):
        self.client.__exit__(*a)


def test_ask_global_limit(calls, monkeypatch):
    monkeypatch.setenv("LIMIT_PER_DAY", "3")
    with ready_client() as client:
        for i in range(3):
            assert client.post("/ask", json={"question": "hi"}, headers={"x-forwarded-for": f"3.3.3.{i}"}).status_code == 200
        r = client.post("/ask", json={"question": "hi"}, headers={"x-forwarded-for": "4.4.4.4"})
    assert r.status_code == 429 and r.json()["detail"] == api.LIMIT_MESSAGE


def test_ask_limits_reset_next_day(calls, monkeypatch):
    monkeypatch.setenv("LIMIT_PER_VISITOR", "2")
    day = {"d": date(2026, 11, 11)}
    monkeypatch.setattr(api, "today", lambda: day["d"])
    with ready_client() as client:
        assert [client.post("/ask", json={"question": "hi"}).status_code for _ in range(3)] == [200, 200, 429]
        day["d"] = date(2026, 11, 12)
        assert client.post("/ask", json={"question": "hi"}).status_code == 200


def test_invalid_question_does_not_use_quota(calls, monkeypatch):
    monkeypatch.setenv("LIMIT_PER_VISITOR", "1")
    with ready_client() as client:
        assert client.post("/ask", json={"question": ""}).status_code == 422
        assert client.post("/ask", json={"question": "hi"}).status_code == 200


def test_unready_engine_does_not_use_quota(calls, monkeypatch):
    monkeypatch.setenv("LIMIT_PER_VISITOR", "1")
    app = api.create_app()
    client = TestClient(app)
    assert client.post("/ask", json={"question": "hi"}).status_code == 503
    with client:
        assert app.state.loaded.wait(5)
        assert client.post("/ask", json={"question": "hi"}).status_code == 200


# ------------------------------------------------------------------ /risk

def guarded(a):
    """What tab 2 (app.check_risk) feeds to explain()."""
    return {**a, "third_party_assessment": a["annex_i_product"] and a["third_party_assessment"]}


def test_risk_same_tree_as_tab2_for_every_combination(calls):
    bools = [False, True]
    areas = [None, *ANNEX_III_AREAS]
    exceptions = [None, *EXCEPTIONS]
    with ready_client() as client:
        for pro, a1, a2, area, prof, exc in itertools.product(bools, bools, bools, areas, bools, exceptions):
            payload = {"prohibited": pro, "annex_i_product": a1, "third_party_assessment": a2,
                       "annex_iii_area": area, "profiling": prof, "exception": exc}
            r = client.post("/risk", json=payload)
            assert r.status_code == 200, payload
            want = explain(guarded(payload))
            got = r.json()
            assert (got["verdict"], got["route"]) == (want["verdict"], want["route"]), payload
            assert got["applies"] == (want["applies"].isoformat() if want["applies"] else None), payload
            assert got["basis"] == want["basis"].replace("Annexe", "Annex"), payload


def test_risk_defaults_mean_no(calls):
    with ready_client() as client:
        got = client.post("/risk", json={}).json()
    assert (got["verdict"], got["route"]) == ("not_high_risk", "none")
    assert got["applies"] is None and "not legal advice" in got["disclaimer"]


def test_risk_third_party_ignored_without_annex_i(calls):
    with ready_client() as client:
        got = client.post("/risk", json={"third_party_assessment": True}).json()
    assert got["route"] == "none"


def test_risk_annex_wording_and_notes(calls):
    with ready_client() as client:
        high = client.post("/risk", json={"annex_iii_area": "4"}).json()
        exc = client.post("/risk", json={"annex_iii_area": "4", "exception": "a"}).json()
    assert high["verdict"] == "high_risk" and "Annexe" not in high["basis"] and "Annex III" in high["basis"]
    assert high["applies"] == "2027-12-02"
    assert any("Annex III points contain their own exclusions" in n for n in high["notes"])
    assert not any("Art. 6(4)" in n for n in high["notes"])
    assert exc["route"] == "art6_3_exception" and any("Art. 6(4)" in n for n in exc["notes"])
    assert any("Art. 50" in n for n in exc["notes"])


@pytest.mark.parametrize("payload", [{"annex_iii_area": "9"}, {"annex_iii_area": "0"}, {"exception": "e"},
                                     {"prohibited": "maybe"}])
def test_risk_invalid_values_422(calls, payload):
    with ready_client() as client:
        assert client.post("/risk", json=payload).status_code == 422


# ------------------------------------------------------------------ /deadlines

def test_deadlines_match_dates_status(calls):
    on = date(2027, 1, 15)
    applied, pending = status(on)
    with ready_client() as client:
        r = client.get("/deadlines", params={"on": "2027-01-15"})
    body = r.json()
    assert r.status_code == 200 and body["on"] == "2027-01-15"
    assert [e["key"] for e in body["applied"]] == [e["key"] for e in applied]
    assert [e["key"] for e in body["pending"]] == [e["key"] for e in pending]
    assert len(body["applied"]) + len(body["pending"]) == len(DATES)
    first = body["applied"][0]
    assert set(first) == {"key", "applies", "label", "chunk"} and set(first["label"]) == {"en", "fr", "ar"}
    assert "Articles 111 and 113" in body["note"]


def test_deadlines_default_is_today(calls, monkeypatch):
    monkeypatch.setattr(api, "today", lambda: date(2026, 11, 11))
    with ready_client() as client:
        assert client.get("/deadlines").json()["on"] == "2026-11-11"
        monkeypatch.setattr(api, "today", lambda: date(2026, 11, 12))
        assert client.get("/deadlines").json()["on"] == "2026-11-12"   # not frozen at startup


@pytest.mark.parametrize("bad", ["2027-13-45", "tomorrow", "15/01/2027"])
def test_deadlines_invalid_date_422(calls, bad):
    with ready_client() as client:
        assert client.get("/deadlines", params={"on": bad}).status_code == 422


# ------------------------------------------------------------------ CORS

def test_cors_allows_only_configured_origin(calls, monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "https://a.example, https://b.example")
    with ready_client() as client:
        ok = client.get("/deadlines", headers={"origin": "https://a.example"})
        no = client.get("/deadlines", headers={"origin": "https://evil.example"})
    assert ok.headers["access-control-allow-origin"] == "https://a.example"
    assert "access-control-allow-origin" not in no.headers


def test_cors_preflight(calls, monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "https://a.example")
    with ready_client() as client:
        r = client.options("/ask", headers={"origin": "https://a.example",
                                            "access-control-request-method": "POST",
                                            "access-control-request-headers": "content-type"})
    assert r.status_code == 200 and r.headers["access-control-allow-origin"] == "https://a.example"


def test_cors_off_by_default(calls, monkeypatch):
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    with ready_client() as client:
        r = client.get("/deadlines", headers={"origin": "https://a.example"})
    assert "access-control-allow-origin" not in r.headers
