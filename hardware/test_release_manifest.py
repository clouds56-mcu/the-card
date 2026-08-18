#!/usr/bin/env python3
"""Tests for the website-facing hardware release manifest."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from scripts.release_manifest import ArtifactSpec, build_release_manifest
from scripts.release_manifest import write_release_manifest


COMMIT = "a" * 40
GENERATED_AT = datetime(2026, 8, 18, 12, 30, tzinfo=timezone.utc)


class ReleaseManifestTests(unittest.TestCase):
  def setUp(self) -> None:
    self.temporary_directory = tempfile.TemporaryDirectory()
    self.addCleanup(self.temporary_directory.cleanup)
    self.root = Path(self.temporary_directory.name)
    self.artifact_path = self.root / "preview" / "schematic.pdf"
    self.artifact_path.parent.mkdir()
    self.artifact_path.write_bytes(b"schematic preview")

  def values(self) -> dict[str, object]:
    return {
      "project": "the-card",
      "release_version": "0.1.0",
      "hardware_revision": "A",
      "git_commit": COMMIT,
      "generated_at": GENERATED_AT,
      "generator": "hardware/scripts/release_fabrication.py",
      "kicad_version": "10.0.5",
      "board": {
        "width_mm": 53.98,
        "height_mm": 85.6,
        "copper_layers": 4,
      },
      "validation": {
        "erc_violations": 0,
        "drc_violations": 0,
        "schematic_parity_violations": 0,
      },
      "assembly": {
        "placed_components": 69,
      },
      "provenance": {
        "dirty_worktree": False,
        "source_files": {"hardware/the-card.kicad_pcb": "b" * 64},
      },
      "manual_approval_status": "pending",
      "manual_release_gates": ["Confirm battery polarity."],
      "artifacts": [
        ArtifactSpec(
          artifact_id="schematic_pdf",
          category="preview",
          path="preview/schematic.pdf",
          media_type="application/pdf",
        ),
      ],
    }

  def test_builds_versioned_manifest_with_verified_artifact_metadata(self) -> None:
    manifest = build_release_manifest(self.root, **self.values())

    self.assertEqual(manifest["schema_version"], 1)
    self.assertEqual(manifest["release_version"], "0.1.0")
    self.assertEqual(manifest["hardware_revision"], "A")
    self.assertEqual(manifest["generated_at"], "2026-08-18T12:30:00Z")
    self.assertEqual(manifest["assembly"], {"placed_components": 69})
    self.assertFalse(manifest["provenance"]["dirty_worktree"])
    self.assertEqual(
      manifest["manual_approval"],
      {"status": "pending", "gates": ["Confirm battery polarity."]},
    )
    self.assertEqual(
      manifest["artifacts"],
      [{
        "artifact_id": "schematic_pdf",
        "category": "preview",
        "path": "preview/schematic.pdf",
        "media_type": "application/pdf",
        "bytes": len(b"schematic preview"),
        "sha256": hashlib.sha256(b"schematic preview").hexdigest(),
      }],
    )

  def test_writes_parseable_release_json_with_trailing_newline(self) -> None:
    manifest_path = write_release_manifest(self.root, **self.values())

    contents = manifest_path.read_text(encoding="utf-8")
    self.assertEqual(manifest_path.name, "release.json")
    self.assertTrue(contents.endswith("\n"))
    self.assertEqual(json.loads(contents)["git_commit"], COMMIT)

  def test_supports_fabrication_preview_and_assembly_artifacts(self) -> None:
    fabrication = self.root / "fabrication" / "the-card-fabrication.zip"
    assembly = self.root / "assembly" / "canonical" / "bom.csv"
    fabrication.parent.mkdir()
    assembly.parent.mkdir(parents=True)
    fabrication.write_bytes(b"fabrication")
    assembly.write_bytes(b"bom")
    values = self.values()
    values["artifacts"] = [
      ArtifactSpec(
        "fabrication_zip",
        "fabrication",
        "fabrication/the-card-fabrication.zip",
        "application/zip",
      ),
      ArtifactSpec(
        "schematic_pdf",
        "preview",
        "preview/schematic.pdf",
        "application/pdf",
      ),
      ArtifactSpec(
        "canonical_bom_csv",
        "assembly",
        "assembly/canonical/bom.csv",
        "text/csv",
        profile="canonical",
      ),
    ]

    manifest = build_release_manifest(self.root, **values)

    self.assertEqual(
      [artifact["category"] for artifact in manifest["artifacts"]],
      ["fabrication", "preview", "assembly"],
    )
    self.assertEqual(manifest["artifacts"][2]["profile"], "canonical")

  def test_supports_validation_reports(self) -> None:
    report = self.root / "reports" / "erc.json"
    report.parent.mkdir()
    report.write_text("{}\n", encoding="utf-8")
    values = self.values()
    values["artifacts"] = [
      ArtifactSpec("erc_report", "report", "reports/erc.json", "application/json"),
    ]

    manifest = build_release_manifest(self.root, **values)

    self.assertEqual(manifest["artifacts"][0]["category"], "report")

  def test_requires_assembly_profile(self) -> None:
    assembly = self.root / "assembly" / "canonical" / "bom.csv"
    assembly.parent.mkdir(parents=True)
    assembly.write_bytes(b"bom")
    values = self.values()
    values["artifacts"] = [
      ArtifactSpec(
        "canonical_bom_csv",
        "assembly",
        "assembly/canonical/bom.csv",
        "text/csv",
      ),
    ]

    with self.assertRaisesRegex(ValueError, "require a profile"):
      build_release_manifest(self.root, **values)

  def test_release_json_cannot_hash_itself(self) -> None:
    (self.root / "release.json").write_text("{}\n", encoding="utf-8")
    values = self.values()
    values["artifacts"] = [
      ArtifactSpec(
        "release_manifest",
        "report",
        "release.json",
        "application/json",
      ),
    ]

    with self.assertRaisesRegex(ValueError, "cannot list itself"):
      build_release_manifest(self.root, **values)

  def test_rejects_duplicate_artifact_ids_and_paths(self) -> None:
    other_path = self.root / "preview" / "pcb.pdf"
    other_path.write_bytes(b"pcb preview")
    values = self.values()
    values["artifacts"] = [
      ArtifactSpec("preview_pdf", "preview", "preview/schematic.pdf", "application/pdf"),
      ArtifactSpec("preview_pdf", "preview", "preview/pcb.pdf", "application/pdf"),
    ]
    with self.assertRaisesRegex(ValueError, "artifact_id values must be unique"):
      build_release_manifest(self.root, **values)

    values["artifacts"] = [
      ArtifactSpec("schematic_pdf", "preview", "preview/schematic.pdf", "application/pdf"),
      ArtifactSpec("pcb_pdf", "preview", "preview/schematic.pdf", "application/pdf"),
    ]
    with self.assertRaisesRegex(ValueError, "artifact paths must be unique"):
      build_release_manifest(self.root, **values)

  def test_rejects_missing_or_escaping_artifact_paths(self) -> None:
    values = self.values()
    values["artifacts"] = [
      ArtifactSpec("missing_pdf", "preview", "preview/missing.pdf", "application/pdf"),
    ]
    with self.assertRaises(FileNotFoundError):
      build_release_manifest(self.root, **values)

    values["artifacts"] = [
      ArtifactSpec("escaped_pdf", "preview", "../schematic.pdf", "application/pdf"),
    ]
    with self.assertRaisesRegex(ValueError, "must be relative"):
      build_release_manifest(self.root, **values)

  def test_rejects_unknown_category_and_invalid_version(self) -> None:
    values = self.values()
    values["release_version"] = "rev-a"
    with self.assertRaisesRegex(ValueError, "release_version is not semantic"):
      build_release_manifest(self.root, **values)

    values = self.values()
    values["artifacts"] = [
      ArtifactSpec(
        "schematic_pdf",
        "documentation",
        "preview/schematic.pdf",
        "application/pdf",
      ),
    ]
    with self.assertRaisesRegex(ValueError, "invalid artifact category"):
      build_release_manifest(self.root, **values)

  def test_validates_semantic_version_identifiers(self) -> None:
    valid_versions = (
      "1.0.0-0",
      "1.0.0-alpha.1",
      "1.0.0-0A",
      "1.0.0+001",
      "1.0.0-alpha+build.001",
    )
    for release_version in valid_versions:
      with self.subTest(release_version=release_version):
        values = self.values()
        values["release_version"] = release_version
        manifest = build_release_manifest(self.root, **values)
        self.assertEqual(manifest["release_version"], release_version)

    invalid_versions = (
      "01.0.0",
      "1.01.0",
      "1.0.01",
      "1.0.0-01",
      "1.0.0-alpha.01",
      "1.0.0-",
      "1.0.0+",
    )
    for release_version in invalid_versions:
      with self.subTest(release_version=release_version):
        values = self.values()
        values["release_version"] = release_version
        with self.assertRaisesRegex(ValueError, "release_version is not semantic"):
          build_release_manifest(self.root, **values)

  def test_requires_timezone_aware_generation_time(self) -> None:
    values = self.values()
    values["generated_at"] = datetime(2026, 8, 18, 12, 30)

    with self.assertRaisesRegex(ValueError, "must include a timezone"):
      build_release_manifest(self.root, **values)


if __name__ == "__main__":
  unittest.main()
