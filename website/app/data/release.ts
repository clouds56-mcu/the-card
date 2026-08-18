import release_manifest from "../../public/hardware/candidates/v0.1.0/release.json";
import { candidate_base } from "./paths";

type ReleaseArtifact = (typeof release_manifest.artifacts)[number];

if (release_manifest.schema_version !== 1) {
  throw new Error(`Unsupported release schema: ${release_manifest.schema_version}`);
}

const bundle_content = {
  preview: {
    action: "Download preview",
    description: "Schematic, copper-layer plots, drill maps, and PDFs.",
    title: "Design review package",
  },
  fabrication: {
    action: "Download fabrication",
    description: "Gerbers, board job, and separate plated/non-plated drill files.",
    title: "Bare-board fabrication",
  },
  assembly: {
    action: "Download assembly",
    description: "Canonical and JLCPCB BOM, positions, and assembly drawings.",
    title: "Assembly package",
  },
} as const;

type BundleCategory = keyof typeof bundle_content;

function publicArtifactPath(path: string) {
  if (path.startsWith("/") || path.split("/").includes("..")) {
    throw new Error(`Unsafe release artifact path: ${path}`);
  }
  return `${candidate_base}/${path}`;
}

function bundle(category: BundleCategory) {
  const artifact = release_manifest.artifacts.find(
    (candidate): candidate is ReleaseArtifact =>
      candidate.category === category && candidate.path.endsWith(".zip"),
  );
  if (!artifact) {
    throw new Error(`Missing ${category} bundle in release manifest`);
  }

  return {
    category,
    ...bundle_content[category],
    bytes: artifact.bytes,
    path: publicArtifactPath(artifact.path),
    sha256: artifact.sha256,
  };
}

export const current_release = {
  assembly: release_manifest.assembly,
  board: release_manifest.board,
  downloads: [bundle("preview"), bundle("fabrication"), bundle("assembly")],
  generated_at: release_manifest.generated_at,
  git_commit: release_manifest.git_commit,
  hardware_revision: release_manifest.hardware_revision,
  kicad_version: release_manifest.kicad_version,
  manual_approval_status: release_manifest.manual_approval.status,
  manual_gates: release_manifest.manual_approval.gates,
  release_version: release_manifest.release_version,
  schema_version: release_manifest.schema_version,
  validation: [
    {
      detail: "electrical rules",
      label: "ERC violations",
      value: String(release_manifest.validation.erc_violations),
    },
    {
      detail: "board rules",
      label: "DRC violations",
      value: String(release_manifest.validation.drc_violations),
    },
    {
      detail: "open endpoints",
      label: "Unconnected items",
      value: String(release_manifest.validation.unconnected_items),
    },
    {
      detail: "schematic ↔ PCB",
      label: "Parity violations",
      value: String(release_manifest.validation.schematic_parity_violations),
    },
  ],
} as const;
