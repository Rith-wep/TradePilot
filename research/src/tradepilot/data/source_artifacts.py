"""Canonical provenance for multi-artifact historical datasets."""

from dataclasses import dataclass
from datetime import datetime

from tradepilot.core.canonical import canonical_json_bytes, sha256_hex

SOURCE_ARTIFACT_SCHEMA_VERSION = "tradepilot-source-artifacts/v1"


@dataclass(frozen=True, slots=True)
class SourceArtifact:
    month: str
    side: str
    file_name: str
    sha256: str
    byte_count: int
    row_count: int
    first_timestamp: datetime
    last_timestamp: datetime

    def __post_init__(self) -> None:
        if self.side not in ("BID", "ASK"):
            raise ValueError("source artifact side must be BID or ASK")
        if len(self.sha256) != 64 or any(value not in "0123456789abcdef" for value in self.sha256):
            raise ValueError("source artifact SHA-256 is invalid")
        if self.byte_count <= 0 or self.row_count <= 0:
            raise ValueError("source artifact sizes must be positive")


@dataclass(frozen=True, slots=True)
class SourceArtifactManifest:
    schema_version: str
    instrument: str
    timeframe: str
    timestamp_format: str
    delimiter: str
    calendar_id: str
    artifacts: tuple[SourceArtifact, ...]

    def __post_init__(self) -> None:
        if self.schema_version != SOURCE_ARTIFACT_SCHEMA_VERSION:
            raise ValueError("unsupported source artifact schema")
        if not self.artifacts:
            raise ValueError("source artifact manifest must not be empty")
        side_order = {"BID": 0, "ASK": 1}
        ordered = tuple(sorted(self.artifacts, key=lambda item: (item.month, side_order[item.side])))
        if self.artifacts != ordered:
            raise ValueError("source artifacts must be ordered by month and side")

    @property
    def checksum(self) -> str:
        return sha256_hex(canonical_json_bytes(self))


def source_manifest_identity(manifest: SourceArtifactManifest) -> str:
    return manifest.checksum
