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
];

const state = {
  pyodide: null,
  pyodideInit: null,
  profile: null,
};

function testControls() {
  return globalThis.__STATIC_SPA_TEST_CONTROLS__ || {};
}

function setStatus(message) {
  document.getElementById("runtime-status").textContent = message;
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
  for (const row of profile.graphics) {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = "Open graphic";
    if (!testControls().disableGraphicHandler) {
      button.addEventListener("click", () => {
        row.status = "Opened";
        renderProfile(profile);
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
  setStatus(
    `Pyodide packet pipeline ready (${profile.packet_path || "unknown"}). `
      + `Deterministic outbound calls: ${profile.outbound_calls}`
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
    state.pyodide.globals.set("packet_payload", state.pyodide.toPy(payload));
    const profileJson = await state.pyodide.runPythonAsync(
      "import json\n"
        + "from pyodide_packet_bridge import run_packet\n"
        + "json.dumps(run_packet(packet_payload))"
    );
    renderProfile(JSON.parse(profileJson));
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
    }];
  }
  return Promise.all(files.map(async (file) => ({ name: file.name, text: await file.text() })));
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

loadProfile([{ name: "pdf_primary_mixed_bundle.json", text: "Summit Arc Capital seeded packet." }]);
