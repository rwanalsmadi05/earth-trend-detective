import time
import httpx

_client = httpx.Client(timeout=httpx.Timeout(240.0, connect=15.0), follow_redirects=True,
                       headers={"User-Agent": "earth-trend-detective/0.1"})


def get(url: str, params: dict | None = None, retries: int = 4, binary: bool = False):
    """GET with exponential-backoff retries. Returns parsed JSON (or bytes if binary)."""
    last = None
    for i in range(retries):
        try:
            r = _client.get(url, params=params)
            r.raise_for_status()
            return r.content if binary else r.json()
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(1.5 * (2 ** i))
    raise RuntimeError(f"GET failed after {retries} tries: {url} ({last})")
