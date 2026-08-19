#!/usr/bin/env python3
"""Tests for hardware release packaging and metadata integration."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import zipfile

from scripts import release_fabrication as release


class ReleaseFabricationTests(unittest.TestCase):
  def setUp(self) -> None:
    self.temporary_directory = tempfile.TemporaryDirectory()
    self.addCleanup(self.temporary_directory.cleanup)
    self.root = Path(self.temporary_directory.name)

  def write(self, relative: str, contents: bytes = b"artifact") -> Path:
    path = self.root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(contents)
    return path

  def test_deterministic_archive_has_sorted_portable_members(self) -> None:
    category = self.root / "fabrication"
    first = self.write("fabrication/z-last.gbr", b"last")
    second = self.write("fabrication/nested/a-first.drl", b"first")
    archive_one = self.root / "one.zip"
    archive_two = self.root / "two.zip"

    release.write_deterministic_archive(
      archive_one,
      [first, second],
      category,
    )
    release.write_deterministic_archive(
      archive_two,
      [second, first],
      category,
    )

    self.assertEqual(archive_one.read_bytes(), archive_two.read_bytes())
    with zipfile.ZipFile(archive_one) as archive:
      self.assertEqual(
        archive.namelist(),
        ["nested/a-first.drl", "z-last.gbr"],
      )
      for member in archive.infolist():
        self.assertEqual(member.date_time, (1980, 1, 1, 0, 0, 0))
        self.assertEqual(member.external_attr >> 16, 0o100644)

  def test_release_metadata_types_every_public_output(self) -> None:
    self.write("fabrication/the-card-fabrication.zip")
    self.write("preview/schematic.pdf")
    self.write("assembly/canonical/bom.csv")
    self.write("assembly/jlcpcb/bom.csv")
    self.write("reports/erc.json", b"{}\n")
    source_hash = "b" * 64

    release.write_release_metadata(
      self.root,
      "0.2.0",
      {"erc_violations": 0, "drc_violations": 0},
      {"placed_components": 1},
      1,
      {"release_inputs": (release.PROJECT,)},
      {release.PROJECT: source_hash},
      {
        "commit": "a" * 40,
        "dirty_worktree": False,
      },
      {
        "kicad_cli": {"path": "kicad-cli", "version": "10.0.5"},
        "python": {"executable": "python3", "version": "3.13"},
      },
    )

    manifest = json.loads((self.root / "release.json").read_text())
    self.assertEqual(manifest["schema_version"], 2)
    self.assertEqual(manifest["design_version"], "0.2.0")
    self.assertNotIn("release_version", manifest)
    self.assertNotIn("hardware_revision", manifest)
    artifacts = {
      artifact["path"]: artifact
      for artifact in manifest["artifacts"]
    }
    self.assertEqual(
      artifacts["fabrication/the-card-fabrication.zip"]["category"],
      "fabrication",
    )
    self.assertEqual(
      artifacts["assembly/canonical/bom.csv"]["profile"],
      "canonical",
    )
    self.assertEqual(
      artifacts["assembly/jlcpcb/bom.csv"]["profile"],
      "jlcpcb",
    )
    self.assertEqual(artifacts["reports/erc.json"]["category"], "report")
    self.assertEqual(
      manifest["provenance"]["source_files"]["hardware/the-card.kicad_pro"],
      source_hash,
    )

    checksums = (self.root / "SHA256SUMS").read_text().splitlines()
    self.assertTrue(any(line.endswith("  release.json") for line in checksums))
    self.assertFalse(any(line.endswith("  SHA256SUMS") for line in checksums))

  def test_artifact_ids_preserve_distinct_normalized_paths(self) -> None:
    flat = Path("preview/pcb-front.png")
    nested = Path("preview/pcb/front.png")

    self.assertNotEqual(release.artifact_id(flat), release.artifact_id(nested))
    self.assertRegex(
      release.artifact_id(flat),
      r"^preview_pcb_front_png_[0-9a-f]{12}$",
    )

  def test_gerber_job_identity_must_match_design_metadata(self) -> None:
    gerber_job = {
      "ProjectId": {"Name": "the-card", "Revision": "0.2.0"},
      "Size": {"X": 54.03, "Y": 85.65},
      "LayerNumber": 4,
      "BoardThickness": 0.8,
    }

    checks = release.validate_gerber_job(gerber_job, "0.2.0")
    self.assertEqual(checks["gerber_job_project"], "the-card")
    self.assertEqual(checks["gerber_job_design_version"], "0.2.0")

    with self.assertRaisesRegex(RuntimeError, "title block"):
      release.validate_gerber_job(gerber_job, "0.3.0")

    gerber_job["ProjectId"]["Name"] = "other-project"
    with self.assertRaisesRegex(RuntimeError, "project name"):
      release.validate_gerber_job(gerber_job, "0.2.0")

  def test_design_version_comes_from_design_metadata(self) -> None:
    self.assertEqual(release.configured_design_version(), "0.2.0")
    with mock.patch.object(
      release,
      "load_design_metadata",
      return_value={"project_name": "the-card", "design_version": "draft-b"},
    ):
      with self.assertRaisesRegex(ValueError, "DESIGN_VERSION is not semantic"):
        release.configured_design_version()

  def test_generated_sources_must_share_the_design_identity(self) -> None:
    schematic = self.write(
      "the-card.kicad_sch",
      b'(kicad_sch\n\t(title_block\n\t\t(rev "0.2.0")\n\t)\n)',
    )
    board = self.write(
      "the-card.kicad_pcb",
      b'(kicad_pcb\n\t(title_block\n\t\t(rev "0.2.0")\n\t)\n'
      b'\t(gr_text "HW 0.2 - 4L / 0.8 mm"\n'
      b'\t\t(layer "B.SilkS")\n\t)\n)',
    )
    with (
      mock.patch.object(release, "SCHEMATIC", schematic),
      mock.patch.object(release, "BOARD", board),
    ):
      release.assert_design_identity("0.2.0")
      with self.assertRaisesRegex(ValueError, "title-block versions"):
        release.assert_design_identity("0.3.0")

  def test_gerber_headers_must_share_the_design_identity(self) -> None:
    first = self.write(
      "gerbers/front.gtl",
      b"%TF.ProjectId,the-card,guid,0.2.0*%\n",
    )
    second = self.write(
      "gerbers/back.gbl",
      b"%TF.ProjectId,the-card,guid,0.2.0*%\n",
    )
    release.validate_gerber_headers(
      [first, second],
      "the-card",
      "0.2.0",
    )
    second.write_text("%TF.ProjectId,the-card,guid,0.1.0*%\n")
    with self.assertRaisesRegex(RuntimeError, "back.gbl"):
      release.validate_gerber_headers(
        [first, second],
        "the-card",
        "0.2.0",
      )

  def test_category_archive_names_use_the_design_version(self) -> None:
    fabrication_file = self.write("fabrication/gerbers/front.gtl")
    self.write("assembly/canonical/bom.csv")
    self.write("preview/schematic.pdf")

    archives = release.write_category_archives(
      self.root,
      "0.2.0",
      [fabrication_file],
    )

    self.assertEqual(
      [archive.name for archive in archives],
      [
        "the-card-hardware-v0.2.0-fabrication.zip",
        "the-card-hardware-v0.2.0-assembly.zip",
        "the-card-hardware-v0.2.0-preview.zip",
      ],
    )

  def test_dnp_and_non_assembly_parts_are_explicitly_excluded(self) -> None:
    self.assertEqual(
      release.excluded_assembly_references(),
      frozenset({"C29", "L2"}),
    )
    release.assert_no_excluded_assembly_references(
      ["R17", "U2"],
      "fixture",
    )

    with self.assertRaisesRegex(
      ValueError,
      r"fixture contains DNP/non-assembly references: \['C29', 'L2'\]",
    ):
      release.assert_no_excluded_assembly_references(
        ["U2", "L2", "C29"],
        "fixture",
      )

  def test_nfc_verifier_is_hashed_and_receives_exact_release_inputs(self) -> None:
    self.assertIn(
      release.VERIFY_NFC_DESIGN,
      release.VERIFICATION_INPUT_FILES,
    )
    with mock.patch.object(release, "run") as run:
      release.verify_nfc_design()

    run.assert_called_once_with([
      release.sys.executable,
      str(release.VERIFY_NFC_DESIGN),
      "--schematic",
      str(release.SCHEMATIC),
      "--board",
      str(release.BOARD),
      "--kicad-cli",
      str(release.KICAD_CLI),
    ])

  def test_failed_nfc_verifier_stops_release_before_exports(self) -> None:
    output = self.root / "release"
    with (
      mock.patch.object(release, "assert_inputs"),
      mock.patch.object(release, "release_source_groups", return_value={}),
      mock.patch.object(release, "capture_source_hashes", return_value={}),
      mock.patch.object(
        release,
        "capture_git_state",
        return_value={"dirty_worktree": False},
      ),
      mock.patch.object(release, "capture_toolchain", return_value={}),
      mock.patch.object(release, "verify_schematic_connectivity"),
      mock.patch.object(
        release,
        "verify_nfc_design",
        side_effect=RuntimeError("foreign copper"),
      ),
      mock.patch.object(release, "export_reports") as export_reports,
    ):
      with self.assertRaisesRegex(RuntimeError, "foreign copper"):
        release.build_release(output, False)

    export_reports.assert_not_called()

  def test_pdf_sanitizer_neutralizes_javascript_names_in_place(self) -> None:
    pdf = self.write(
      "preview/schematic.pdf",
      b"%PDF-1.7\n"
      b"<< /Names << /JavaScript 4 0 R >> >>\n"
      b"<< /Type /Action /S /JavaScript /JS (app.launchURL) >>\n"
      b"%%EOF\n",
    )
    original_size = pdf.stat().st_size

    replacements = release.sanitize_pdf(pdf)

    contents = pdf.read_bytes()
    self.assertEqual(replacements, 3)
    self.assertEqual(pdf.stat().st_size, original_size)
    self.assertNotIn(b"/JavaScript", contents)
    self.assertNotRegex(contents, rb"/JS(?=[\s<>()\[\]{}/%])")
    self.assertIn(b"/JavaScrip_", contents)
    self.assertIn(b"/J_", contents)

  def test_pdf_sanitizer_leaves_passive_pdf_unchanged(self) -> None:
    pdf = self.write("preview/passive.pdf", b"%PDF-1.7\n%%EOF\n")

    self.assertEqual(release.sanitize_pdf(pdf), 0)
    self.assertEqual(pdf.read_bytes(), b"%PDF-1.7\n%%EOF\n")

  def test_pdf_release_gate_rejects_missed_active_output(self) -> None:
    self.write("preview/passive.pdf", b"%PDF-1.7\n%%EOF\n")
    self.write(
      "assembly/canonical/active.pdf",
      b"%PDF-1.7\n<< /S /JavaScript /JS (alert) >>\n%%EOF\n",
    )

    with self.assertRaisesRegex(RuntimeError, "active PDF JavaScript"):
      release.assert_pdfs_passive(self.root)


if __name__ == "__main__":
  unittest.main()
