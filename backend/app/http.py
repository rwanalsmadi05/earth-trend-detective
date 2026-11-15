import time
import httpx

_client = httpx.Client(timeout=httpx.Timeout(240.0, connect=15.0), follow_redirects=True,
                       headers={"User-Agent": "earth-trend-detective/0.1"})


def get(url: str, params: dict | None = None, retries: int = 4, binary: bool = False,
        timeout: float | None = None, headers: dict | None = None, backoff: float = 1.5):
    """GET with exponential-backoff retries. Returns parsed JSON (or bytes if binary).
    `timeout` (seconds) overrides the client default for this call; `headers` are added to the request."""
    last = None
    kw = {}
    if timeout is not None:
        kw["timeout"] = httpx.Timeout(timeout, connect=min(timeout, 15.0))
    if headers:
        kw["headers"] = headers
    for i in range(retries):
        try:
            r = _client.get(url, params=params, **kw)
            r.raise_for_status()
            return r.content if binary else r.json()
        except Exception as e:  # noqa: BLE001
            last = e
            if i < retries - 1:
                time.sleep(backoff * (2 ** i))
    raise RuntimeError(f"GET failed after {retries} tries: {url} ({last})")
