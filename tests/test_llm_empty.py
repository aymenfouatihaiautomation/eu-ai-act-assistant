"""max_tokens exhausted with no text must end as format_error, never as an exception.
No network, no real model call: the Anthropic client and the search are faked.

    python -m pytest tests/test_llm_empty.py -q      (from the project root)
"""
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import anthropic  # noqa: E402
import answer as answer_mod  # noqa: E402
import llm  # noqa: E402


def fake_client_factory(stop_reason):
    """Anthropic() whose reply holds only a thinking block (no text)."""
    class FakeMessages:
        def create(self, **kwargs):
            return SimpleNamespace(content=[SimpleNamespace(type="thinking")],
                                   stop_reason=stop_reason)

    class FakeClient:
        def __init__(self, *args, **kwargs):
            self.messages = FakeMessages()

    return FakeClient


def test_chat_returns_empty_text_on_max_tokens(monkeypatch):
    monkeypatch.setattr(llm, "get_key", lambda provider: "fake")
    monkeypatch.setattr(anthropic, "Anthropic", fake_client_factory("max_tokens"))
    assert llm.chat("sys", "user", provider="anthropic") == ""


def test_empty_for_another_reason_still_raises(monkeypatch):
    monkeypatch.setattr(llm, "get_key", lambda provider: "fake")
    monkeypatch.setattr(anthropic, "Anthropic", fake_client_factory("refusal"))
    try:
        llm.chat("sys", "user", provider="anthropic")
    except RuntimeError:
        return
    raise AssertionError("expected RuntimeError")


def test_answer_ends_in_format_error_message(monkeypatch):
    monkeypatch.setattr(llm, "get_key", lambda provider: "fake")
    monkeypatch.setattr(anthropic, "Anthropic", fake_client_factory("max_tokens"))
    monkeypatch.setattr(answer_mod, "chat",
                        lambda s, u, max_tokens=0: llm.chat(s, u, provider="anthropic",
                                                            max_tokens=max_tokens))
    chunks = [{"id": "x", "legal_id": "Art. 5", "label": "Art. 5", "text": "t", "meta": {}}]
    monkeypatch.setattr(answer_mod, "search", lambda q: ("q", "fr", chunks))
    r = answer_mod.answer("question ?")
    assert r["format_error"] is True
    assert r["answer"] == answer_mod.FORMAT_ERROR["fr"]
