"use client";

import Image from "next/image";
import { useState } from "react";
import { candidate_paths } from "../data/paths";

const layers = [
  {
    id: "front",
    short_label: "01",
    label: "Front",
    role: "Display + controls",
    image_path: candidate_paths.pcb_front,
    description: "Display interface, button controls, NFC coil, and front-side signal routing.",
  },
  {
    id: "inner-1",
    short_label: "02",
    label: "Inner 1",
    role: "Ground plane",
    image_path: candidate_paths.pcb_inner_1,
    description: "Continuous ground reference for return paths, shielding, and RF control.",
  },
  {
    id: "inner-2",
    short_label: "03",
    label: "Inner 2",
    role: "Power + signals",
    image_path: candidate_paths.pcb_inner_2,
    description: "Power distribution with secondary signal routing through the stackup.",
  },
  {
    id: "back",
    short_label: "04",
    label: "Back",
    role: "Electronics + battery",
    image_path: candidate_paths.pcb_back,
    description: "ESP32-S3, USB-C, sensors, battery path, protection, and support circuitry.",
  },
] as const;

interface LayerExplorerProps {
  board_height_mm: number;
  board_width_mm: number;
  hardware_revision: string;
}

export function LayerExplorer({
  board_height_mm,
  board_width_mm,
  hardware_revision,
}: LayerExplorerProps) {
  const [active_id, setActiveId] = useState<(typeof layers)[number]["id"]>("front");
  const active_layer = layers.find((layer) => layer.id === active_id) ?? layers[0];

  return (
    <div className="layer-explorer">
      <div className="layer-controls" role="group" aria-label="PCB copper layer">
        {layers.map((layer) => (
          <button
            className="layer-button"
            data-active={layer.id === active_id}
            key={layer.id}
            onClick={() => setActiveId(layer.id)}
            type="button"
            aria-pressed={layer.id === active_id}
          >
            <span>{layer.short_label}</span>
            <strong>{layer.label}</strong>
            <small>{layer.role}</small>
          </button>
        ))}
      </div>

      <div className="layer-view">
        <div className="layer-view-meta">
          <p>{active_layer.short_label} / {active_layer.label}</p>
          <p>{active_layer.description}</p>
        </div>
        <div className="layer-image-shell">
          <Image
            alt={`${active_layer.label} copper plot for The Card Revision ${hardware_revision}: ${active_layer.description}`}
            className="layer-image"
            height={1800}
            key={active_layer.id}
            src={active_layer.image_path}
            width={1135}
          />
        </div>
        <span className="layer-scale">
          {board_width_mm.toFixed(2)} × {board_height_mm.toFixed(2)} mm
        </span>
      </div>
    </div>
  );
}
