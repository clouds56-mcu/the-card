import Image from "next/image";
import { LayerExplorer } from "./components/layer-explorer";
import { candidate_paths } from "./data/paths";
import { current_release } from "./data/release";

const specifications = [
  {
    value: `${current_release.board.width_mm.toFixed(2)} × ${current_release.board.height_mm.toFixed(2)}`,
    label: "millimetres",
  },
  { value: String(current_release.board.copper_layers), label: "copper layers" },
  {
    value: current_release.board.finished_thickness_mm.toFixed(2),
    label: "millimetre PCB",
  },
  {
    value: String(current_release.assembly.placed_components),
    label: "placed components",
  },
];

const capabilities = [
  {
    index: "01",
    title: "Persistent display",
    detail: "2.9-inch · 296 × 128",
    description:
      "A monochrome SSD1680 e-paper panel supports partial refresh and keeps a static image without display power.",
  },
  {
    index: "02",
    title: "Two ways to connect",
    detail: "Bluetooth 5 LE · NFC",
    description:
      "The ESP32-S3 handles Bluetooth while a dynamic ST25DV NFC tag can be read by a phone and rewritten by the badge.",
  },
  {
    index: "03",
    title: "Context on board",
    detail: "6-axis IMU · Temp/RH",
    description:
      "Motion, gesture, temperature, and humidity sensing make the badge a compact platform for responsive experiments.",
  },
  {
    index: "04",
    title: "Built for iteration",
    detail: "Native USB-C · 16 MB flash",
    description:
      "Native USB, 8 MB PSRAM, battery gauging, and accessible source files keep firmware and hardware development open.",
  },
];

const process_stages = [
  { index: "01", name: "Parts", file: "parts.yaml" },
  { index: "02", name: "Circuit", file: "SKiDL" },
  { index: "03", name: "Schematic", file: "KiCad" },
  { index: "04", name: "PCB", file: "4 layers" },
  { index: "05", name: "Checks", file: "ERC · DRC · parity" },
  { index: "06", name: "Output", file: "Gerber · BOM · CPL" },
];

const roadmap = [
  { label: "CAD generated", status: "complete" },
  { label: "Automated verification", status: "complete" },
  { label: "First physical prototype", status: "next" },
  { label: "Firmware baseline", status: "planned" },
  { label: "Enclosure", status: "planned" },
];

function formatBytes(bytes: number) {
  if (bytes >= 1_000_000) return `${(bytes / 1_000_000).toFixed(1)} MB`;
  return `${Math.round(bytes / 1_000)} KB`;
}

function formatDate(timestamp: string) {
  return new Intl.DateTimeFormat("en-GB", {
    day: "2-digit",
    month: "short",
    timeZone: "UTC",
    year: "numeric",
  }).format(new Date(timestamp));
}

function SectionHeading({
  eyebrow,
  title,
  description,
}: {
  eyebrow: string;
  title: string;
  description?: string;
}) {
  return (
    <div className="section-heading">
      <p className="eyebrow">{eyebrow}</p>
      <h2>{title}</h2>
      {description ? <p className="section-description">{description}</p> : null}
    </div>
  );
}

export default function Home() {
  return (
    <>
      <header className="site-header">
        <a className="wordmark" href="#top" aria-label="The Card, home">
          <span aria-hidden="true" className="wordmark-mark">TC</span>
          <span>The Card</span>
        </a>
        <nav className="site-nav" aria-label="Primary navigation">
          <a href="#design">Design</a>
          <a href="#layers">Layers</a>
          <a href="#build">Build</a>
          <a href="#status">Status</a>
        </nav>
        <div className="header-meta">
          <span>Rev {current_release.hardware_revision} · Candidate</span>
          <a href="https://github.com/clouds56-mcu/the-card">
            GitHub <span aria-hidden="true">↗</span>
          </a>
        </div>
      </header>

      <main>
      <section className="hero" id="top">
        <div className="hero-copy">
          <p className="eyebrow">Open hardware · Revision {current_release.hardware_revision}</p>
          <h1>An open e-paper badge, down to the last trace.</h1>
          <p className="lede">
            A lanyard-sized ESP32-S3 platform with a 2.9-inch e-paper
            display, Bluetooth, dynamic NFC, motion, and climate sensing.
            Designed in the open and documented to be rebuilt.
          </p>

          <div className="hero-actions">
            <a className="button button-primary" href="#layers">Explore the board</a>
            <a className="button button-secondary" href="#build">
              Get Rev {current_release.hardware_revision} files
            </a>
          </div>

          <div className="release-status">
            <span className="status-light" aria-hidden="true" />
            <div>
              <strong>CAD candidate</strong>
              <span>Automated checks clean · physical approval pending</span>
            </div>
          </div>
        </div>

        <figure className="board-stage">
          <div className="board-label">
            <span>01 / FRONT</span>
            <span>CAD PREVIEW</span>
          </div>
          <div className="board-image-wrap">
            <Image
              className="board-image"
              src={candidate_paths.pcb_front}
              width={1135}
              height={1800}
              priority
              alt={`Front copper, solder mask, silkscreen, and outline plot for The Card Revision ${current_release.hardware_revision} PCB`}
            />
          </div>
          <figcaption>
            <span>Generated from the checked KiCad source</span>
            <span>Source plot 1:1 · display scaled · Rev {current_release.hardware_revision}</span>
          </figcaption>
        </figure>
      </section>

      <section className="specifications" aria-label="Board specifications">
        {specifications.map((specification, index) => (
          <div className="specification" key={specification.label}>
            <span className="specification-index">0{index + 1}</span>
            <strong>{specification.value}</strong>
            <span>{specification.label}</span>
          </div>
        ))}
      </section>

      <section className="capabilities section-shell" id="design">
        <SectionHeading
          eyebrow="01 / Platform"
          title="Badge outside. Development platform inside."
          description="A familiar portrait format carries a complete connected-device stack—without hiding the design behind a black box."
        />
        <div className="capability-list">
          {capabilities.map((capability) => (
            <article className="capability" key={capability.index}>
              <span className="capability-index">{capability.index}</span>
              <div>
                <h3>{capability.title}</h3>
                <p className="capability-detail">{capability.detail}</p>
              </div>
              <p>{capability.description}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="layers-section section-shell" id="layers">
        <SectionHeading
          eyebrow="02 / Board"
          title="See every copper layer."
          description="The browser is showing the same generated plots used for design review—front, both inner layers, and the mirrored bottom view."
        />
        <LayerExplorer
          board_height_mm={current_release.board.height_mm}
          board_width_mm={current_release.board.width_mm}
          hardware_revision={current_release.hardware_revision}
        />
        <div className="design-links">
          <a href={candidate_paths.pcb_pdf} target="_blank" rel="noreferrer">
            Open the 4-page PCB PDF <span aria-hidden="true">↗</span>
          </a>
          <span>KiCad {current_release.kicad_version}</span>
        </div>
      </section>

      <section className="schematic-section section-shell">
        <div className="schematic-copy">
          <SectionHeading
            eyebrow="03 / Schematic"
            title="The whole circuit, one sheet."
            description="Power, USB, display drive, NFC, sensors, controls, and protection are grouped for review while retaining canonical net names back to the generated circuit model."
          />
          <dl className="schematic-facts">
            <div><dt>Components</dt><dd>75</dd></div>
            <div><dt>Modeled pins</dt><dd>286</dd></div>
            <div><dt>Named nets</dt><dd>42</dd></div>
          </dl>
          <a className="text-link" href={candidate_paths.schematic_pdf} target="_blank" rel="noreferrer">
            Open schematic PDF <span aria-hidden="true">↗</span>
          </a>
        </div>
        <a
          className="schematic-preview"
          href={candidate_paths.schematic_pdf}
          target="_blank"
          rel="noreferrer"
          aria-label="Open the full schematic PDF"
        >
          <Image
            alt={`Thumbnail of The Card Revision ${current_release.hardware_revision} complete schematic`}
            height={900}
            src={candidate_paths.schematic_thumbnail}
            width={1273}
          />
          <span>Complete schematic · Rev {current_release.hardware_revision}</span>
        </a>
      </section>

      <section className="process-section section-shell">
        <SectionHeading
          eyebrow="04 / Provenance"
          title="Open from netlist to board house."
          description="The design is generated, checked, and packaged as a traceable chain. Each release carries its source commit, tool version, reports, file sizes, and SHA-256 hashes."
        />
        <ol className="process-list">
          {process_stages.map((stage) => (
            <li key={stage.index}>
              <span>{stage.index}</span>
              <strong>{stage.name}</strong>
              <small>{stage.file}</small>
            </li>
          ))}
        </ol>
        <div className="source-strip">
          <p>
            <span>Current source</span>
            <code>{current_release.git_commit.slice(0, 12)}</code>
          </p>
          <a href={`https://github.com/clouds56-mcu/the-card/commit/${current_release.git_commit}`}>
            Inspect commit <span aria-hidden="true">↗</span>
          </a>
        </div>
      </section>

      <section className="build-section section-shell" id="build">
        <div className="release-heading">
          <SectionHeading
            eyebrow="05 / Build"
            title={`Build Revision ${current_release.hardware_revision}.`}
            description="Choose the level you need: inspect the design, order a bare board, assemble it, or fork the source."
          />
          <dl className="release-meta">
            <div><dt>Artifact version</dt><dd>v{current_release.release_version}</dd></div>
            <div><dt>Hardware revision</dt><dd>{current_release.hardware_revision}</dd></div>
            <div>
              <dt>Generated</dt>
              <dd><time dateTime={current_release.generated_at}>{formatDate(current_release.generated_at)}</time></dd>
            </div>
          </dl>
        </div>

        <div className="candidate-warning" role="note">
          <strong>Prototype candidate—not production approved.</strong>
          <p>
            The files below pass automated CAD checks. Review the physical gates and board-house import before ordering or assembly.
          </p>
        </div>

        <div className="download-list">
          {current_release.downloads.map((item, index) => (
            <article className="download-row" key={item.category}>
              <span className="download-index">0{index + 1}</span>
              <div className="download-title">
                <p>{item.category}</p>
                <h3>{item.title}</h3>
              </div>
              <p className="download-description">{item.description}</p>
              <div className="download-meta">
                <span>{formatBytes(item.bytes)}</span>
                <code title={item.sha256}>SHA {item.sha256.slice(0, 10)}…</code>
              </div>
              <a className="download-action" href={item.path} download>
                {item.action} <span aria-hidden="true">↓</span>
              </a>
            </article>
          ))}
          <article className="download-row source-download">
            <span className="download-index">04</span>
            <div className="download-title">
              <p>Source</p>
              <h3>Design source</h3>
            </div>
            <p className="download-description">Generators, KiCad source, libraries, datasheets, and documentation.</p>
            <div className="download-meta"><span>MIT</span><code>git</code></div>
            <a className="download-action" href="https://github.com/clouds56-mcu/the-card">
              Fork <span aria-hidden="true">↗</span>
            </a>
          </article>
        </div>

        <div className="manifest-links">
          <span>Machine-readable release</span>
          <a href={candidate_paths.release_manifest}>release.json</a>
          <a href={candidate_paths.checksums}>SHA256SUMS</a>
        </div>
      </section>

      <section className="status-section" id="status">
        <div className="status-intro">
          <p className="eyebrow">06 / Status</p>
          <h2>CAD checks pass.<br />The prototype decides the rest.</h2>
          <p>
            Automated verification confirms connectivity and source-to-board consistency. It cannot replace fit checks, polarity review, assembly import, RF tuning, or bench characterization.
          </p>
        </div>

        <div className="validation-grid" aria-label="Automated validation results">
          {current_release.validation.map((check) => (
            <div className="validation-check" key={check.label}>
              <span>{check.label}</span>
              <strong>{check.value}</strong>
              <small>{check.detail}</small>
            </div>
          ))}
        </div>

        <div className="manual-gates">
          <div className="manual-gates-heading">
            <p>Manual approval</p>
            <strong>{current_release.manual_approval_status}</strong>
          </div>
          <ol>
            {current_release.manual_gates.map((gate, index) => (
              <li key={gate}>
                <span>0{index + 1}</span>
                <p>{gate}</p>
              </li>
            ))}
          </ol>
        </div>
      </section>

      <section className="roadmap-section section-shell">
        <SectionHeading
          eyebrow="07 / Roadmap"
          title="The design is public before the badge is finished."
          description={`Revision ${current_release.hardware_revision} is a reviewable CAD candidate. The next meaningful milestone is a measured, physically assembled prototype.`}
        />
        <ol className="roadmap-list">
          {roadmap.map((item, index) => (
            <li data-status={item.status} key={item.label}>
              <span>0{index + 1}</span>
              <strong>{item.label}</strong>
              <small>{item.status}</small>
            </li>
          ))}
        </ol>
      </section>
      </main>

      <footer className="site-footer">
        <div>
          <span className="wordmark-mark" aria-hidden="true">TC</span>
          <p>An open e-paper badge,<br />down to the last trace.</p>
        </div>
        <div className="footer-links">
          <a href="https://github.com/clouds56-mcu/the-card">GitHub ↗</a>
          <a href="https://github.com/clouds56-mcu/the-card/tree/main/docs">Documentation ↗</a>
          <a href="https://github.com/clouds56-mcu/the-card/blob/main/LICENSE">MIT License ↗</a>
        </div>
        <div className="footer-meta">
          <span>Hardware Rev {current_release.hardware_revision}</span>
          <span>Artifact v{current_release.release_version}</span>
          <span>{current_release.git_commit.slice(0, 12)}</span>
        </div>
      </footer>
    </>
  );
}
