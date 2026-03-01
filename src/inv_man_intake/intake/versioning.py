"""Utilities for deterministic document fingerprinting and version IDs."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class VersionFingerprint:
    """Document fingerprint fields used to version inbound uploads."""

    sha256: str
    received_at: str


def compute_sha256(content: bytes) -> str:
    """Compute SHA-256 digest for a file payload."""
    return hashlib.sha256(content).hexdigest()


def normalize_received_at(received_at: str) -> str:
    """Normalize ISO received timestamp/date to a stable UTC-like representation."""
    candidate = received_at.strip()
    if not candidate:
        raise ValueError("received_at must not be empty")

    parsed = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
    return parsed.isoformat()


def build_version_id(sha256: str, received_at: str) -> str:
    """Create deterministic version identifier from hash and received timestamp."""
    normalized = normalize_received_at(received_at)
    return f"{normalized}:{sha256[:16]}"


def create_fingerprint(content: bytes, received_at: str) -> VersionFingerprint:
    """Build a normalized fingerprint from binary content and receive time."""
    digest = compute_sha256(content)
    normalized = normalize_received_at(received_at)
    return VersionFingerprint(sha256=digest, received_at=normalized)
