#!/usr/bin/env python3
"""Build the versioned, website-facing ``release.json`` manifest."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
from typing import Any, Iterable, Mapping, Sequence


SCHEMA_VERSION = 1
ARTIFACT_CATEGORIES = frozenset({
  "assembly",
  "fabrication",
  "preview",
  "report",
})
APPROVAL_STATUSES = frozenset({"approved", "pending", "rejected"})
SEMANTIC_VERSION = re.compile(
  r"(?:0|[1-9]\d*)\."
  r"(?:0|[1-9]\d*)\."
  r"(?:0|[1-9]\d*)"
  r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
  r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
)
HARDWARE_REVISION_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
GIT_COMMIT = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})")


@dataclass(frozen=True)
class ArtifactSpec:
  """Metadata supplied by the producer for one generated file."""

  artifact_id: str
  category: str
  path: str | Path
  media_type: str
  profile: str | None = None


def sha256_file(path: Path) -> str:
  digest = hashlib.sha256()
  with path.open("rb") as source:
    for chunk in iter(lambda: source.read(1024 * 1024), b""):
      digest.update(chunk)
  return digest.hexdigest()


def _artifact_path(root: Path, path: str | Path) -> tuple[Path, str]:
  relative = PurePosixPath(Path(path).as_posix())
  if relative.is_absolute() or not relative.parts or ".." in relative.parts:
    raise ValueError(f"artifact path must be relative to the release: {path!s}")

  root = root.resolve()
  resolved = (root / Path(*relative.parts)).resolve()
  try:
    resolved.relative_to(root)
  except ValueError as error:
    raise ValueError(
      f"artifact path escapes the release directory: {path!s}"
    ) from error
  if not resolved.is_file():
    raise FileNotFoundError(f"artifact does not exist: {resolved}")
  return resolved, relative.as_posix()


def artifact_metadata(root: Path, spec: ArtifactSpec) -> dict[str, str | int]:
  """Resolve and hash an artifact while preserving a portable relative path."""
  if not re.fullmatch(r"[a-z0-9]+(?:_[a-z0-9]+)*", spec.artifact_id):
    raise ValueError(f"invalid artifact_id: {spec.artifact_id!r}")
  if spec.category not in ARTIFACT_CATEGORIES:
    raise ValueError(f"invalid artifact category: {spec.category!r}")
  if not re.fullmatch(r"[^\s/]+/[^\s/]+", spec.media_type):
    raise ValueError(f"invalid media_type: {spec.media_type!r}")
  if spec.category == "assembly" and spec.profile is None:
    raise ValueError("assembly artifacts require a profile")
  if spec.category != "assembly" and spec.profile is not None:
    raise ValueError("profile is only valid for assembly artifacts")
  if spec.profile is not None and not re.fullmatch(
    r"[a-z0-9]+(?:_[a-z0-9]+)*",
    spec.profile,
  ):
    raise ValueError(f"invalid artifact profile: {spec.profile!r}")

  path, relative_path = _artifact_path(root, spec.path)
  if relative_path == "release.json":
    raise ValueError("release.json cannot list itself as an artifact")
  metadata: dict[str, str | int] = {
    "artifact_id": spec.artifact_id,
    "category": spec.category,
    "path": relative_path,
    "media_type": spec.media_type,
    "bytes": path.stat().st_size,
    "sha256": sha256_file(path),
  }
  if spec.profile is not None:
    metadata["profile"] = spec.profile
  return metadata


def _generated_at(value: datetime | None) -> str:
  timestamp = value or datetime.now(timezone.utc)
  if timestamp.tzinfo is None or timestamp.utcoffset() is None:
    raise ValueError("generated_at must include a timezone")
  return timestamp.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def build_release_manifest(
  root: Path,
  *,
  project: str,
  release_version: str,
  hardware_revision: str,
  git_commit: str,
  generator: str,
  kicad_version: str,
  board: Mapping[str, Any],
  validation: Mapping[str, Any],
  assembly: Mapping[str, Any],
  provenance: Mapping[str, Any],
  manual_approval_status: str,
  manual_release_gates: Sequence[str],
  artifacts: Iterable[ArtifactSpec],
  generated_at: datetime | None = None,
) -> dict[str, Any]:
  """Build and validate the stable public release-manifest representation."""
  if not project:
    raise ValueError("project must not be empty")
  if not SEMANTIC_VERSION.fullmatch(release_version):
    raise ValueError(f"release_version is not semantic: {release_version!r}")
  if not HARDWARE_REVISION_PATTERN.fullmatch(hardware_revision):
    raise ValueError(f"invalid hardware_revision: {hardware_revision!r}")
  if not GIT_COMMIT.fullmatch(git_commit):
    raise ValueError(f"invalid git_commit: {git_commit!r}")
  if manual_approval_status not in APPROVAL_STATUSES:
    raise ValueError(
      f"invalid manual approval status: {manual_approval_status!r}"
    )
  if not generator:
    raise ValueError("generator must not be empty")
  if not kicad_version:
    raise ValueError("kicad_version must not be empty")

  artifact_entries = [artifact_metadata(root, spec) for spec in artifacts]
  artifact_ids = [entry["artifact_id"] for entry in artifact_entries]
  artifact_paths = [entry["path"] for entry in artifact_entries]
  if len(set(artifact_ids)) != len(artifact_ids):
    raise ValueError("artifact_id values must be unique")
  if len(set(artifact_paths)) != len(artifact_paths):
    raise ValueError("artifact paths must be unique")

  return {
    "schema_version": SCHEMA_VERSION,
    "project": project,
    "release_version": release_version,
    "hardware_revision": hardware_revision,
    "git_commit": git_commit,
    "generated_at": _generated_at(generated_at),
    "generator": generator,
    "kicad_version": kicad_version,
    "board": dict(board),
    "validation": dict(validation),
    "assembly": dict(assembly),
    "provenance": dict(provenance),
    "manual_approval": {
      "status": manual_approval_status,
      "gates": list(manual_release_gates),
    },
    "artifacts": artifact_entries,
  }


def write_release_manifest(root: Path, **values: Any) -> Path:
  """Write ``release.json`` and return its path."""
  manifest = build_release_manifest(root, **values)
  path = root / "release.json"
  path.write_text(
    json.dumps(manifest, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
  )
  return path
