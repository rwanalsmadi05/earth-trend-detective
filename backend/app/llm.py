"""Thin, provider-configurable LLM layer (LLM_PROVIDER / LLM_API_KEY / LLM_MODEL).

Only structured JSON comes out: callers pass a pydantic schema and get a validated instance back.
The API key is read from the environment only; it is never logged, printed or placed in an error message."""
import json
import logging
import os

log = logging.getLogger("etd.llm")

DEFAULT_MODELS = ("gemini-3.5-flash-lite", "gemini-3.1-flash-lite")  # fast tier; picked from the key's model list
TIMEOUT_S = 10   # the Gemini API rejects client deadlines below 10 s


class LLMUnavailable(Exception):
    """No provider/key configured, or provider not supported."""


class LLMError(Exception):
    """The call failed (network, quota, bad output). Message is already redacted."""


def provider() -> str:
    return os.getenv("LLM_PROVIDER", "").strip().lower()


def available() -> bool:
    return provider() == "gemini" and bool(os.getenv("LLM_API_KEY", "").strip())


def models() -> list[str]:
    first = os.getenv("LLM_MODEL", "").strip()
    return [m for i, m in enumerate([first, *DEFAULT_MODELS]) if m and m not in ([first, *DEFAULT_MODELS])[:i]]


def redact(msg: str) -> str:
    key = os.getenv("LLM_API_KEY", "")
    return msg.replace(key, "<redacted>") if key else msg


def generate_json(system: str, prompt: str, schema, temperature: float = 0.2):
    """Return (validated `schema` instance, model name). Tries each model in turn; raises LLMError/LLMUnavailable."""
    if not available():
        raise LLMUnavailable("no LLM configured (set LLM_PROVIDER=gemini and LLM_API_KEY)")
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=os.environ["LLM_API_KEY"], http_options=types.HttpOptions(timeout=TIMEOUT_S * 1000))
    last = "no model tried"
    for model in models():
        try:
            r = client.models.generate_content(
                model=model, contents=prompt,
                config=types.GenerateContentConfig(system_instruction=system, response_mime_type="application/json",
                                                   response_schema=schema, temperature=temperature))
            parsed = r.parsed if isinstance(r.parsed, schema) else schema.model_validate(json.loads(r.text))
            return parsed, model
        except Exception as e:  # noqa: BLE001
            last = redact(f"{type(e).__name__}: {str(e)[:160]}")
            log.warning("LLM call failed on %s: %s", model, last)
    raise LLMError(last)
