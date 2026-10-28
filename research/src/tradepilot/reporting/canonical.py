"""Canonical lossless JSON serialization used for report identity."""

import hashlib
import json
from dataclasses import fields, is_dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum
from typing import Any


def canonical_value(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: canonical_value(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("canonical JSON does not support non-finite Decimal values")
        return format(value, "f")
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("canonical timestamps must be timezone-aware")
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    if isinstance(value, timedelta):
        return {
            "days": value.days,
            "seconds": value.seconds,
            "microseconds": value.microseconds,
        }
    if isinstance(value, Enum):
        return canonical_value(value.value)
    if isinstance(value, dict):
        return {str(key): canonical_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [canonical_value(item) for item in value]
    if value is None or isinstance(value, (str, int, bool)):
        return value
    raise TypeError(f"unsupported canonical JSON value: {type(value).__name__}")


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        canonical_value(value), sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False,
    ).encode("utf-8")


def sha256_hex(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()

