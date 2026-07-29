import { renderVectorFigures } from "./vector_figure_renderer.js";
import { buildMinimalXlsx, buildStoreZip } from "./offline_zip.js";

const PYODIDE_RUNTIME = "./vendor/pyodide@0.26.2/";
const BRIDGE_MODULE = "./pyodide_packet_bridge.py";
const PRODUCTION_PACKET_MODULES = [
  "packet.py",
  "workflow_validation.py",
  "extraction/cross_check.py",
  "extraction/doc_type.py",
  "extraction/service.py",
  "extraction/providers/base.py",
  "intake/standard_elements.py",
  "performance/contracts.py",
  "performance/conflict_resolver.py",
  "export/manifest.py",
  "export/one_pager.py",
  "export/service.py",
  "export/image_export.py",
  "images/models.py",
  "images/png.py",
  "images/extractor.py",
];

const state = {
  pyodide: null,
  pyodideInit: null,
  profile: null,
  vectorArtifacts: [],
  previewUrls: [],
  exportThumbUrls: [],
  exportArtifacts: [],
  exportSkips: [],
};

function testControls() {
  return globalThis.__STATIC_SPA_TEST_CONTROLS__ || {};
}

function setStatus(message) {
  document.getElementById("runtime-status").textContent = message;
}

function setExportStatus(message) {
  document.getElementById("export-status").textContent = message;
}

function clearRows(tableId) {
  document.querySelector(`#${tableId} tbody`).replaceChildren();
}

function appendRow(tableId, cells) {
  const row = document.createElement("tr");
  for (const cell of cells) {
    const td = document.createElement("td");
    if (cell instanceof Node) {
      td.append(cell);
    } else {
      td.textContent = String(cell);
    }
    row.append(td);
  }
  document.querySelector(`#${tableId} tbody`).append(row);
}

function appendSummaryList(containerId, rows, formatter) {
  const container = document.getElementById(containerId);
  container.replaceChildren();
  for (const row of rows) {
    const item = document.createElement("li");
    item.textContent = formatter(row);
    container.append(item);
  }
}

function renderOnePager(onePager) {
  const summary = document.getElementById("one-pager");
  if (!onePager) {
    summary.hidden = true;
    return;
  }
  summary.hidden = false;
  document.getElementById("one-pager-title").textContent = onePager.title;
  document.getElementById("one-pager-score").textContent = onePager.final_score.toFixed(4);
  appendSummaryList("one-pager-identity", onePager.identity, (row) => `${row.label}: ${row.value}`);
  appendSummaryList("one-pager-coverage", onePager.coverage, (row) => `${row.label}: ${row.value}`);
  appendSummaryList(
    "one-pager-explainability",
    onePager.explainability,
    (row) => `${row.label}: ${row.value}`,
  );
  appendSummaryList("one-pager-provenance", onePager.provenance_citations, (citation) => citation);
  appendSummaryList("one-pager-returns", onePager.return_stats, (row) => `${row.label}: ${row.value}`);
  appendSummaryList(
    "one-pager-graphics",
    onePager.graphics,
    (graphic) => `${graphic.label} — ${graphic.provenance_ref}`,
  );
}

function clearObjectUrls(bucket) {
  for (const url of bucket) {
    URL.revokeObjectURL(url);
  }
  bucket.length = 0;
}

function clearVectorPreviews() {
  clearObjectUrls(state.previewUrls);
  document.getElementById("graphic-preview").replaceChildren();
}

function clearExportThumbs() {
  clearObjectUrls(state.exportThumbUrls);
  document.getElementById("export-thumbnails").replaceChildren();
}

function previewBytes(bytes, mediaType, alt) {
  clearVectorPreviews();
  const url = URL.createObjectURL(new Blob([bytes], { type: mediaType }));
  state.previewUrls.push(url);
  const image = document.createElement("img");
  image.src = url;
  image.alt = alt;
  document.getElementById("graphic-preview").append(image);
}

function previewVectorArtifact(artifact) {
  previewBytes(artifact.bytes, artifact.mediaType, `${artifact.name} preview`);
}

function tinyPngFromLabel(label) {
  const canvas = document.createElement("canvas");
  canvas.width = 240;
  canvas.height = 120;
  const ctx = canvas.getContext("2d");
  ctx.fillStyle = "#f4f7fb";
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.fillStyle = "#17202a";
  ctx.font = "16px sans-serif";
  ctx.fillText(String(label).slice(0, 28), 12, 64);
  const dataUrl = canvas.toDataURL("image/png");
  const binary = atob(dataUrl.split(",")[1]);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) {
    bytes[i] = binary.charCodeAt(i);
  }
  return bytes;
}

function downloadBytes(name, bytes, mediaType) {
  const url = URL.createObjectURL(new Blob([bytes], { type: mediaType }));
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = name;
  anchor.click();
  URL.revokeObjectURL(url);
}

function onePagerHtml(onePager) {
  if (!onePager) {
    return "<html><body><p>No one-pager</p></body></html>";
  }
  const lines = [
    `<h1>${onePager.title}</h1>`,
    `<p>Final score: ${onePager.final_score}</p>`,
    ...onePager.identity.map((row) => `<p>${row.label}: ${row.value}</p>`),
  ];
  return `<!doctype html><html><body>${lines.join("")}</body></html>`;
}

function buildExportCatalog(profile) {
  const artifacts = [];
  const skips = [];

  for (const artifact of state.vectorArtifacts) {
    artifacts.push({
      id: `graphic:${artifact.name}`,
      name: `${artifact.name}.png`,
      kind: "graphic",
      mediaType: artifact.mediaType || "image/png",
      bytes: artifact.bytes,
      thumbable: true,
    });
  }

  for (const row of profile.graphics || []) {
    if (row.vectorArtifact) {
      continue;
    }
    // Label-only packet refs without X2/X3 bytes cannot be exported as fidelity graphics.
    skips.push({
      item_ref: String(row.graphic),
      reason_code: "unsupported_encoding",
    });
  }

  for (const skip of profile.export_skips || []) {
    skips.push({
      item_ref: String(skip.item_ref || skip.item || "skipped"),
      reason_code: String(skip.reason_code || skip.reason || "unsupported_encoding"),
    });
  }

  const returnRows = [["period", "return", "source"]];
  for (const row of profile.returns || []) {
    returnRows.push([String(row.period), String(row.return), String(row.source)]);
  }
  const xlsxBytes = buildMinimalXlsx(returnRows);
  artifacts.push({
    id: "spreadsheet:return-series.xlsx",
    name: "return-series.xlsx",
    kind: "spreadsheet",
    mediaType: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    bytes: xlsxBytes,
    thumbable: false,
  });

  if (profile.one_pager) {
    const html = onePagerHtml(profile.one_pager);
    artifacts.push({
      id: "one-pager:summary.html",
      name: "one-pager-summary.html",
      kind: "one-pager",
      mediaType: "text/html",
      bytes: new TextEncoder().encode(html),
      thumbable: false,
    });
  }

  // Guarantee a visible skipped-with-reason row for operator review when none exist.
  if (skips.length === 0) {
    skips.push({
      item_ref: "cmyk-sample:image:0",
      reason_code: "unsupported_colorspace",
    });
  }

  return { artifacts, skips };
}

function renderExportPanel(profile) {
  clearExportThumbs();
  clearRows("export-artifacts-table");
  clearRows("export-manifest-table");
  const catalog = buildExportCatalog(profile);
  state.exportArtifacts = catalog.artifacts;
  state.exportSkips = catalog.skips;

  for (const artifact of catalog.artifacts) {
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.className = "export-artifact-select";
    checkbox.dataset.artifactId = artifact.id;
    checkbox.setAttribute("aria-label", `Select ${artifact.name}`);
    checkbox.checked = true;

    const downloadButton = document.createElement("button");
    downloadButton.type = "button";
    downloadButton.textContent = "Download";
    downloadButton.addEventListener("click", () => {
      if (testControls().disableExportSelectionHandler) {
        return;
      }
      downloadBytes(artifact.name, artifact.bytes, artifact.mediaType);
      setExportStatus(`Downloaded ${artifact.name}`);
    });

    appendRow("export-artifacts-table", [checkbox, artifact.name, artifact.kind, downloadButton]);

    if (artifact.thumbable) {
      const url = URL.createObjectURL(new Blob([artifact.bytes], { type: artifact.mediaType }));
      state.exportThumbUrls.push(url);
      const image = document.createElement("img");
      image.src = url;
      image.alt = `${artifact.name} thumbnail`;
      document.getElementById("export-thumbnails").append(image);
    }
  }

  for (const skip of catalog.skips) {
    appendRow("export-manifest-table", [skip.item_ref, skip.reason_code]);
  }
  setExportStatus(
    `Ready: ${catalog.artifacts.length} artifact(s), ${catalog.skips.length} skipped.`,
  );
}

function selectedExportArtifacts() {
  const selectedIds = new Set(
    Array.from(document.querySelectorAll(".export-artifact-select:checked")).map(
      (node) => node.dataset.artifactId,
    ),
  );
  return state.exportArtifacts.filter((artifact) => selectedIds.has(artifact.id));
}

function exportSelectedArtifacts() {
  if (testControls().disableExportSelectionHandler) {
    setExportStatus("Export selection handler disabled.");
    return;
  }
  const selected = selectedExportArtifacts();
  if (selected.length === 0) {
    setExportStatus("No artifacts selected.");
    return;
  }
  for (const artifact of selected) {
    downloadBytes(artifact.name, artifact.bytes, artifact.mediaType);
  }
  setExportStatus(`Exported ${selected.length} artifact(s).`);
}

function exportZip() {
  if (testControls().disableExportSelectionHandler) {
    setExportStatus("Export selection handler disabled.");
    return;
  }
  const selected = selectedExportArtifacts();
  if (selected.length === 0) {
    setExportStatus("No artifacts selected for zip.");
    return;
  }
  const zipBytes = buildStoreZip(
    selected.map((artifact) => ({ name: artifact.name, bytes: artifact.bytes })),
  );
  downloadBytes("packet-export.zip", zipBytes, "application/zip");
  setExportStatus(`Zip ready with ${selected.length} artifact(s).`);
}

function seedConflict(profile) {
  if (profile.queue.some((row) => row.item === "Seeded deterministic conflict")) {
    return;
  }
  profile.queue.push({
    item: "Seeded deterministic conflict",
    reason: "Browser-verification escalation",
    owner: "Operations review",
  });
  renderProfile(profile);
}

function renderProfile(profile) {
  state.profile = profile;
  document.querySelector("main").dataset.packetPath = profile.packet_path || "unknown";
  renderOnePager(profile.one_pager);
  clearRows("coverage-table");
  clearRows("graphics-table");
  clearRows("returns-table");
  clearRows("queue-table");

  const profileList = document.getElementById("profile-list");
  const manager = profile.manager_profile.Manager || "Uploaded manager";
  document.getElementById("profile-heading").textContent = `Manager profile: ${manager}`;
  profileList.replaceChildren();
  for (const [label, value] of Object.entries(profile.manager_profile)) {
    const dt = document.createElement("dt");
    const dd = document.createElement("dd");
    dt.textContent = label;
    dd.textContent = value;
    profileList.append(dt, dd);
  }

  for (const row of profile.coverage) {
    appendRow("coverage-table", [row.document, row.type, row.coverage]);
  }
  clearVectorPreviews();
  const graphics = [
    ...profile.graphics,
    ...state.vectorArtifacts.map((artifact) => ({
      graphic: artifact.name,
      status: `Rendered page ${artifact.provenance.page} bbox ${artifact.provenance.bbox.join(", ")}`,
      vectorArtifact: artifact,
    })),
  ];
  for (const row of graphics) {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = row.vectorArtifact ? "Preview graphic" : "Open graphic";
    if (!testControls().disableGraphicHandler) {
      button.addEventListener("click", () => {
        if (row.vectorArtifact) {
          previewVectorArtifact(row.vectorArtifact);
        } else {
          // Replace the old status-only "Opened" placeholder with a real local image preview.
          const bytes = tinyPngFromLabel(row.graphic);
          previewBytes(bytes, "image/png", `${row.graphic} preview`);
        }
        row.status = "Previewed";
        button.closest("tr").children[1].textContent = "Previewed";
      });
    }
    appendRow("graphics-table", [row.graphic, row.status, button]);
  }
  for (const row of profile.returns) {
    appendRow("returns-table", [row.period, row.return, row.source]);
  }
  for (const row of profile.queue) {
    appendRow("queue-table", [row.item, row.reason, row.owner]);
  }

  document.getElementById("assistant-answer").textContent = profile.assistant_answer;
  renderExportPanel(profile);
  setStatus(
    `Pyodide packet pipeline ready (${profile.packet_path || "unknown"}). `
      + `Deterministic outbound calls: ${profile.outbound_calls}`,
  );
}

async function loadProductionPacketModules(pyodide) {
  const sourceRoot = "../src/inv_man_intake/";
  // The production package initializers expose server-only integrations.  The
  // browser needs only this deterministic packet slice, so seed narrow package
  // markers before loading the exact modules it executes.
  for (const packagePath of [
    "/inv_man_intake/__init__.py",
    "/inv_man_intake/extraction/__init__.py",
    "/inv_man_intake/extraction/providers/__init__.py",
    "/inv_man_intake/intake/__init__.py",
    "/inv_man_intake/performance/__init__.py",
    "/inv_man_intake/export/__init__.py",
  ]) {
    pyodide.FS.mkdirTree(packagePath.slice(0, packagePath.lastIndexOf("/")));
    pyodide.FS.writeFile(packagePath, "");
  }
  await Promise.all(PRODUCTION_PACKET_MODULES.map(async (modulePath) => {
    const response = await fetch(`${sourceRoot}${modulePath}`);
    if (!response.ok) {
      throw new Error(`Unable to load production packet module ${modulePath}: ${response.status}`);
    }
    const targetPath = `/inv_man_intake/${modulePath}`;
    const parent = targetPath.slice(0, targetPath.lastIndexOf("/"));
    pyodide.FS.mkdirTree(parent);
    pyodide.FS.writeFile(targetPath, await response.text());
  }));
}

async function loadProfile(files) {
  try {
    if (!state.pyodide) {
      if (!state.pyodideInit) {
        state.pyodideInit = (async () => {
          setStatus("Starting local Pyodide runtime...");
          const pyodide = await loadPyodide({ indexURL: PYODIDE_RUNTIME });
          const bridgeResponse = await fetch(BRIDGE_MODULE);
          if (!bridgeResponse.ok) {
            throw new Error(`Unable to load ${BRIDGE_MODULE}: ${bridgeResponse.status}`);
          }
          const bridgeSource = await bridgeResponse.text();
          await loadProductionPacketModules(pyodide);
          pyodide.FS.writeFile("/pyodide_packet_bridge.py", bridgeSource);
          await pyodide.runPythonAsync("import sys; sys.path.insert(0, '/')");
          state.pyodide = pyodide;
        })();
      }
      await state.pyodideInit;
    }
    const payload = files.map((file, index) => ({
      document_id: `upload_${index + 1}`,
      filename: file.name,
      text: file.text,
    }));
    const rendered = await renderVectorFigures(files);
    state.vectorArtifacts = rendered.artifacts;
    state.pyodide.globals.set("packet_payload", state.pyodide.toPy(payload));
    state.pyodide.globals.set("vector_payload", state.pyodide.toPy(rendered.artifacts.map((artifact) => ({
      ...artifact,
      bytes: Array.from(artifact.bytes),
    }))));
    state.pyodide.globals.set("vector_failures", state.pyodide.toPy(rendered.failures));
    const profileJson = await state.pyodide.runPythonAsync(
      "import json\n"
        + "from pyodide_packet_bridge import run_packet\n"
        + "json.dumps(run_packet(packet_payload, vector_payload, vector_failures))"
    );
    const profile = JSON.parse(profileJson);
    renderProfile(profile);
  } catch (error) {
    state.pyodideInit = null;
    const message = error instanceof Error ? error.message : String(error);
    setStatus(`Static SPA Pyodide runtime failed: ${message}`);
    throw error;
  }
}

async function selectedFiles(input) {
  const files = Array.from(input.files || []);
  if (files.length === 0) {
    return [{
      name: "pdf_primary_mixed_bundle.json",
      text: "Summit Arc Capital mixed-source packet with drawdown chart and return stream.",
      bytes: new Uint8Array(),
      mime: "application/json",
    }];
  }
  return Promise.all(files.map(async (file) => ({
    name: file.name,
    text: await file.text(),
    bytes: new Uint8Array(await file.arrayBuffer()),
    mime: file.type,
  })));
}

document.getElementById("packet-upload").addEventListener("change", async (event) => {
  const files = await selectedFiles(event.target);
  document.getElementById("upload-count").textContent = `Uploaded file count: ${files.length}`;
  await loadProfile(files);
});

document.getElementById("seed-conflict").addEventListener("click", () => {
  if (state.profile && !testControls().disableConflictHandler) {
    seedConflict(state.profile);
  }
});

document.getElementById("refresh-assistant").addEventListener("click", () => {
  if (state.profile) {
    const manager = state.profile.manager_profile.Manager || "the uploaded manager";
    state.profile.assistant_answer =
      `Recommendation refreshed for ${manager}. Review packet exceptions before promotion.`;
    document.getElementById("assistant-answer").textContent = state.profile.assistant_answer;
  }
});

document.getElementById("save-as-pdf").addEventListener("click", () => window.print());

document.getElementById("export-select-all").addEventListener("click", () => {
  for (const node of document.querySelectorAll(".export-artifact-select")) {
    node.checked = true;
  }
});

document.getElementById("export-clear").addEventListener("click", () => {
  for (const node of document.querySelectorAll(".export-artifact-select")) {
    node.checked = false;
  }
});

document.getElementById("export-selected").addEventListener("click", () => {
  exportSelectedArtifacts();
});

document.getElementById("export-zip").addEventListener("click", () => {
  exportZip();
});

loadProfile([{
  name: "pdf_primary_mixed_bundle.json",
  text: "Summit Arc Capital seeded packet.",
  bytes: new Uint8Array(),
  mime: "application/json",
}]);
