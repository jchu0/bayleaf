"""Shared identity, hashing, and time helpers for the record layer.

The `schemas.md` conventions live here so every record acquires them the same way:

  * **type-prefixed UUIDv7 ids** (time-sortable), with `created_at` stored
    separately as the source of truth for time;
  * **content hashes** (sha256 over canonical JSON) that give immutable records
    a stable identity;
  * **UTC storage** — America/Phoenix is a display concern handled at the edge.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any

# Bump only on a breaking change to any persisted record shape; every record
# stores it so a reader can migrate old ledger/corpus entries.
SCHEMA_VERSION = 1


def _uuid7() -> uuid.UUID:
    """A minimal RFC 9562 UUIDv7 (48-bit ms timestamp + random), time-sortable.

    Implemented locally rather than depending on stdlib ``uuid.uuid7`` (absent on
    our 3.10 floor). Ids sort by creation time, but ``created_at`` is the source
    of truth — never parse a timestamp back out of an id.
    """
    unix_ms = int(time.time() * 1000) & ((1 << 48) - 1)
    rand = int.from_bytes(os.urandom(10), "big")  # 80 random bits
    rand_a = (rand >> 62) & 0xFFF  # 12 bits
    rand_b = rand & ((1 << 62) - 1)  # 62 bits
    # 48-bit ts | version 7 | 12-bit rand_a | variant 0b10 | 62-bit rand_b
    value = (unix_ms << 80) | (0x7 << 76) | (rand_a << 64) | (0b10 << 62) | rand_b
    return uuid.UUID(int=value)


def new_id(prefix: str) -> str:
    """A type-prefixed id, e.g. ``new_id("arun") -> 'arun_018f...'``."""
    return f"{prefix}_{_uuid7().hex}"


def utc_now() -> datetime:
    """Timezone-aware UTC timestamp. Storage is UTC; display is the edge's job."""
    return datetime.now(timezone.utc)


def content_hash(payload: Any) -> str:
    """sha256 hex over a canonical JSON view — the identity of an immutable record."""
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
