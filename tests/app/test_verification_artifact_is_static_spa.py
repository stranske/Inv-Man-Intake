"""Guard: committed browser evidence must describe the static SPA, not stlite."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse

ARTIFACT = Path("app/live-verification-artifacts/browser-demo-score.json")
FORBIDDEN_SUBSTRINGS = ("@stlite", "cdn.jsdelivr.net", "Streamlit server")


def _is_allowed_url(text: str) -> bool:
    """Return True when text contains no disallowed absolute URL origins."""

    for token in text.replace("'", " ").replace('"', " ").split():
        if "://" not in token and not token.startswith("//"):
            continue
        candidate = token if "://" in token else f"http:{token}"
        parsed = urlparse(candidate)
        scheme = (parsed.scheme or "").lower()
        host = (parsed.hostname or "").lower()
        if scheme in {"blob", "data", "about"}:
            continue
        if scheme in {"http", "https"} and host in {"127.0.0.1", "localhost"}:
            continue
        return False
    return True


def test_artifact_has_no_stlite_or_external_cdn() -> None:
    assert ARTIFACT.is_file(), f"missing verification artifact: {ARTIFACT}"
    raw = ARTIFACT.read_text(encoding="utf-8")
    for needle in FORBIDDEN_SUBSTRINGS:
        assert needle not in raw, f"artifact still references {needle!r}"

    payload = json.loads(raw)
    excerpt = payload.get("body_excerpt") or ""
    assert "Streamlit server" not in excerpt
    assert "@stlite" not in excerpt

    for message in payload.get("console_messages") or []:
        text = str(message.get("text") or "")
        for needle in FORBIDDEN_SUBSTRINGS:
            assert needle not in text, f"console message still references {needle!r}: {text[:160]}"
        assert _is_allowed_url(text), f"console message has non-loopback URL: {text[:200]}"
