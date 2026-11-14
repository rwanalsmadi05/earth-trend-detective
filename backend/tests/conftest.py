"""Tests never call a real LLM and never read/write the on-disk plan or explanation caches.

The guard is SESSION-scoped (module/session fixtures such as the Azraq case run before any function-scoped patch,
so a function-scoped guard would let them reach the real Gemini API or a cached live plan). Individual tests inject
their own fake with their own monkeypatch, which overrides this one and is undone after the test."""
import pytest
from _pytest.monkeypatch import MonkeyPatch

from app import explain, llm, planner


def _real_llm_forbidden(*args, **kwargs):
    raise AssertionError("tests must not call the real LLM; inject a fake with monkeypatch")


@pytest.fixture(scope="session", autouse=True)
def _no_real_llm_ever():
    mp = MonkeyPatch()
    mp.setattr(llm, "available", lambda: False)
    mp.setattr(llm, "generate_json", _real_llm_forbidden)
    mp.setattr(planner, "CACHE_ON", False)
    mp.setattr(explain, "CACHE_ON", False)
    yield
    mp.undo()
