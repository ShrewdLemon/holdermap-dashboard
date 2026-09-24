# ---------------------------------------------------------------------------
# VENDORED (2nd hop) from `alpha` :: corpus/net.py (sha256[:16] = ed1e840e9c89ec6a),
# copied 2026-09-25 into holdermap-dashboard/pipeline/nseresults/.
# holdermap changes:
#   - ROOT = holdermap-dashboard; cache at cache/results_raw/, manifest at
#     cache/results_raw/manifest.jsonl
#   - `requests` optional (not installed in the build Python): curl-only when absent
#   - _record() is lock-protected so archive downloads can run in threads
#
# Original header follows.
# VENDORED from `steelglass` :: steelglass/net.py
# source sha256[:16] = 3ddd1c15cd2ead47
#
# alpha is deliberately self-contained: the exact corpus and gate code that
# produced the published results table is pinned in this repository's history,
# not in another repo's HEAD. Vendoring costs us hand-porting upstream fixes;
# for a study whose output is a frozen table, reproducibility wins.
#
# Changes from upstream:
#   - none (verbatim copy)
# ---------------------------------------------------------------------------
"""HTTP layer with on-disk caching and a curl fallback.

NSE fingerprints TLS clients: python-requests is frequently rejected with 403
where curl succeeds. We therefore try requests first and transparently fall
back to a curl subprocess, keeping one shared cookie jar per host.

Every fetch is cached to disk and recorded in a manifest so that any figure in
the final workbook can be traced to the exact bytes it came from.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

try:
    import requests
except ImportError:          # holdermap: build Python has no requests -> curl only
    requests = None
import threading
_MANIFEST_LOCK = threading.Lock()

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)

ROOT = Path(__file__).resolve().parent.parent.parent   # holdermap-dashboard/
RAW = ROOT / "cache" / "results_raw"
MANIFEST = RAW / "manifest.jsonl"


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Response:
    status: int
    body: bytes
    url: str
    from_cache: bool = False
    backend: str = "requests"

    def json(self):
        return json.loads(self.body.decode("utf-8", "replace"))

    @property
    def text(self) -> str:
        return self.body.decode("utf-8", "replace")


class Fetcher:
    """Cache-backed fetcher. `throttle` seconds between live network calls."""

    def __init__(self, throttle: float = 0.8, cache_dir: Path = RAW):
        self.throttle = throttle
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.session = requests.Session() if requests else None
        if self.session:
            self.session.headers.update({"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"})
        self._cookie_file = Path(tempfile.gettempdir()) / "steelglass_cookies.txt"
        self._last_call = 0.0
        self._primed: set[str] = set()
        # Hosts where python-requests' TLS fingerprint gets rejected but curl
        # succeeds (NSE does this). Once learned, skip the doomed attempt.
        self._curl_hosts: set[str] = set()

    # ---------------------------------------------------------------- caching
    def _cache_path(self, url: str, suffix: str) -> Path:
        h = hashlib.sha256(url.encode()).hexdigest()[:24]
        return self.cache_dir / f"{h}{suffix}"

    def _record(self, url: str, path: Path, status: int, backend: str, sha: str):
        MANIFEST.parent.mkdir(parents=True, exist_ok=True)
        with _MANIFEST_LOCK, MANIFEST.open("a") as fh:
            fh.write(json.dumps({
                "url": url, "cached_as": str(path.relative_to(ROOT)),
                "status": status, "backend": backend, "sha256": sha,
                "retrieved_at": utcnow(),
            }) + "\n")

    def _sleep(self):
        gap = time.time() - self._last_call
        if gap < self.throttle:
            time.sleep(self.throttle - gap)
        self._last_call = time.time()

    # ----------------------------------------------------------------- curl
    def _curl(self, url: str, headers: dict, out: Path | None = None) -> Response:
        cmd = ["curl", "-sS", "-m", "60", "-A", UA,
               "-b", str(self._cookie_file), "-c", str(self._cookie_file),
               "-w", "\n%{http_code}"]
        for k, v in headers.items():
            cmd += ["-H", f"{k}: {v}"]
        if out is not None:
            cmd += ["-o", str(out), url]
            r = subprocess.run(cmd, capture_output=True, timeout=120)
            code = int((r.stdout.decode().strip().splitlines() or ["0"])[-1] or 0)
            return Response(code, out.read_bytes() if out.exists() else b"", url, backend="curl")
        cmd += [url]
        r = subprocess.run(cmd, capture_output=True, timeout=120)
        raw = r.stdout
        nl = raw.rfind(b"\n")
        code = int(raw[nl + 1:].strip() or 0)
        return Response(code, raw[:nl] if nl >= 0 else raw, url, backend="curl")

    # ----------------------------------------------------------------- fetch
    def prime(self, base: str, paths: list[str]):
        """Warm cookies for a host. Failures are non-fatal - NSE returns 403 on
        the homepage while still issuing the cookies the API needs."""
        if base in self._primed:
            return
        for p in paths:
            try:
                self._sleep()
                self._curl(base + p, {"Accept": "text/html,application/xhtml+xml"})
            except Exception:
                pass
        self._primed.add(base)

    # Transient statuses worth retrying. 404 is deliberately absent - it is an
    # answer, not an outage.
    _RETRYABLE = {0, 429, 500, 502, 503, 504}

    def _attempt(self, url: str, headers: dict, host: str,
                 cp: Path, binary: bool) -> Response:
        resp: Response | None = None
        if host not in self._curl_hosts and self.session is not None:
            try:
                self._sleep()
                r = self.session.get(url, headers=headers, timeout=60)
                resp = Response(r.status_code, r.content, url, backend="requests")
            except Exception:
                resp = None
        # Any failure - not just 401/403/429 - earns the curl fallback. NSE
        # returns 404 to python-requests where curl gets 200; treating 404 as
        # final would silently hide working endpoints.
        if resp is None or resp.status >= 400 or not resp.body:
            self._sleep()
            try:
                curl_resp = self._curl(url, headers, out=cp if binary else None)
            except Exception as exc:
                return resp or Response(0, str(exc).encode(), url, backend="curl")
            if resp is not None and resp.status >= 400 and curl_resp.status == 200:
                self._curl_hosts.add(host)  # learn: this host wants curl
            resp = curl_resp
        return resp

    def get(self, url: str, headers: dict | None = None, *, binary: bool = False,
            use_cache: bool = True, force_curl: bool = False) -> Response:
        suffix = ".bin" if binary else ".json"
        cp = self._cache_path(url, suffix)
        if use_cache and cp.exists() and cp.stat().st_size > 0:
            return Response(200, cp.read_bytes(), url, from_cache=True)

        headers = dict(headers or {})
        host = url.split("/", 3)[2] if "://" in url else ""
        if force_curl:
            self._curl_hosts.add(host)

        resp = self._attempt(url, headers, host, cp, binary)
        for backoff in (2.0, 5.0):
            if resp.status not in self._RETRYABLE:
                break
            time.sleep(backoff)
            resp = self._attempt(url, headers, host, cp, binary)

        if resp.status == 200 and resp.body:
            cp.write_bytes(resp.body)
            self._record(url, cp, resp.status, resp.backend,
                         hashlib.sha256(resp.body).hexdigest())
        return resp

    def download(self, url: str, dest: Path, headers: dict | None = None) -> Path | None:
        """Fetch a binary document (PDF) into `dest`. Returns None on failure.

        `dest` is a human-readable alias (data/raw/<SYMBOL>/<date>_<TYPE>_<name>);
        the bytes themselves live once in the URL-keyed cache. We symlink rather
        than writing a second copy - at ~30 filings a company, duplicating
        multi-MB PDFs cost more disk than the whole rest of the project.

        BSE serves an HTML error page with HTTP 200 for withdrawn filings, so the
        %PDF magic check below - not the status code - is what keeps soft-404s
        out of the corpus.
        """
        dest.parent.mkdir(parents=True, exist_ok=True)
        r = self.get(url, headers or {}, binary=True)
        if r.status != 200 or len(r.body) < 1000:
            return None
        if not r.body[:5].startswith(b"%PDF"):
            return None

        cache = self._cache_path(url, ".bin")
        if dest.is_symlink() or dest.exists():
            dest.unlink()
        if cache.exists():
            try:
                dest.symlink_to(os.path.relpath(cache, dest.parent))
                return dest
            except OSError:
                pass  # filesystem without symlink support - fall through to a copy
        dest.write_bytes(r.body)
        return dest
