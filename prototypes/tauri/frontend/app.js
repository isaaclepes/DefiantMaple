import { gridGeometry, moveIndex, visibleRange } from "./virtual-grid.mjs";

const invoke = window.__TAURI__.core.invoke;
const REVIEW_STATES = [
  "new",
  "needs_review",
  "reviewed",
  "organized",
  "ignored",
  "error",
];

const elements = {
  gallery: document.querySelector("#gallery"),
  spacer: document.querySelector("#spacer"),
  visible: document.querySelector("#visible-items"),
  filter: document.querySelector("#filter"),
  cellSize: document.querySelector("#cell-size"),
  detail: document.querySelector("#detail"),
  files: document.querySelector("#files"),
  startTask: document.querySelector("#start-task"),
  cancelTask: document.querySelector("#cancel-task"),
  progress: document.querySelector("#progress"),
  status: document.querySelector("#status"),
};

let assetCount = 0;
let activeFilter = null;
let cellSize = Number(elements.cellSize.value);
let selectedIndex = 0;
let selectedAsset = null;
let lastGeometry = gridGeometry(1, 1, cellSize);
let renderVersion = 0;
let scrollFrame = null;
let currentTask = null;
let lastKeyAction = Promise.resolve();
const pageCache = new Map();

function cacheSet(key, value) {
  pageCache.set(key, value);
  if (pageCache.size > 24) {
    pageCache.delete(pageCache.keys().next().value);
  }
}

function basename(path) {
  return path.split(/[\\/]/).pop();
}

function percentile(values, fraction) {
  const sorted = [...values].sort((left, right) => left - right);
  const index = Math.max(0, Math.min(sorted.length - 1, Math.round((sorted.length - 1) * fraction)));
  return sorted[index];
}

async function fetchPage(range) {
  if (range.limit === 0) return [];
  const key = `${activeFilter ?? "all"}:${range.start}:${range.limit}`;
  if (pageCache.has(key)) return pageCache.get(key);
  const assets = await invoke("page_assets", {
    workflowState: activeFilter,
    offset: range.start,
    limit: Math.max(1, range.limit),
  });
  cacheSet(key, assets);
  return assets;
}

function showDetail(asset) {
  selectedAsset = asset ?? null;
  elements.detail.textContent = asset ? JSON.stringify(asset, null, 2) : "Select an asset.";
}

function cardFor(asset, absoluteIndex) {
  const card = document.createElement("button");
  card.type = "button";
  card.className = "card";
  card.dataset.index = String(absoluteIndex);
  card.setAttribute("role", "gridcell");
  card.setAttribute("aria-rowindex", String(absoluteIndex + 1));
  card.setAttribute("aria-selected", String(absoluteIndex === selectedIndex));
  card.tabIndex = absoluteIndex === selectedIndex ? 0 : -1;
  card.setAttribute(
    "aria-label",
    `${basename(asset.current_path)}, ${asset.media_type}, state ${asset.workflow_state}`,
  );

  const placeholder = document.createElement("span");
  placeholder.className = `placeholder type-${asset.media_type.split("/").pop()}`;
  placeholder.style.height = `${cellSize}px`;
  placeholder.textContent = asset.media_type;
  const name = document.createElement("span");
  name.className = "filename";
  name.textContent = basename(asset.current_path);
  const state = document.createElement("span");
  state.className = "state";
  state.textContent = asset.workflow_state.replaceAll("_", " ");
  card.append(placeholder, name, state);
  card.addEventListener("click", () => {
    selectedIndex = absoluteIndex;
    showDetail(asset);
    updateSelection();
  });
  return card;
}

function updateSelection() {
  for (const card of elements.visible.querySelectorAll(".card")) {
    const selected = Number(card.dataset.index) === selectedIndex;
    card.setAttribute("aria-selected", String(selected));
    card.tabIndex = selected ? 0 : -1;
  }
}

async function renderVisible(force = false) {
  const activeElement = document.activeElement;
  const restoreGalleryFocus = activeElement === elements.gallery
    || activeElement?.classList?.contains("card");
  const version = ++renderVersion;
  lastGeometry = gridGeometry(
    elements.gallery.clientWidth,
    elements.gallery.clientHeight,
    cellSize,
  );
  const range = visibleRange(elements.gallery.scrollTop, assetCount, lastGeometry);
  elements.spacer.style.height = `${range.totalHeight}px`;
  elements.visible.style.transform = `translateY(${range.translateY}px)`;
  elements.visible.style.gridTemplateColumns = `repeat(${lastGeometry.columns}, minmax(0, 1fr))`;
  elements.visible.style.gridAutoRows = `${cellSize + 58}px`;
  const assets = await fetchPage(range);
  if (version !== renderVersion) return;
  elements.visible.replaceChildren(
    ...assets.map((asset, index) => cardFor(asset, range.start + index)),
  );
  const selectedOffset = selectedIndex - range.start;
  if (selectedOffset >= 0 && selectedOffset < assets.length) {
    showDetail(assets[selectedOffset]);
  }
  updateSelection();
  if (restoreGalleryFocus) {
    const selectedCard = elements.visible.querySelector(`[data-index="${selectedIndex}"]`);
    (selectedCard ?? elements.gallery).focus({ preventScroll: true });
  }
  void elements.visible.offsetHeight;
}

async function loadCountAndRender() {
  assetCount = await invoke("count_assets", { workflowState: activeFilter });
  elements.gallery.setAttribute("aria-rowcount", String(assetCount));
  selectedIndex = Math.max(0, Math.min(selectedIndex, Math.max(0, assetCount - 1)));
  await renderVisible(true);
  elements.status.textContent = `${assetCount.toLocaleString()} assets`;
}

async function goToIndex(index) {
  if (assetCount === 0) return;
  selectedIndex = Math.max(0, Math.min(index, assetCount - 1));
  const row = Math.floor(selectedIndex / lastGeometry.columns);
  elements.gallery.scrollTop = row * lastGeometry.rowHeight;
  await renderVisible(true);
  updateSelection();
}

async function setReviewState(workflowState) {
  if (!selectedAsset) await goToIndex(selectedIndex);
  if (!selectedAsset) return;
  const updated = await invoke("update_asset_state", {
    assetId: selectedAsset.asset_id,
    workflowState,
  });
  pageCache.clear();
  if (activeFilter && activeFilter !== workflowState) {
    await loadCountAndRender();
  } else {
    showDetail(updated);
    await renderVisible(true);
  }
  elements.status.textContent = `Review state set to ${workflowState}`;
}

async function monitorTask(taskId) {
  if (taskId !== currentTask) return;
  const snapshot = await invoke("poll_background_task", { taskId });
  elements.progress.value = snapshot.progress;
  if (snapshot.done) {
    elements.startTask.disabled = false;
    elements.cancelTask.disabled = true;
    elements.status.textContent = snapshot.canceled ? "Background task canceled" : "Background task complete";
    currentTask = null;
    return;
  }
  window.setTimeout(() => monitorTask(taskId), 40);
}

async function startTask() {
  if (currentTask !== null) return;
  currentTask = await invoke("start_background_task", { units: null });
  elements.progress.value = 0;
  elements.startTask.disabled = true;
  elements.cancelTask.disabled = false;
  void monitorTask(currentTask);
}

async function cancelTask() {
  if (currentTask === null) return;
  await invoke("cancel_background_task", { taskId: currentTask });
}

async function waitForTask(taskId) {
  for (;;) {
    const snapshot = await invoke("poll_background_task", { taskId });
    if (snapshot.done) return snapshot;
    await new Promise((resolve) => window.setTimeout(resolve, 1));
  }
}

function bindInteractions() {
  elements.filter.addEventListener("change", async () => {
    activeFilter = elements.filter.value || null;
    pageCache.clear();
    selectedIndex = 0;
    elements.gallery.scrollTop = 0;
    await loadCountAndRender();
  });
  elements.cellSize.addEventListener("input", async () => {
    cellSize = Number(elements.cellSize.value);
    await renderVisible(true);
  });
  elements.gallery.addEventListener("scroll", () => {
    if (scrollFrame !== null) cancelAnimationFrame(scrollFrame);
    scrollFrame = requestAnimationFrame(() => {
      scrollFrame = null;
      void renderVisible();
    });
  });
  elements.gallery.addEventListener("keydown", (event) => {
    if (/^[1-6]$/.test(event.key)) {
      event.preventDefault();
      lastKeyAction = setReviewState(REVIEW_STATES[Number(event.key) - 1]);
      return;
    }
    const target = moveIndex(selectedIndex, event.key, lastGeometry.columns, assetCount);
    if (target !== selectedIndex) {
      event.preventDefault();
      lastKeyAction = goToIndex(target);
    }
  });
  elements.files.addEventListener("change", () => {
    const count = elements.files.files?.length ?? 0;
    elements.status.textContent = `Read-only preview request: ${count} file(s); no files changed`;
  });
  elements.gallery.addEventListener("dragover", (event) => event.preventDefault());
  elements.gallery.addEventListener("drop", (event) => {
    event.preventDefault();
    const count = event.dataTransfer?.files.length ?? 0;
    elements.status.textContent = `Read-only drop preview: ${count} file(s); no files changed`;
  });
  elements.startTask.addEventListener("click", startTask);
  elements.cancelTask.addEventListener("click", cancelTask);
  window.addEventListener("resize", () => void renderVisible());
}

async function runBenchmark(config) {
  const backend = await invoke("backend_info");
  const startupMs = config.launch_time_ms === null
    ? performance.now()
    : Date.now() - config.launch_time_ms;
  const initialRss = await invoke("process_rss_bytes");

  const queryMs = [];
  for (let operation = 0; operation < 50; operation += 1) {
    const started = performance.now();
    activeFilter = operation % 2 === 0 ? "new" : null;
    pageCache.clear();
    await loadCountAndRender();
    queryMs.push(performance.now() - started);
  }
  activeFilter = null;
  pageCache.clear();
  await loadCountAndRender();

  const keyboardMs = [];
  const reviewStateMs = [];
  for (let operation = 0; operation < 500; operation += 1) {
    const started = performance.now();
    elements.gallery.dispatchEvent(new KeyboardEvent("keydown", {
      key: "ArrowRight",
      bubbles: true,
    }));
    await lastKeyAction;
    keyboardMs.push(performance.now() - started);
    if (operation % 10 === 0) {
      const stateStarted = performance.now();
      elements.gallery.dispatchEvent(new KeyboardEvent("keydown", {
        key: String((operation / 10) % 4 + 1),
        bubbles: true,
      }));
      await lastKeyAction;
      reviewStateMs.push(performance.now() - stateStarted);
    }
  }

  const taskId = await invoke("start_background_task", { units: 100_000 });
  const scrollMs = [];
  const upper = Math.max(0, Math.min(assetCount - 1, 9_999));
  const traversalStarted = performance.now();
  const traversalDeadline = traversalStarted + 60_000;
  let step = 0;
  while (performance.now() < traversalDeadline) {
    const phase = step % 2_000;
    const ratio = phase <= 999 ? phase / 999 : (1_999 - phase) / 1_000;
    const target = upper > 0 ? Math.floor(upper * ratio) : 0;
    const started = performance.now();
    await goToIndex(target);
    scrollMs.push(performance.now() - started);
    step += 1;
  }
  const scrollDurationSeconds = (performance.now() - traversalStarted) / 1_000;
  const cancelStarted = performance.now();
  await invoke("cancel_background_task", { taskId });
  await waitForTask(taskId);
  const cancelMs = performance.now() - cancelStarted;
  const finalRss = await invoke("process_rss_bytes");

  const metrics = {
    schema: "defiantmaple.desktop-benchmark.v1",
    stack: "tauri-2",
    ...backend,
    display_backend: navigator.userAgent,
    display_scale: window.devicePixelRatio,
    display_size_px: [window.screen.width, window.screen.height],
    asset_count: assetCount,
    startup_ms: Number(startupMs.toFixed(3)),
    rss_first_grid_bytes: initialRss,
    rss_after_scroll_bytes: finalRss,
    query_ms_median: Number(percentile(queryMs, 0.5).toFixed(3)),
    query_ms_p95: Number(percentile(queryMs, 0.95).toFixed(3)),
    keyboard_ms_median: Number(percentile(keyboardMs, 0.5).toFixed(3)),
    keyboard_ms_p95: Number(percentile(keyboardMs, 0.95).toFixed(3)),
    keyboard_ms_max: Number(Math.max(...keyboardMs).toFixed(3)),
    review_state_ms_median: Number(percentile(reviewStateMs, 0.5).toFixed(3)),
    review_state_ms_p95: Number(percentile(reviewStateMs, 0.95).toFixed(3)),
    review_state_ms_max: Number(Math.max(...reviewStateMs).toFixed(3)),
    scroll_step_ms_median: Number(percentile(scrollMs, 0.5).toFixed(3)),
    scroll_step_ms_p95: Number(percentile(scrollMs, 0.95).toFixed(3)),
    scroll_steps_over_16_7_ms: scrollMs.filter((value) => value > 16.7).length,
    scroll_steps: scrollMs.length,
    scroll_duration_seconds: Number(scrollDurationSeconds.toFixed(3)),
    background_cancel_ms: Number(cancelMs.toFixed(3)),
    measurement_notes: [
      "Placeholder cells only; no image decode or disk thumbnail I/O.",
      "System WebView behavior varies by operating system and installed runtime.",
      "Scroll timing includes SQLite IPC, virtual DOM replacement, and forced layout; it does not measure compositor presentation.",
      "The background CPU task is active throughout the 60-second traversal.",
      "Hosted Linux uses Xvfb/X11; native Wayland remains unmeasured.",
      "RSS is the current process resident memory reported by sysinfo.",
      "Startup is one release-executable launch; filesystem, WebView, and OS caches are not controlled.",
    ],
  };
  await invoke("write_benchmark_metrics", { metrics });
  await invoke("finish_benchmark").catch(() => {});
}

async function main() {
  bindInteractions();
  const benchmark = await invoke("benchmark_config");
  await loadCountAndRender();
  await goToIndex(0);
  if (benchmark.enabled) {
    await runBenchmark(benchmark);
  }
}

main().catch(async (error) => {
  const message = error instanceof Error ? error.message : String(error);
  elements.status.textContent = `Prototype error: ${message}`;
  console.error(error);
  try {
    const benchmark = await invoke("benchmark_config");
    if (benchmark.enabled) {
      await invoke("write_benchmark_metrics", {
        metrics: {
          schema: "defiantmaple.desktop-benchmark.v1",
          stack: "tauri-2",
          error: message,
        },
      });
      await invoke("finish_benchmark").catch(() => {});
    }
  } catch (secondary) {
    console.error(secondary);
  }
});
