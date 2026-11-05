"""Deterministic hashing primitives for Data Vault 2.0."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable
from typing import Any

_NULL_TOKEN = "<NULL>"
_WHITESPACE = re.compile(r"\s+")
HASH_CONTRACT_VERSION = "sha256-length-prefixed-v1"


def canonicalize(value: Any) -> str:
    """Convert a value into a stable, source-independent string representation."""
    if value is None:
        return _NULL_TOKEN
    text = str(value).strip().upper()
    return _WHITESPACE.sub(" ", text)


def hash_components(*values: Any) -> str:
    """Return a SHA-256 digest for ordered, null-safe components.

    Entity names should be passed as the first component for hub/link keys to
    prevent accidental cross-entity collisions when business keys overlap.
    """
    components = [canonicalize(value) for value in values]
    framed = "".join(f"{len(component.encode('utf-8'))}:{component}" for component in components)
    payload = f"{HASH_CONTRACT_VERSION}:{framed}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def hub_hash(entity: str, business_key: Any, source_system: Any = None) -> str:
    """Hash a hub key, optionally qualified by source system.

    Source qualification is enabled by the loader so two systems may both use
    an identifier such as ``C-100`` without being incorrectly merged.
    """
    return hash_components(entity, source_system, business_key)


def link_hash(entity: str, *hub_keys: str) -> str:
    return hash_components(entity, *hub_keys)


def hash_diff(values: Iterable[Any]) -> str:
    return hash_components(*values)
