import { candidate_base } from "./release";

export const candidate_paths = {
  pcb_front: `${candidate_base}/preview/pcb-front.png`,
  pcb_inner_1: `${candidate_base}/preview/pcb-inner-1.png`,
  pcb_inner_2: `${candidate_base}/preview/pcb-inner-2.png`,
  pcb_back: `${candidate_base}/preview/pcb-back.png`,
  pcb_pdf: `${candidate_base}/preview/pcb.pdf`,
  schematic_thumbnail: `${candidate_base}/preview/schematic-thumbnail.png`,
  schematic_pdf: `${candidate_base}/preview/schematic.pdf`,
  assembly_front: `${candidate_base}/assembly/canonical/assembly-front.png`,
  assembly_back: `${candidate_base}/assembly/canonical/assembly-back.png`,
  release_manifest: `${candidate_base}/release.json`,
  checksums: `${candidate_base}/SHA256SUMS`,
} as const;
