const PHASES = [
  "orientation",
  "exploration",
  "planning",
  "execution",
  "review",
  "convergence",
  "crystallization",
];

const state = {
  registryEntries: [],
  track: null,
  filteredPoints: [],
  selectedPointId: null,
  mode: "local",
  serverRootPath: "",
  serverRootUrl: "/",
};

const elements = {
  trackFileInput: document.querySelector("#track-file-input"),
  trackUrlInput: document.querySelector("#track-url-input"),
  loadTrackUrl: document.querySelector("#load-track-url"),
  registryUrlInput: document.querySelector("#registry-url-input"),
  loadRegistryUrl: document.querySelector("#load-registry-url"),
  loadHubLibrary: document.querySelector("#load-hub-library"),
  loadExampleLibrary: document.querySelector("#load-example-library"),
  loadSampleTrack: document.querySelector("#load-sample-track"),
  serverRootPathInput: document.querySelector("#server-root-path"),
  serverRootUrlInput: document.querySelector("#server-root-url"),
  searchInput: document.querySelector("#search-input"),
  phaseFilter: document.querySelector("#phase-filter"),
  sortOrder: document.querySelector("#sort-order"),
  modeTag: document.querySelector("#mode-tag"),
  statusMessage: document.querySelector("#status-message"),
  sourceMessage: document.querySelector("#source-message"),
  libraryList: document.querySelector("#library-list"),
  libraryEmpty: document.querySelector("#library-empty"),
  libraryCount: document.querySelector("#library-count"),
  timelineList: document.querySelector("#timeline-list"),
  timelineEmpty: document.querySelector("#timeline-empty"),
  timelineCount: document.querySelector("#timeline-count"),
  summarySession: document.querySelector("#summary-session"),
  summaryTurns: document.querySelector("#summary-turns"),
  summaryPhases: document.querySelector("#summary-phases"),
  summaryOpen: document.querySelector("#summary-open"),
  trackMeta: document.querySelector("#track-meta"),
  detailView: document.querySelector("#detail-view"),
  detailTag: document.querySelector("#detail-tag"),
  prevPoint: document.querySelector("#prev-point"),
  nextPoint: document.querySelector("#next-point"),
};

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function tryParseJson(value) {
  try {
    return JSON.parse(value);
  } catch {
    return null;
  }
}

function parseJsonLines(text) {
  return text
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line, index) => {
      const parsed = tryParseJson(line);
      if (!parsed) {
        throw new Error(`Line ${index + 1} is not valid JSON.`);
      }
      return parsed;
    });
}

function parseRegistryText(text) {
  const asJson = tryParseJson(text);
  if (asJson && Array.isArray(asJson.wheels)) {
    return asJson.wheels.map(normalizeHubWheelEntry).filter(Boolean);
  }
  if (asJson && Array.isArray(asJson.projects)) {
    return asJson.projects.map(normalizeLegacyProjectEntry).filter(Boolean);
  }
  if (Array.isArray(asJson)) {
    return asJson.map(normalizeRegistryEntry).filter(Boolean);
  }
  if (asJson && Array.isArray(asJson.entries)) {
    return asJson.entries.map(normalizeRegistryEntry).filter(Boolean);
  }
  return parseJsonLines(text).map(normalizeRegistryEntry).filter(Boolean);
}

function normalizeRegistryEntry(entry, index = 0) {
  if (!entry || typeof entry !== "object") {
    return null;
  }

  const path =
    entry.path ||
    entry.url ||
    entry.track ||
    entry.track_path ||
    entry.trackUrl ||
    entry.file ||
    entry.href;

  if (!path) {
    return null;
  }

  return {
    id: entry.id || `entry-${index}-${path}`,
    title:
      entry.title ||
      entry.name ||
      entry.session_id ||
      entry.sessionId ||
      path.split("/").pop(),
    path,
    summary:
      entry.summary ||
      entry.description ||
      entry.note ||
      entry.provider ||
      "",
    provider: entry.provider || "",
    model: entry.model || "",
    source: entry.source || entry.origin || "",
    kind: entry.kind || "track",
  };
}

function normalizeHubWheelEntry(entry, index = 0) {
  if (!entry?.path) {
    return null;
  }

  return {
    id: entry.wheel_id || entry.spoke_id || `wheel-${index}`,
    title:
      entry.foundation_name || entry.foundation_abbrev || entry.wheel_id || entry.path,
    path: entry.path,
    summary:
      entry.project_description ||
      entry.current_phase ||
      entry.status ||
      "Wheelwright wheel",
    provider: "",
    model: "",
    source: "hub-registry.json",
    kind: "wheel-root",
    metadata: {
      wheel_id: entry.wheel_id || "",
      spoke_id: entry.spoke_id || "",
      status: entry.status || "",
    },
  };
}

function normalizeLegacyProjectEntry(entry, index = 0) {
  if (!entry?.path) {
    return null;
  }

  return {
    id: entry.name || `project-${index}`,
    title: entry.name || entry.path,
    path: entry.path,
    summary: entry.description || "Registry project",
    provider: "",
    model: "",
    source: "wheel-projects.json",
    kind: "wheel-root",
  };
}

function parseTrackText(text, sourceLabel = "Loaded Track") {
  const records = parseJsonLines(text);
  const start = records.find((record) => record.event === "session_start") || null;
  const end = records.find((record) => record.event === "session_end") || null;
  const points = records
    .filter((record) => typeof record.turn === "number")
    .map((record) => ({
      ...record,
      __id: `turn-${record.turn}-${record.ts || "unknown"}`,
    }));

  const phases = [...new Set(points.map((point) => point.phase).filter(Boolean))];
  const openCount = points.reduce((count, point) => {
    return count + (Array.isArray(point.open) ? point.open.length : 0);
  }, 0);

  return {
    sourceLabel,
    start,
    end,
    points,
    records,
    phases,
    openCount,
  };
}

function buildPointSearchText(point) {
  return [
    point.phase,
    point.focus,
    point.action,
    point.thinking,
    point.user_intent,
    ...(point.pivotal_statements || []),
    ...(point.decisions || []),
    ...(point.insights || []),
    ...(point.activity || []),
    ...(point.open || []).map((item) => item.item),
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
}

function computeFilteredPoints() {
  if (!state.track) {
    state.filteredPoints = [];
    return;
  }

  const searchTerm = elements.searchInput.value.trim().toLowerCase();
  const phaseFilter = elements.phaseFilter.value;
  const sortOrder = elements.sortOrder.value;

  let points = state.track.points.filter((point) => {
    const matchesPhase = !phaseFilter || point.phase === phaseFilter;
    const matchesSearch =
      !searchTerm || buildPointSearchText(point).includes(searchTerm);
    return matchesPhase && matchesSearch;
  });

  points = [...points].sort((left, right) => {
    if (sortOrder === "desc") {
      return right.turn - left.turn;
    }
    return left.turn - right.turn;
  });

  state.filteredPoints = points;

  const selectedStillVisible = points.some(
    (point) => point.__id === state.selectedPointId,
  );
  if (!selectedStillVisible) {
    state.selectedPointId = points[0]?.__id || null;
  }
}

function setStatus(message, source = "") {
  elements.statusMessage.textContent = message;
  elements.sourceMessage.textContent = source;
}

function renderPhaseOptions() {
  const phases = state.track ? state.track.phases : PHASES;
  const currentValue = elements.phaseFilter.value;
  elements.phaseFilter.innerHTML =
    '<option value="">All phases</option>' +
    phases
      .map((phase) => `<option value="${escapeHtml(phase)}">${escapeHtml(phase)}</option>`)
      .join("");
  if (phases.includes(currentValue)) {
    elements.phaseFilter.value = currentValue;
  }
}

function renderLibrary() {
  elements.libraryCount.textContent = `${state.registryEntries.length} entr${
    state.registryEntries.length === 1 ? "y" : "ies"
  }`;

  if (!state.registryEntries.length) {
    elements.libraryEmpty.style.display = "block";
    elements.libraryList.innerHTML = "";
    return;
  }

  elements.libraryEmpty.style.display = "none";
  elements.libraryList.innerHTML = state.registryEntries
    .map((entry) => {
      const isActive = state.track?.sourceLabel === entry.path;
      const meta = [
        entry.kind === "wheel-root" && "Wheel library root",
        entry.provider && `Provider: ${entry.provider}`,
        entry.model && `Model: ${entry.model}`,
        entry.summary,
      ]
        .filter(Boolean)
        .join(" • ");

      return `
        <li>
          <button class="library-button ${isActive ? "active" : ""}" data-registry-path="${escapeHtml(entry.path)}" type="button">
            <span class="list-title">${escapeHtml(entry.title)}</span>
            <span class="list-meta">${escapeHtml(meta || entry.path)}</span>
          </button>
        </li>
      `;
    })
    .join("");
}

function renderTimeline() {
  const points = state.filteredPoints;
  elements.timelineCount.textContent = `${points.length} point${
    points.length === 1 ? "" : "s"
  }`;

  if (!points.length) {
    elements.timelineEmpty.style.display = "block";
    elements.timelineList.innerHTML = "";
    return;
  }

  elements.timelineEmpty.style.display = "none";
  elements.timelineList.innerHTML = points
    .map((point) => {
      const isActive = point.__id === state.selectedPointId;
      return `
        <li>
          <button class="timeline-button ${isActive ? "active" : ""}" data-point-id="${escapeHtml(point.__id)}" type="button">
            <span class="list-title">
              <span class="turn-accent">Turn ${point.turn}</span>
              <span class="phase-chip">${escapeHtml(point.phase || "point")}</span>
              ${escapeHtml(point.focus || "Untitled point")}
            </span>
            <span class="list-meta">${escapeHtml(point.action || "")}</span>
          </button>
        </li>
      `;
    })
    .join("");
}

function renderSummary() {
  if (!state.track) {
    elements.summarySession.textContent = "No Track loaded";
    elements.summaryTurns.textContent = "0";
    elements.summaryPhases.textContent = "0";
    elements.summaryOpen.textContent = "0";
    return;
  }

  const title =
    state.track.start?.session_id ||
    state.track.end?.summary ||
    state.track.sourceLabel;

  elements.summarySession.textContent = title;
  elements.summaryTurns.textContent = String(state.track.points.length);
  elements.summaryPhases.textContent = String(state.track.phases.length);
  elements.summaryOpen.textContent = String(state.track.openCount);
}

function renderTrackMeta() {
  if (!state.track) {
    elements.trackMeta.innerHTML =
      '<div class="empty-state">Track metadata appears here.</div>';
    return;
  }

  const start = state.track.start || {};
  const end = state.track.end || {};
  const mode = start.mode || "unknown";

  elements.trackMeta.innerHTML = `
    <div class="meta-block">
      <h3>Session Start</h3>
      <ul class="key-value-grid">
        <li><span class="key-label">Source</span><span class="key-value">${escapeHtml(state.track.sourceLabel)}</span></li>
        <li><span class="key-label">Session ID</span><span class="key-value">${escapeHtml(start.session_id || "Unknown")}</span></li>
        <li><span class="key-label">Provider</span><span class="key-value">${escapeHtml(start.provider || "Unknown")}</span></li>
        <li><span class="key-label">Model</span><span class="key-value">${escapeHtml(start.model || "Unknown")}</span></li>
        <li><span class="key-label">Mode</span><span class="key-value">${escapeHtml(mode)}</span></li>
        <li><span class="key-label">Started</span><span class="key-value">${escapeHtml(start.ts || "Unknown")}</span></li>
        <li><span class="key-label">Continues</span><span class="key-value">${escapeHtml(start.continues || start.source_context || "None")}</span></li>
        <li><span class="key-label">Ended</span><span class="key-value">${escapeHtml(end.ts || "Unknown")}</span></li>
      </ul>
    </div>
    <div class="meta-block">
      <h3>Session End</h3>
      <ul class="key-value-grid">
        <li><span class="key-label">Total Turns</span><span class="key-value">${escapeHtml(end.total_turns ?? state.track.points.length)}</span></li>
        <li><span class="key-label">Unresolved Count</span><span class="key-value">${escapeHtml(end.unresolved_count ?? state.track.openCount)}</span></li>
        <li><span class="key-label">Summary</span><span class="key-value">${escapeHtml(end.summary || "No session_end summary present")}</span></li>
      </ul>
    </div>
    <div class="meta-block">
      <h3>Phase Coverage</h3>
      <ul class="tag-list">
        ${state.track.phases.map((phase) => `<li>${escapeHtml(phase)}</li>`).join("") || "<li>No phases found</li>"}
      </ul>
    </div>
  `;
}

function objectListHtml(items) {
  if (!items?.length) {
    return '<p class="field-note">None</p>';
  }
  return `
    <ul class="object-list">
      ${items
        .map((item) => {
          if (typeof item === "string") {
            return `<li>${escapeHtml(item)}</li>`;
          }
          return `<li>${Object.entries(item)
            .map(
              ([key, value]) =>
                `<strong>${escapeHtml(key)}:</strong> ${escapeHtml(
                  Array.isArray(value) ? value.join(", ") : value,
                )}`,
            )
            .join("<br />")}</li>`;
        })
        .join("")}
    </ul>
  `;
}

function renderDetail() {
  const point = state.filteredPoints.find(
    (entry) => entry.__id === state.selectedPointId,
  );

  if (!point) {
    elements.detailTag.textContent = "No selection";
    elements.detailView.innerHTML =
      '<div class="empty-state">Select a visible point to inspect it.</div>';
    return;
  }

  elements.detailTag.textContent = `Turn ${point.turn}`;
  elements.detailView.innerHTML = `
    <div class="detail-block">
      <h3>Core</h3>
      <ul class="key-value-grid">
        <li><span class="key-label">Timestamp</span><span class="key-value">${escapeHtml(point.ts || "Unknown")}</span></li>
        <li><span class="key-label">Phase</span><span class="key-value">${escapeHtml(point.phase || "Unknown")}</span></li>
        <li><span class="key-label">Focus</span><span class="key-value">${escapeHtml(point.focus || "")}</span></li>
        <li><span class="key-label">Action</span><span class="key-value">${escapeHtml(point.action || "")}</span></li>
      </ul>
    </div>
    <div class="detail-block">
      <h3>Thinking</h3>
      <p class="detail-rich-text">${escapeHtml(point.thinking || "No thinking field present.")}</p>
    </div>
    ${
      point.user_intent
        ? `
      <div class="detail-block">
        <h3>User Intent</h3>
        <p class="detail-rich-text">${escapeHtml(point.user_intent)}</p>
      </div>
    `
        : ""
    }
    ${
      point.evolution
        ? `
      <div class="detail-block">
        <h3>Evolution</h3>
        <p class="detail-rich-text">${escapeHtml(point.evolution)}</p>
      </div>
    `
        : ""
    }
    <div class="detail-block">
      <h3>Pivotal Statements</h3>
      ${objectListHtml(point.pivotal_statements || [])}
    </div>
    <div class="detail-block">
      <h3>Decisions</h3>
      ${objectListHtml(point.decisions || [])}
    </div>
    <div class="detail-block">
      <h3>Insights</h3>
      ${objectListHtml(point.insights || [])}
    </div>
    <div class="detail-block">
      <h3>Activity</h3>
      ${objectListHtml(point.activity || [])}
    </div>
    <div class="detail-block">
      <h3>Open</h3>
      ${objectListHtml(point.open || [])}
    </div>
    <div class="detail-block">
      <h3>Fossils</h3>
      ${objectListHtml(point.fossils || [])}
    </div>
    <div class="detail-block">
      <h3>Files In</h3>
      ${objectListHtml(point.files_in || [])}
    </div>
    <div class="detail-block">
      <h3>Files Out</h3>
      ${objectListHtml(point.files_out || [])}
    </div>
    ${
      point.context_health
        ? `
      <div class="detail-block">
        <h3>Context Health</h3>
        ${objectListHtml([point.context_health])}
      </div>
    `
        : ""
    }
  `;
}

function renderAll() {
  renderPhaseOptions();
  computeFilteredPoints();
  renderLibrary();
  renderTimeline();
  renderSummary();
  renderTrackMeta();
  renderDetail();
}

function updateMode(mode) {
  state.mode = mode;
  elements.modeTag.textContent =
    mode === "library" ? "Library mode" : "Local mode";
}

async function fetchText(path) {
  const response = await fetch(path);
  if (!response.ok) {
    throw new Error(`Failed to fetch ${path} (${response.status}).`);
  }
  return response.text();
}

function syncServerRootConfig() {
  state.serverRootPath = elements.serverRootPathInput.value.trim();
  state.serverRootUrl = elements.serverRootUrlInput.value.trim() || "/";
}

function normalizeUrlPrefix(value) {
  if (!value || value === "/") {
    return "/";
  }
  return `/${value.replace(/^\/+|\/+$/g, "")}`;
}

function mapFilesystemPathToUrl(path) {
  if (!path) {
    return null;
  }
  if (/^https?:\/\//i.test(path)) {
    return path;
  }
  if (!path.startsWith("/")) {
    return path;
  }

  syncServerRootConfig();
  if (!state.serverRootPath) {
    return null;
  }

  const normalizedRoot = state.serverRootPath.replace(/\/+$/, "");
  if (!path.startsWith(normalizedRoot)) {
    return null;
  }

  const relative = path.slice(normalizedRoot.length).replace(/^\/+/, "");
  const urlPrefix = normalizeUrlPrefix(state.serverRootUrl);
  return `${urlPrefix === "/" ? "" : urlPrefix}/${relative}`;
}

function resolveTrackPath(path) {
  const mapped = mapFilesystemPathToUrl(path);
  return mapped || path;
}

async function discoverTrackFilesFromDirectory(directoryUrl) {
  const text = await fetchText(directoryUrl);
  const parser = new DOMParser();
  const doc = parser.parseFromString(text, "text/html");
  const hrefs = [...doc.querySelectorAll("a[href]")]
    .map((anchor) => anchor.getAttribute("href"))
    .filter(Boolean)
    .filter((href) => href !== "../")
    .filter((href) => href.endsWith(".jsonl"));

  const unique = [...new Set(hrefs)];
  return unique.map((href) => new URL(href, new URL(directoryUrl, window.location.href)).pathname);
}

async function resolveWheelEntry(entry) {
  const mappedBase = mapFilesystemPathToUrl(entry.path);
  if (!mappedBase) {
    return [
      {
        ...entry,
        summary: `${entry.summary} • configure server root mapping to resolve Track files`,
      },
    ];
  }

  const sessionsPath = `${mappedBase.replace(/\/+$/, "")}/WAI-Spoke/sessions/`;

  try {
    const tracks = await discoverTrackFilesFromDirectory(sessionsPath);
    if (!tracks.length) {
      return [
        {
          ...entry,
          summary: `${entry.summary} • no discoverable .jsonl files in WAI-Spoke/sessions/`,
        },
      ];
    }

    return tracks.map((trackPath, index) => ({
      id: `${entry.id}-track-${index}`,
      title: `${entry.title} — ${trackPath.split("/").pop()}`,
      path: trackPath,
      summary: `${entry.summary} • auto-resolved from ${entry.source}`,
      provider: "",
      model: "",
      source: entry.source,
      kind: "track",
    }));
  } catch {
    return [
      {
        ...entry,
        summary: `${entry.summary} • unable to read WAI-Spoke/sessions/ from server`,
      },
    ];
  }
}

async function resolveRegistryEntries(entries) {
  const resolved = await Promise.all(
    entries.map(async (entry) => {
      if (entry.kind !== "wheel-root") {
        return [entry];
      }
      return resolveWheelEntry(entry);
    }),
  );

  return resolved.flat();
}

async function loadTrackFromText(text, sourceLabel) {
  state.track = parseTrackText(text, sourceLabel);
  state.selectedPointId = state.track.points[0]?.__id || null;
  setStatus(
    `Loaded ${state.track.points.length} points from Track.`,
    sourceLabel,
  );
  renderAll();
}

async function loadTrackFromPath(path) {
  const resolvedPath = resolveTrackPath(path);
  const text = await fetchText(resolvedPath);
  await loadTrackFromText(text, path);
}

async function loadRegistry(path) {
  const text = await fetchText(path);
  const parsed = parseRegistryText(text);
  state.registryEntries = parsed;
  updateMode("library");
  setStatus(
    `Loaded registry with ${parsed.length} entr${parsed.length === 1 ? "y" : "ies"}.`,
    path,
  );
  renderAll();

  const hasWheelEntries = parsed.some((entry) => entry.kind === "wheel-root");
  if (hasWheelEntries) {
    setStatus(
      "Loaded hub/project registry. Resolving wheel session libraries...",
      path,
    );
    state.registryEntries = await resolveRegistryEntries(parsed);
    setStatus(
      `Resolved ${state.registryEntries.length} library entr${
        state.registryEntries.length === 1 ? "y" : "ies"
      } from registry.`,
      path,
    );
    renderAll();
  }
}

function selectRelativePoint(direction) {
  const points = state.filteredPoints;
  if (!points.length) {
    return;
  }

  const currentIndex = points.findIndex(
    (point) => point.__id === state.selectedPointId,
  );
  const nextIndex =
    currentIndex === -1
      ? 0
      : Math.max(0, Math.min(points.length - 1, currentIndex + direction));
  state.selectedPointId = points[nextIndex].__id;
  renderDetail();
  renderTimeline();
}

function hydrateFromQuery() {
  const params = new URLSearchParams(window.location.search);
  const track = params.get("track");
  const registry = params.get("registry");
  const serverRootPath = params.get("serverRootPath");
  const serverRootUrl = params.get("serverRootUrl");

  if (serverRootPath) {
    elements.serverRootPathInput.value = serverRootPath;
  }
  if (serverRootUrl) {
    elements.serverRootUrlInput.value = serverRootUrl;
  }

  if (registry) {
    elements.registryUrlInput.value = registry;
    loadRegistry(registry).catch((error) => {
      setStatus("Failed to load registry.", error.message);
    });
    return;
  }

  if (track) {
    elements.trackUrlInput.value = track;
    loadTrackFromPath(track).catch((error) => {
      setStatus("Failed to load Track.", error.message);
    });
  }
}

function attachEvents() {
  elements.trackFileInput.addEventListener("change", async (event) => {
    const [file] = event.target.files || [];
    if (!file) {
      return;
    }

    const text = await file.text();
    updateMode("local");
    await loadTrackFromText(text, file.name).catch((error) => {
      setStatus("Failed to open local Track file.", error.message);
    });
  });

  elements.loadTrackUrl.addEventListener("click", () => {
    const path = elements.trackUrlInput.value.trim();
    if (!path) {
      setStatus("Track path is empty.", "Enter a URL or relative path.");
      return;
    }

    updateMode("local");
    loadTrackFromPath(path).catch((error) => {
      setStatus("Failed to load Track.", error.message);
    });
  });

  elements.loadRegistryUrl.addEventListener("click", () => {
    const path = elements.registryUrlInput.value.trim();
    if (!path) {
      setStatus("Registry path is empty.", "Enter a URL or relative path.");
      return;
    }

    loadRegistry(path).catch((error) => {
      setStatus("Failed to load registry.", error.message);
    });
  });

  elements.loadExampleLibrary.addEventListener("click", () => {
    elements.registryUrlInput.value = "./library.example.json";
    loadRegistry("./library.example.json").catch((error) => {
      setStatus("Failed to load example library.", error.message);
    });
  });

  elements.loadHubLibrary.addEventListener("click", async () => {
    const candidates = [
      "../../hub/hub-registry.json",
      "../../hub/registry/wheel-projects.json",
      "/wheelwright/hub/hub-registry.json",
      "/wheelwright/hub/registry/wheel-projects.json",
      "/hub/hub-registry.json",
      "/hub/registry/wheel-projects.json",
    ];

    for (const candidate of candidates) {
      try {
        elements.registryUrlInput.value = candidate;
        await loadRegistry(candidate);
        return;
      } catch {
        // Try the next candidate.
      }
    }

    setStatus(
      "Failed to auto-detect a hub registry.",
      "Set the registry path manually and, if needed, configure the server root mapping.",
    );
  });

  elements.loadSampleTrack.addEventListener("click", () => {
    elements.trackUrlInput.value = "../samples/coding-session.jsonl";
    updateMode("local");
    loadTrackFromPath("../samples/coding-session.jsonl").catch((error) => {
      setStatus("Failed to load sample Track.", error.message);
    });
  });

  elements.searchInput.addEventListener("input", renderAll);
  elements.phaseFilter.addEventListener("change", renderAll);
  elements.sortOrder.addEventListener("change", renderAll);
  elements.serverRootPathInput.addEventListener("change", syncServerRootConfig);
  elements.serverRootUrlInput.addEventListener("change", syncServerRootConfig);
  elements.prevPoint.addEventListener("click", () => selectRelativePoint(-1));
  elements.nextPoint.addEventListener("click", () => selectRelativePoint(1));

  elements.libraryList.addEventListener("click", (event) => {
    const button = event.target.closest("[data-registry-path]");
    if (!button) {
      return;
    }
    const path = button.getAttribute("data-registry-path");
    if (!path) {
      return;
    }
    loadTrackFromPath(path).catch((error) => {
      setStatus("Failed to load registry Track.", error.message);
    });
  });

  elements.timelineList.addEventListener("click", (event) => {
    const button = event.target.closest("[data-point-id]");
    if (!button) {
      return;
    }
    state.selectedPointId = button.getAttribute("data-point-id");
    renderTimeline();
    renderDetail();
  });
}

attachEvents();
renderAll();
hydrateFromQuery();
