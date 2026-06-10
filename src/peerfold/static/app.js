const SPAN_PICK_MAX_DIST = 14;
let draftSaveTimer = null;

const state = {
  doc: null,
  color: "yellow",
  pages: new Map(),
  annotations: new Map(),
  selecting: false,
  activeSelection: null,
  globalSelectionBound: false,
  focusId: null,
  locateId: null,
  locateTimer: null,
  pendingNote: null,
  draft: null,
  loadingPages: new Set(),
  pageLoadGen: new Map(),
  pageLoadQueue: [],
  savePending: 0,
  localDirty: false,
  fileMtime: 0,
  syncTimer: null,
  serverRevision: 0,
  tabId: typeof crypto?.randomUUID === "function"
    ? crypto.randomUUID()
    : `tab-${Date.now()}-${Math.random().toString(36).slice(2)}`,
  zoom: 1,
  pinch: null,
  pageOffsets: [],
  pagesTotalHeight: 0,
  pageStubs: new Map(),
  pageObserver: null,
  stubSyncScheduled: false,
  pendingStubRemoval: new Map(),
  zooming: false,
  zoomEndTimer: null,
  gestureActive: false,
  gestureBaseZoom: 1,
  highlightGesture: null,
  extendPreview: null,
  selectedCommentIds: new Set(),
  lastSelectedCommentId: null,
  undoStack: [],
  redoStack: [],
  historyApplying: false,
  commentsCollapsed: false,
  linkWindow: null,
  viewerNavBound: false,
  navReplaceTimer: null,
  navRestoring: false,
};

const syncChannel = typeof BroadcastChannel !== "undefined"
  ? new BroadcastChannel("peerfold-sync")
  : null;

const ZOOM_MIN = 0.55;
const ZOOM_MAX = 2.75;
const ZOOM_STEP = 1.12;
const WHEEL_ZOOM_GAIN = 0.0017;
const WHEEL_ZOOM_STEP_MAX = 0.014;
const PAGE_GAP = 24;
const PAGE_PAD_TOP = 28;
const PAGE_PAD_BOTTOM = 48;
const PAGE_STUB_BUFFER = 5;
const PAGE_PREFETCH = 10;
const STUB_UNLOAD_DELAY_MS = 600;
const PAGE_LOAD_MARGIN = "1600px 0px";
const MAX_PAGE_LOADS_IN_FLIGHT = 8;
const USE_CSS_ZOOM = typeof CSS !== "undefined" && CSS.supports?.("zoom", "1");
const DRAFT_GREY = "rgba(118, 118, 128, 0.44)";
const LINK_WINDOW_NAME = "peerfold-citation";
const LINK_WINDOW_FEATURES = "width=1120,height=840,left=120,top=80,resizable=yes,scrollbars=yes";
const COMMENTS_W_MIN = 220;
const COMMENTS_W_MAX = 640;
const COMMENTS_H_MIN = 120;
const COMMENTS_H_MAX = 720;
const LS_COMMENTS_W = "peerfold-comments-w";
const LS_COMMENTS_H = "peerfold-comments-h";
const LS_COMMENTS_COLLAPSED = "peerfold-comments-collapsed";

const LINE_Y_TOL = 4;
const DRAG_THRESHOLD = 4;
const LS_UPDATE_DISMISS = "peerfold-update-dismiss";
const LS_CUSTOM_PALETTE = "peerfold-custom-palette";
const HISTORY_MAX = 80;
const $ = (sel) => document.querySelector(sel);
const pagesViewportEl = $("#pages-viewport");
const pagesEl = $("#pages");
const paletteEl = $("#palette");
const reviewerEl = $("#reviewer");
const reviewerListEl = $("#reviewer-list");
const viewerEl = $("#viewer");
const commentsListEl = $("#comments-list");
const commentsCountEl = $("#comments-count");
const commentsSelectionBarEl = $("#comments-selection-bar");
const commentsSelectionCountEl = $("#comments-selection-count");
const commentsDeleteSelectedEl = $("#comments-delete-selected");
const commentsClearSelectionEl = $("#comments-clear-selection");
const zoomLabelEl = $("#zoom-label");
const ctxMenu = $("#ctx-menu");
const toastEl = $("#toast");
const commentEditorEl = $("#comment-editor");
const commentEditorPanelEl = commentEditorEl?.querySelector(".comment-editor-panel");
const commentEditorBackdropEl = commentEditorEl?.querySelector(".comment-editor-backdrop");
const commentEditorTitleEl = $("#comment-editor-title");
const commentEditorMetaEl = $("#comment-editor-meta");
const commentEditorQuoteEl = $("#comment-editor-quote");
const commentEditorTa = $("#comment-editor-ta");
const commentEditorFootEl = $("#comment-editor-foot");
const workspaceEl = $("#workspace");
const workspaceSplitterEl = $("#workspace-splitter");
const commentsPaneEl = $("#comments-pane");
const commentsCollapseBtnEl = $("#comments-collapse-btn");
const undoBtnEl = $("#undo-btn");
const redoBtnEl = $("#redo-btn");
const openPdfBtnEl = $("#open-pdf-btn");
const openPdfInputEl = $("#open-pdf-input");

async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(opts.headers || {}) },
    ...opts,
  });
  const data = await res.json().catch(() => ({}));
  if (res.status === 503 && data.status === "loading") {
    const err = new Error("loading");
    err.loading = true;
    throw err;
  }
  if (res.status === 503 && data.status === "no_document") {
    const err = new Error("no_document");
    err.noDocument = true;
    throw err;
  }
  if (!res.ok) throw new Error(data.error || res.statusText);
  return data;
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function showBootMessage(msg) {
  if (!pagesEl) return;
  pagesEl.replaceChildren();
  const el = document.createElement("div");
  el.className = "viewer-boot";
  el.textContent = msg;
  pagesEl.appendChild(el);
}

async function waitForApp() {
  for (let attempt = 0; attempt < 600; attempt += 1) {
    try {
      return await api("/api/document");
    } catch (err) {
      if (err.loading) {
        showBootMessage("Opening PDF…");
        await sleep(100);
        continue;
      }
      throw err;
    }
  }
  throw new Error("Timed out while opening the PDF");
}

function showWelcomeScreen() {
  if (!pagesEl) return;
  pagesEl.replaceChildren();
  const el = document.createElement("div");
  el.className = "welcome-screen";
  el.innerHTML = `
    <div class="welcome-card">
      <div class="welcome-mark" aria-hidden="true"></div>
      <h2 class="welcome-title">Open a PDF to review</h2>
      <p class="welcome-lead">Highlight text, write comments, export a copy with standard PDF annotations.</p>
      <div class="welcome-dropzone">
        <p class="welcome-drop-label">Drop PDF here</p>
        <p class="welcome-drop-sub">Annotations save into the PDF</p>
        <span class="welcome-or">or</span>
        <button type="button" class="btn primary welcome-open" data-welcome-open>Open PDF…</button>
        <p class="welcome-shortcut"><kbd>⌘O</kbd></p>
      </div>
    </div>
  `;
  el.querySelector("[data-welcome-open]")?.addEventListener("click", () => {
    void pickAndOpenPdf();
  });
  pagesEl.appendChild(el);
}

async function openPdfByPath(path) {
  if (!path) return;
  if (!confirmUnsaved("Open another PDF")) return;
  await settleDraft();
  await blurComment();
  showBootMessage("Opening PDF…");
  const doc = await api("/api/open", {
    method: "POST",
    body: JSON.stringify({ path }),
  });
  await applyOpenDocument(doc);
  startDiskSync();
}

async function openPdfFile(file) {
  if (!file) return;
  if (!confirmUnsaved("Open another PDF")) return;
  await settleDraft();
  await blurComment();
  showBootMessage("Opening PDF…");
  const form = new FormData();
  form.append("file", file, file.name || "document.pdf");
  const res = await fetch("/api/open", { method: "POST", body: form });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || res.statusText);
  await applyOpenDocument(data);
  startDiskSync();
}

function wireNativeDropPaths() {
  window.addEventListener("peerfold-drop-path", (ev) => {
    const path = ev.detail;
    if (path) {
      void openPdfByPath(path).catch((err) => toast(err.message || "Could not open PDF"));
    }
  });
  window.addEventListener("peerfold-open-path", (ev) => {
    const path = ev.detail;
    if (path) {
      void openPdfByPath(path).catch((err) => toast(err.message || "Could not open PDF"));
    }
  });
  window.addEventListener("peerfold-menu", (ev) => {
    const action = ev.detail?.action;
    if (action === "undo") void performUndo();
    else if (action === "redo") void performRedo();
    else if (action === "check-updates") void checkForUpdates({ force: true });
  });
}

async function nativePdfPickerAvailable() {
  return Boolean(window.pywebview?.api?.pick_pdf);
}

async function pickAndOpenPdf() {
  if (await nativePdfPickerAvailable()) {
    try {
      const path = await window.pywebview.api.pick_pdf();
      if (path) await openPdfByPath(path);
      return;
    } catch (err) {
      toast(err.message || "Could not open file picker");
      return;
    }
  }
  openPdfInputEl?.click();
}

async function applyOpenDocument(doc) {
  clearHistory();
  state.annotations.clear();
  state.draft = null;
  state.pendingNote = null;
  state.focusId = null;
  state.locateId = null;
  closeCommentEditor();
  clearCommentSelection();
  await syncDocFlags(doc);
  $("#doc-name").textContent = doc.open ? doc.name : "PeerFold";
  if (doc.open && doc.source && window.pywebview?.api?.document_opened) {
    void window.pywebview.api.document_opened(doc.source);
  }
  reviewerEl.value = doc.reviewer;
  populateReviewers();
  buildPalette(doc.palette);
  updateDocMeta();
  if (!doc.open) {
    showWelcomeScreen();
    renderCommentsPane();
    return;
  }
  resetPageViewport();
  clearHistory();
  await reloadAnnotations();
  initPageViewport();
  scheduleStubSync();
  seedViewerNavHistory();
  if (editingInPlace(doc)) {
    toast(`Editing ${basename(doc.source || doc.name)}`, 3200);
  } else {
    const saveName = basename(doc.save_path);
    const srcName = basename(doc.source || doc.name);
    const sameFolder = dirname(doc.save_path) === dirname(doc.source || doc.save_path);
    toast(
      sameFolder
        ? `Saving as ${saveName} beside ${srcName}`
        : `Saving as ${saveName} in ${dirname(doc.save_path)}`,
      4500,
    );
  }
}

async function bootViewer() {
  resetPageViewport();
  await reloadAnnotations();
  initPageViewport();
  scheduleStubSync();
  seedViewerNavHistory();
}

function wireOpenPdf() {
  wireNativeDropPaths();
  const pick = () => { void pickAndOpenPdf(); };
  openPdfBtnEl?.addEventListener("click", pick);
  openPdfInputEl?.addEventListener("change", () => {
    const file = openPdfInputEl.files?.[0];
    openPdfInputEl.value = "";
    if (file) void openPdfFile(file).catch((err) => toast(err.message || "Could not open PDF"));
  });

  const targets = [document.body, workspaceEl, viewerEl].filter(Boolean);
  for (const el of targets) {
    el.addEventListener("dragover", (ev) => {
      if (![...ev.dataTransfer?.types || []].includes("Files")) return;
      ev.preventDefault();
      pagesEl?.querySelector(".welcome-dropzone")?.classList.add("is-dragover");
    });
    el.addEventListener("dragleave", () => {
      pagesEl?.querySelector(".welcome-dropzone")?.classList.remove("is-dragover");
    });
    el.addEventListener("drop", (ev) => {
      pagesEl?.querySelector(".welcome-dropzone")?.classList.remove("is-dragover");
      const file = [...ev.dataTransfer?.files || []].find((f) =>
        f.type === "application/pdf" || f.name.toLowerCase().endsWith(".pdf"),
      );
      if (!file) return;
      ev.preventDefault();
      // Native window: Python drop handler sends peerfold-drop-path with full path.
      if (window.pywebview?.api?.pick_pdf) return;
      void openPdfFile(file).catch((err) => toast(err.message || "Could not open PDF"));
    });
  }
}

function toast(msg, ms = 2200) {
  toastEl.onclick = null;
  toastEl.style.cursor = "";
  toastEl.classList.remove("toast-update");
  toastEl.textContent = msg;
  toastEl.hidden = false;
  clearTimeout(toast._t);
  toast._t = setTimeout(() => { toastEl.hidden = true; }, ms);
}

async function openExternalUrl(url) {
  if (window.pywebview?.api?.open_url) {
    await window.pywebview.api.open_url(url);
    return;
  }
  window.open(url, "_blank", "noopener,noreferrer");
}

function setAppVersion(version) {
  const el = $("#app-version");
  if (el && version) el.textContent = `v${version}`;
}

async function checkForUpdates({ force = false } = {}) {
  try {
    const info = await api("/api/update-check");
    const current = info.current || state.doc?.app_version || "?";
    if (!info.check_ok) {
      if (force) toast("Could not check for updates.", 3000);
      return;
    }
    if (!info.update_available || !info.latest) {
      if (force) toast(`PeerFold v${current} is up to date.`, 3500);
      return;
    }
    const dismissKey = `${LS_UPDATE_DISMISS}:${info.latest}`;
    if (!force && sessionStorage.getItem(dismissKey)) return;

    toastEl.textContent = `Update available: v${info.latest} (you have v${current}) — click to download`;
    toastEl.hidden = false;
    toastEl.classList.add("toast-update");
    toastEl.style.cursor = "pointer";
    toastEl.onclick = () => {
      void openExternalUrl(info.url);
      sessionStorage.setItem(dismissKey, "1");
      toastEl.hidden = true;
      toastEl.onclick = null;
      toastEl.style.cursor = "";
      toastEl.classList.remove("toast-update");
    };
    clearTimeout(toast._t);
    toast._t = setTimeout(() => {
      toastEl.hidden = true;
      toastEl.onclick = null;
      toastEl.style.cursor = "";
      toastEl.classList.remove("toast-update");
    }, 15000);
  } catch (_) {
    if (force) toast("Could not check for updates.", 3000);
  }
}

function hideCtx() {
  ctxMenu.hidden = true;
  ctxMenu.innerHTML = "";
}

function basename(p) {
  return p.split(/[/\\]/).pop();
}

function dirname(p) {
  const parts = (p || "").split(/[/\\]/);
  parts.pop();
  return parts.join("/") || ".";
}

function editingInPlace(doc = state.doc) {
  return doc && (doc.save_copy === false || doc.save_path === doc.source);
}

function trimText(s) {
  return (s || "").trim();
}

function annotKey(ann) {
  if (!ann) return "";
  const rects = (ann.rects || []).slice(0, 3).map((r) =>
    r.map((v) => Math.round(Number(v) * 10) / 10));
  return `${ann.page}|${JSON.stringify(rects)}|${trimText(ann.content)}`;
}

function emergencyBackup() {
  if (!state.doc) return;
  const payload = {
    source: state.doc.source,
    save_path: state.doc.save_path,
    reviewer: state.doc.reviewer,
    at: new Date().toISOString(),
    annotations: [...state.annotations.values()],
  };
  try {
    localStorage.setItem(LS_KEY, JSON.stringify(payload));
  } catch (_) { /* quota */ }
}

function clearNativeSelection() {
  const sel = window.getSelection?.();
  if (!sel) return;
  if (sel.empty) sel.empty();
  else sel.removeAllRanges?.();
}

function clearPreviewLayers() {
  for (const meta of state.pages.values()) {
    meta.draftLayer?.replaceChildren();
  }
  state.selecting = false;
  state.activeSelection = null;
  clearNativeSelection();
}

function clearDraft() {
  clearTimeout(draftSaveTimer);
  draftSaveTimer = null;
  clearPreviewLayers();
  state.draft = null;
  closeCommentEditor();
  updateDocMeta();
  renderCommentsPane();
}

function syncDraftTextFromEditor() {
  if (!state.draft || state.draft.committed) return;
  if (commentEditorTa) state.draft.text = commentEditorTa.value;
}

function draftText() {
  return trimText(state.draft?.text ?? commentEditorTa?.value ?? "");
}

async function settleDraft() {
  if (!state.draft || state.draft.committed) return;
  clearTimeout(draftSaveTimer);
  draftSaveTimer = null;
  if (draftText()) await onDraftEditorInputSave();
  else clearDraft();
}

function settleDraftSync() {
  if (!state.draft || state.draft.committed) return;
  clearTimeout(draftSaveTimer);
  draftSaveTimer = null;
  if (draftText()) void onDraftEditorInputSave();
  else clearDraft();
}

function editorIsOpen() {
  return (
    !commentEditorEl?.hidden
    || (state.draft && !state.draft.committed)
    || Boolean(state.pendingNote)
    || Boolean(state.focusId)
  );
}

async function dismissEditorFromViewerBackground() {
  if (state.draft && !state.draft.committed) {
    syncDraftTextFromEditor();
    if (draftText()) await onDraftEditorInputSave();
    else clearDraft();
    return;
  }
  if (state.pendingNote || state.focusId) {
    await dismissComment();
    return;
  }
  if (!commentEditorEl?.hidden) closeCommentEditor();
}

document.addEventListener("click", (e) => {
  if (!ctxMenu.hidden && !ctxMenu.contains(e.target)) hideCtx();
  if (!state.draft || state.draft.committed) return;
  if (e.target.closest("#comment-editor")) return;
  if (e.target.closest(".comment-card")) return;
  if (e.target.closest("#viewer")) return;
  if (e.target.closest("#comments-pane")) return;
  syncDraftTextFromEditor();
  if (draftText()) void settleDraft();
  else clearDraft();
});

document.addEventListener("mousedown", (e) => {
  if (e.button !== 0) return;
  if (e.target.closest("#comment-editor")) return;
  if (e.target.closest(".comment-card.draft")) return;
  if (e.target.closest(".comment-card:not(.draft)")) return;
  if (e.target.closest(".highlight-group")) return;
  if (e.target.closest(".pdf-link")) return;

  const pageEl = e.target.closest(".page");
  if (pageEl) {
    const pageIndex = Number(pageEl.dataset.page);
    const meta = pageMeta(pageIndex);
    if (meta) {
      const onText = spanIdAtClient(meta, pageIndex, e.clientX, e.clientY, { strict: true }) != null;
      if (!onText && editorIsOpen()) {
        e.preventDefault();
        void dismissEditorFromViewerBackground();
      }
    }
    return;
  }

  if (e.target.closest("#viewer") && editorIsOpen()) {
    void dismissEditorFromViewerBackground();
    return;
  }

  if (state.pendingNote) {
    dismissComment().catch((err) => toast(err.message || "Could not save comment"));
  }
});

function updateDocMeta() {
  if (!state.doc) return;
  const metaEl = $("#doc-meta");
  if (!state.doc.open) {
    metaEl.textContent = "No PDF open";
    metaEl.title = "";
    return;
  }
  const unsaved = hasUnsavedChanges() ? " · unsaved" : "";
  if (editingInPlace()) {
    metaEl.textContent = `${state.doc.pages} p · ${basename(state.doc.source || state.doc.name)}${unsaved}`;
  } else {
    const saveName = basename(state.doc.save_path);
    const srcName = basename(state.doc.source || state.doc.name);
    const sameFolder = dirname(state.doc.save_path) === dirname(state.doc.source || state.doc.save_path);
    metaEl.textContent = sameFolder
      ? `${state.doc.pages} p · ${saveName} beside ${srcName}${unsaved}`
      : `${state.doc.pages} p · ${saveName} · ${dirname(state.doc.save_path)}${unsaved}`;
  }
  metaEl.title = state.doc.save_path;
}

function hasUnsavedChanges() {
  if (state.savePending > 0) return true;
  if (state.localDirty) return true;
  if (state.doc?.unsaved) return true;
  if (state.draft && trimText(state.draft.text)) return true;
  if (state.pendingNote) {
    const ann = state.annotations.get(state.pendingNote.id);
    if (ann && state.pendingNote.ta.value !== ann.content) return true;
  }
  return false;
}

function confirmUnsaved(actionLabel) {
  if (!hasUnsavedChanges()) return true;
  return window.confirm(
    `You have unsaved changes.\n\n${actionLabel} anyway? Unsaved work may be lost.`,
  );
}

function populateReviewers() {
  reviewerListEl.innerHTML = "";
  for (const name of state.doc.reviewers || []) {
    const opt = document.createElement("option");
    opt.value = name;
    reviewerListEl.appendChild(opt);
  }
}

function setServerRevision(rev) {
  if (rev != null) state.serverRevision = rev;
}

function applyServerRevision(rev) {
  if (rev != null && rev > state.serverRevision) state.serverRevision = rev;
}

function broadcastSync() {
  if (!syncChannel || !state.doc?.save_path) return;
  syncChannel.postMessage({
    tabId: state.tabId,
    save_path: state.doc.save_path,
    revision: state.serverRevision,
  });
}

async function withSave(fn) {
  state.savePending += 1;
  try {
    const result = await fn();
    applyServerRevision(result?.revision);
    broadcastSync();
    return result;
  } finally {
    state.savePending -= 1;
  }
}

function loadCustomPalette() {
  try {
    const raw = localStorage.getItem(LS_CUSTOM_PALETTE);
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object") return {};
    const out = {};
    for (const [name, hex] of Object.entries(parsed)) {
      if (typeof hex === "string" && /^#[0-9a-fA-F]{6}$/.test(hex)) {
        out[name.startsWith("#") ? name.toLowerCase() : name] = hex.toLowerCase();
      }
    }
    return out;
  } catch (_) {
    return {};
  }
}

function saveCustomPalette(palette) {
  localStorage.setItem(LS_CUSTOM_PALETTE, JSON.stringify(palette));
}

function mergedPalette(basePalette) {
  return { ...(basePalette || {}), ...loadCustomPalette() };
}

function activeColorName() {
  if (state.draft && !state.draft.committed) return state.draft.color;
  const id = state.focusId ?? state.pendingNote?.id;
  if (id != null && state.annotations.has(id)) {
    return state.annotations.get(id).color;
  }
  return state.color;
}

function updatePaletteSelection(name) {
  paletteEl?.querySelectorAll(".swatch[data-color]").forEach((swatch) => {
    swatch.setAttribute(
      "aria-checked",
      swatch.dataset.color === name ? "true" : "false",
    );
  });
}

function setCommentChromeColor(hex) {
  if (commentEditorEl) commentEditorEl.style.setProperty("--comment-color", hex);
  const id = state.focusId ?? state.pendingNote?.id;
  if (id != null) {
    commentsListEl
      .querySelector(`.comment-card[data-id="${id}"]`)
      ?.style.setProperty("--comment-color", hex);
  }
  if (state.draft && !state.draft.committed) {
    commentsListEl
      .querySelector(".comment-card.draft")
      ?.style.setProperty("--comment-color", hex);
  }
}

async function applyPaletteColor(name) {
  state.color = name;
  updatePaletteSelection(name);
  if (state.draft && !state.draft.committed) {
    state.draft.color = name;
    const meta = pageMeta(state.draft.pageIndex);
    if (meta) renderDraftOverlay(meta, state.draft.rects);
    setCommentChromeColor(colorHex(name));
    return;
  }
  const id = state.focusId ?? state.pendingNote?.id;
  if (id != null && state.annotations.has(id)) {
    const updated = await patchAnnotation(id, { color: name }, { quiet: true });
    setCommentChromeColor(updated.hex);
    updatePaletteSelection(updated.color);
  }
}

function buildPalette(palette) {
  const merged = mergedPalette(palette);
  const current = activeColorName();
  paletteEl.innerHTML = "";
  for (const [name, hex] of Object.entries(merged)) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "swatch";
    btn.dataset.color = name;
    btn.style.background = hex;
    btn.title = name.startsWith("#") ? `Custom ${name}` : name;
    btn.setAttribute("role", "radio");
    btn.setAttribute("aria-checked", name === current ? "true" : "false");
    btn.addEventListener("click", () => {
      void applyPaletteColor(name);
    });
    paletteEl.appendChild(btn);
  }

  const addBtn = document.createElement("button");
  addBtn.type = "button";
  addBtn.className = "swatch swatch-add";
  addBtn.title = "Add custom colour";
  addBtn.setAttribute("aria-label", "Add custom colour");
  addBtn.textContent = "+";

  const colorInput = document.createElement("input");
  colorInput.type = "color";
  colorInput.className = "palette-color-input";
  colorInput.value = "#7eb8ff";
  addBtn.addEventListener("click", () => colorInput.click());
  colorInput.addEventListener("change", () => {
    const hex = (colorInput.value || "#7eb8ff").toLowerCase();
    const custom = loadCustomPalette();
    custom[hex] = hex;
    saveCustomPalette(custom);
    buildPalette(state.doc?.palette || {});
    void applyPaletteColor(hex);
  });

  paletteEl.appendChild(addBtn);
  paletteEl.appendChild(colorInput);
}

function spanRange(a, b) {
  const [lo, hi] = a <= b ? [a, b] : [b, a];
  const ids = [];
  for (let i = lo; i <= hi; i += 1) ids.push(i);
  return ids;
}

function spanRangeOrdered(spans, idA, idB) {
  if (!spans?.length) return [];
  const ia = spans.findIndex((s) => s.id === idA);
  const ib = spans.findIndex((s) => s.id === idB);
  if (ia < 0 && ib < 0) return [];
  if (ia < 0) return [spans[ib].id];
  if (ib < 0) return [spans[ia].id];
  const lo = Math.min(ia, ib);
  const hi = Math.max(ia, ib);
  return spans.slice(lo, hi + 1).map((s) => s.id);
}

function clientToPdf(meta, pageIndex, clientX, clientY) {
  const rect = meta.pageEl.getBoundingClientRect();
  if (rect.width <= 0 || rect.height <= 0) return { x: 0, y: 0 };
  const pageW = state.doc.page_sizes[pageIndex]?.width || rect.width;
  const pageH = state.doc.page_sizes[pageIndex]?.height || rect.height;
  return {
    x: ((clientX - rect.left) / rect.width) * pageW,
    y: ((clientY - rect.top) / rect.height) * pageH,
  };
}

function spanIdAtClient(meta, pageIndex, clientX, clientY, { strict = false } = {}) {
  const { x, y } = clientToPdf(meta, pageIndex, clientX, clientY);
  let bestId = null;
  let bestArea = Infinity;
  for (const sp of meta.spans) {
    const [x0, y0, x1, y1] = sp.bbox;
    if (x < x0 - 1.5 || x > x1 + 1.5 || y < y0 - 1.5 || y > y1 + 1.5) continue;
    const area = (x1 - x0) * (y1 - y0);
    if (area < bestArea) {
      bestArea = area;
      bestId = sp.id;
    }
  }
  if (bestId != null) return bestId;
  if (strict) return null;
  let nearestId = meta.spans[0]?.id ?? null;
  let nearestDist = Infinity;
  for (const sp of meta.spans) {
    const [x0, y0, x1, y1] = sp.bbox;
    const dx = x < x0 ? x0 - x : x > x1 ? x - x1 : 0;
    const dy = y < y0 ? y0 - y : y > y1 ? y - y1 : 0;
    const dist = dx * dx + dy * dy;
    if (dist < nearestDist) {
      nearestDist = dist;
      nearestId = sp.id;
    }
  }
  if (nearestDist > SPAN_PICK_MAX_DIST * SPAN_PICK_MAX_DIST) return null;
  return nearestId;
}

function selectionOverlapsOthers(pageIndex, spanIds, exceptId = null) {
  const meta = pageMeta(pageIndex);
  if (!meta || !spanIds.length) return false;
  const rects = mergeLineRects(meta.spans, spanIds);
  return [...state.annotations.values()].some(
    (ann) => ann.page === pageIndex
      && ann.id !== exceptId
      && ann.rects.some((ar) => rects.some((r) => rectsOverlap(ar, r))),
  );
}

function spanIdsFromAnnotation(meta, ann) {
  return meta.spans
    .filter((sp) => ann.rects.some((r) => rectsOverlap(sp.bbox, r)))
    .map((sp) => sp.id);
}

function resizeSpanIds(meta, anchorId, focusId) {
  return spanRangeOrdered(meta.spans, anchorId, focusId);
}

function spanIdsEqual(a, b) {
  if (a.length !== b.length) return false;
  for (let i = 0; i < a.length; i += 1) {
    if (a[i] !== b[i]) return false;
  }
  return true;
}

function updateSelectionOverlay(sel, focusId) {
  const ids = spanRangeOrdered(sel.meta.spans, sel.anchorId, focusId);
  if (selectionOverlapsOthers(sel.pageIndex, ids)) return;
  sel.meta._dragSpanIds = ids;
  sel.focusId = focusId;
  renderDraftOverlay(sel.meta, mergeLineRects(sel.meta.spans, ids));
}

function updateExtendPreview(gesture, focusId) {
  const ids = resizeSpanIds(gesture.meta, gesture.anchorId, focusId);
  if (!ids.length) return;
  if (selectionOverlapsOthers(gesture.pageIndex, ids, gesture.annId)) return;
  gesture.previewSpanIds = ids;
  state.extendPreview = {
    annId: gesture.annId,
    pageIndex: gesture.pageIndex,
    spanIds: ids,
  };
  renderHighlights(gesture.pageIndex);
}

function setSelectingUi(active, pageEl = null) {
  for (const meta of state.pages.values()) {
    meta.pageEl?.classList.toggle("is-selecting", active && meta.pageEl === pageEl);
  }
}

function mergeLineRects(spans, spanIds) {
  const chosen = spanIds.map((id) => spans[id]).filter(Boolean);
  if (!chosen.length) return [];
  const ordered = [...chosen].sort((a, b) => a.bbox[1] - b.bbox[1] || a.bbox[0] - b.bbox[0]);
  const lines = [];
  for (const sp of ordered) {
    const y0 = sp.bbox[1];
    let placed = false;
    for (const line of lines) {
      if (Math.abs(y0 - line[0].bbox[1]) <= LINE_Y_TOL) {
        line.push(sp);
        placed = true;
        break;
      }
    }
    if (!placed) lines.push([sp]);
  }
  return lines.map((line) => [
    Math.min(...line.map((s) => s.bbox[0])),
    Math.min(...line.map((s) => s.bbox[1])),
    Math.max(...line.map((s) => s.bbox[2])),
    Math.max(...line.map((s) => s.bbox[3])),
  ]);
}

function annotationSortKey(ann) {
  const rects = ann.rects || [[0, 0, 0, 0]];
  return [
    ann.page,
    Math.min(...rects.map((r) => r[1])),
    Math.min(...rects.map((r) => r[0])),
  ];
}

function draftSortKey(draft) {
  return [
    draft.pageIndex,
    Math.min(...draft.rects.map((r) => r[1])),
    Math.min(...draft.rects.map((r) => r[0])),
  ];
}

function compareSortKeys(a, b) {
  for (let i = 0; i < 3; i += 1) {
    if (a[i] !== b[i]) return a[i] - b[i];
  }
  return 0;
}

function rectsOverlap(a, b, tol = 1) {
  return !(
    a[2] < b[0] - tol
    || b[2] < a[0] - tol
    || a[3] < b[1] - tol
    || b[3] < a[1] - tol
  );
}

function autosizeCommentEditorTa() {
  if (!commentEditorTa) return;
  commentEditorTa.style.height = "auto";
  const next = Math.min(320, Math.max(168, commentEditorTa.scrollHeight));
  commentEditorTa.style.height = `${next}px`;
}

function positionCommentEditor(anchorCard) {
  if (!commentEditorPanelEl || !commentsPaneEl) return;
  const paneRect = commentsPaneEl.getBoundingClientRect();
  const anchorRect = anchorCard?.getBoundingClientRect();
  const margin = 14;
  const chrome = 96 + 44;
  const panelWidth = Math.min(500, Math.max(400, paneRect.width + 140));
  const left = Math.max(margin, paneRect.left - (panelWidth - paneRect.width) + 4);
  const panelHeight = commentEditorPanelEl.offsetHeight || 360;
  let top = anchorRect
    ? anchorRect.top - 6
    : (window.innerHeight - panelHeight) / 2;
  const maxTop = window.innerHeight - margin - panelHeight;
  top = Math.max(chrome + margin, Math.min(top, maxTop));
  commentEditorPanelEl.style.width = `${panelWidth}px`;
  commentEditorPanelEl.style.left = `${left}px`;
  commentEditorPanelEl.style.top = `${top}px`;
}

function bindCommentEditorReposition(anchorCard) {
  if (state.commentEditorReposition) return;
  state.commentEditorReposition = () => positionCommentEditor(anchorCard);
  window.addEventListener("resize", state.commentEditorReposition);
  commentsListEl?.addEventListener("scroll", state.commentEditorReposition, { passive: true });
}

function unbindCommentEditorReposition() {
  if (!state.commentEditorReposition) return;
  window.removeEventListener("resize", state.commentEditorReposition);
  commentsListEl?.removeEventListener("scroll", state.commentEditorReposition);
  state.commentEditorReposition = null;
}

function closeCommentEditor() {
  if (!commentEditorEl || commentEditorEl.hidden) return;
  if (state.draft && !state.draft.committed) syncDraftTextFromEditor();
  unbindCommentEditorReposition();
  commentEditorEl.hidden = true;
  commentEditorEl.setAttribute("aria-hidden", "true");
  for (const card of document.querySelectorAll(".comment-card.editor-open")) {
    card.classList.remove("editor-open");
  }
  if (commentEditorTa && !(state.draft && !state.draft.committed)) {
    commentEditorTa.value = "";
    commentEditorTa.style.height = "";
  }
  state.commentEditor = null;
}

function isCommentEditorActive() {
  return Boolean(commentEditorTa && commentEditorEl && !commentEditorEl.hidden
    && document.activeElement === commentEditorTa);
}

function editorValueFor(ann) {
  if (
    state.pendingNote?.id === ann.id
    && state.localDirty
    && state.pendingNote.ta
  ) {
    return state.pendingNote.ta.value;
  }
  return ann.content ?? "";
}

function openCommentEditor({ mode, anchorCard, color, title, meta, quote, value, placeholder, foot, onInput, onKeydown }) {
  if (!commentEditorEl || !commentEditorTa) return;
  if (mode === "draft") syncDraftTextFromEditor();
  const editorKey = mode === "draft" ? "draft" : String(state.focusId ?? title);
  const same = state.commentEditor?.mode === mode && state.commentEditor?.key === editorKey;
  const keepTyping = same && document.activeElement === commentEditorTa;
  const text = keepTyping
    ? commentEditorTa.value
    : (mode === "draft" ? (state.draft?.text ?? value ?? "") : (value ?? ""));
  const selStart = keepTyping ? commentEditorTa.selectionStart : text.length;
  const selEnd = keepTyping ? commentEditorTa.selectionEnd : text.length;

  for (const card of document.querySelectorAll(".comment-card.editor-open")) {
    card.classList.remove("editor-open");
  }
  anchorCard?.classList.add("editor-open");

  commentEditorEl.style.setProperty("--comment-color", color);
  commentEditorTitleEl.textContent = title;
  commentEditorMetaEl.textContent = meta;
  commentEditorQuoteEl.textContent = quote;
  commentEditorFootEl.textContent = foot;
  commentEditorTa.placeholder = placeholder;
  commentEditorTa.value = text;
  commentEditorTa.oninput = onInput ?? null;
  commentEditorTa.onkeydown = onKeydown ?? null;
  autosizeCommentEditorTa();

  commentEditorEl.hidden = false;
  commentEditorEl.setAttribute("aria-hidden", "false");
  state.commentEditor = { mode, key: editorKey, anchorCard };

  window.requestAnimationFrame(() => {
    autosizeCommentEditorTa();
    positionCommentEditor(anchorCard);
    bindCommentEditorReposition(anchorCard);
    if (!keepTyping) {
      commentEditorTa.focus();
      commentEditorTa.setSelectionRange(selStart, selEnd);
    }
  });

  if (mode === "draft") state.draft.ta = commentEditorTa;
  return commentEditorTa;
}

function syncCommentEditor() {
  if (state.draft && !state.draft.committed) {
    syncDraftTextFromEditor();
    let card = commentsListEl.querySelector(".comment-card.draft");
    if (!card) {
      renderCommentsPane();
      return;
    }
    const ta = openCommentEditor({
      mode: "draft",
      anchorCard: card,
      color: colorHex(state.draft.color),
      title: "New comment",
      meta: `p.${state.draft.pageIndex + 1}`,
      quote: excerptFor({ page: state.draft.pageIndex, rects: state.draft.rects }),
      value: state.draft.text ?? "",
      placeholder: "Write your comment…",
      foot: "Autosaves as you type · Esc saves · Shift+↵ new line",
      onInput: () => {
        syncDraftTextFromEditor();
        autosizeCommentEditorTa();
      },
      onKeydown: onDraftEditorKeydown,
    });
    state.draft.ta = ta;
    card.scrollIntoView({ block: "nearest", behavior: "auto" });
    return;
  }

  if (state.focusId && state.annotations.has(state.focusId)) {
    const ann = state.annotations.get(state.focusId);
    const card = commentsListEl.querySelector(`.comment-card[data-id="${state.focusId}"]`);
    if (!card || !ann) {
      closeCommentEditor();
      return;
    }
    const ta = openCommentEditor({
      mode: "ann",
      anchorCard: card,
      color: ann.hex,
      title: ann.title || state.doc?.reviewer || "Review",
      meta: `p.${ann.page + 1}`,
      quote: excerptFor(ann),
      value: editorValueFor(ann),
      placeholder: trimText(ann.content) ? "Comment" : "Empty — Backspace/Delete removes",
      foot: "Autosaves as you type · Esc saves · Shift+↵ new line",
      onInput: state.pendingNote?.onInput,
      onKeydown: state.pendingNote?.onKeydown,
    });
    if (state.pendingNote) state.pendingNote.ta = ta;
    return;
  }

  closeCommentEditor();
}

async function onDraftEditorInputSave() {
  if (!state.draft || state.draft.committed || !commentEditorTa) return;
  syncDraftTextFromEditor();
  if (draftText() === "") return;
  state.draft.committed = true;
  const { pageIndex: page, spanIds: ids, color, text } = state.draft;
  const content = text ?? commentEditorTa.value;
  try {
    const created = await withSave(() => api("/api/annotations", {
      method: "POST",
      body: JSON.stringify({ page, span_ids: ids, color, content }),
    }));
    state.annotations.set(created.id, created);
    if (!state.historyApplying) {
      pushHistory(makeCreateHistoryEntry(cloneSnapshot(created), created.id));
    }
    state.draft = null;
    clearPreviewLayers();
    renderAllHighlights();
    await refreshPageBitmap(page);
    syncDocFlags(await api("/api/document"));
    emergencyBackup();
    const savePath = created.save_path || state.doc?.save_path;
    if (savePath && state.doc) state.doc.save_path = savePath;
    updateDocMeta();
    toast(`Comment saved · ${basename(savePath)}`, 2800);
    const caret = commentEditorTa.selectionStart;
    focusAnnotation(created.id, { center: false, edit: true, scrollCard: false, behavior: "auto" });
    requestAnimationFrame(() => {
      if (!commentEditorTa) return;
      commentEditorTa.focus();
      const end = commentEditorTa.value.length;
      commentEditorTa.setSelectionRange(Math.min(caret, end), Math.min(caret, end));
    });
  } catch (err) {
    state.draft.committed = false;
    syncDraftTextFromEditor();
    syncCommentEditor();
    toast(err.message || "Could not save highlight");
  }
}

function onDraftEditorKeydown(ev) {
  if (ev.key === "Escape") {
    ev.preventDefault();
    clearTimeout(draftSaveTimer);
    draftSaveTimer = null;
    if (draftText()) void onDraftEditorInputSave();
    else clearDraft();
  }
}

commentEditorTa?.addEventListener("input", () => {
  if (state.draft && !state.draft.committed) syncDraftTextFromEditor();
  autosizeCommentEditorTa();
  if (!state.draft || state.draft.committed || !draftText()) return;
  clearTimeout(draftSaveTimer);
  draftSaveTimer = setTimeout(() => {
    draftSaveTimer = null;
    void onDraftEditorInputSave();
  }, 400);
});

function focusDraftNote() {
  syncCommentEditor();
}

function sortedAnnotations() {
  return [...state.annotations.values()].sort((a, b) => {
    const cmp = compareSortKeys(annotationSortKey(a), annotationSortKey(b));
    return cmp !== 0 ? cmp : a.id - b.id;
  });
}

function pruneCommentSelection() {
  for (const id of [...state.selectedCommentIds]) {
    if (!state.annotations.has(id)) state.selectedCommentIds.delete(id);
  }
  if (state.lastSelectedCommentId != null && !state.annotations.has(state.lastSelectedCommentId)) {
    state.lastSelectedCommentId = null;
  }
}

function clearCommentSelection() {
  state.selectedCommentIds.clear();
  state.lastSelectedCommentId = null;
  updateCommentSelectionUi();
}

function toggleCommentSelection(id, { additive = false, range = false } = {}) {
  const sorted = sortedAnnotations().map((ann) => ann.id);
  if (range && state.lastSelectedCommentId != null) {
    const ia = sorted.indexOf(state.lastSelectedCommentId);
    const ib = sorted.indexOf(id);
    if (ia >= 0 && ib >= 0) {
      const lo = Math.min(ia, ib);
      const hi = Math.max(ia, ib);
      if (!additive) state.selectedCommentIds.clear();
      for (let i = lo; i <= hi; i += 1) state.selectedCommentIds.add(sorted[i]);
    }
  } else if (additive) {
    if (state.selectedCommentIds.has(id)) state.selectedCommentIds.delete(id);
    else state.selectedCommentIds.add(id);
  } else {
    state.selectedCommentIds.clear();
    state.selectedCommentIds.add(id);
  }
  state.lastSelectedCommentId = id;
  updateCommentSelectionUi();
}

function updateCommentSelectionUi() {
  pruneCommentSelection();
  const n = state.selectedCommentIds.size;
  if (commentsSelectionBarEl) commentsSelectionBarEl.hidden = n === 0;
  if (commentsSelectionCountEl) {
    commentsSelectionCountEl.textContent = `${n} selected`;
  }
  for (const card of commentsListEl.querySelectorAll(".comment-card[data-id]")) {
    const id = Number(card.dataset.id);
    const picked = state.selectedCommentIds.has(id);
    card.classList.toggle("selected", picked);
    const pick = card.querySelector(".comment-pick");
    if (pick) pick.checked = picked;
  }
  renderAllHighlights();
}

function applyZoom() {
  const z = state.zoom;
  if (USE_CSS_ZOOM) {
    pagesEl.style.zoom = String(z);
    pagesEl.style.transform = "";
    pagesViewportEl.style.height = "";
  } else {
    pagesEl.style.zoom = "";
    pagesEl.style.transform = `scale(${z})`;
    pagesEl.style.transformOrigin = "0 0";
    if (state.pagesTotalHeight) {
      pagesViewportEl.style.height = `${state.pagesTotalHeight * z}px`;
    }
  }
  if (zoomLabelEl) zoomLabelEl.textContent = `${Math.round(z * 100)}%`;
}

function zoomContentPoint(clientX, clientY) {
  const viewerRect = viewerEl.getBoundingClientRect();
  return {
    x: (viewerEl.scrollLeft + clientX - viewerRect.left) / state.zoom,
    y: (viewerEl.scrollTop + clientY - viewerRect.top) / state.zoom,
  };
}

function scrollToContentPoint(clientX, clientY, contentX, contentY, zoom) {
  const viewerRect = viewerEl.getBoundingClientRect();
  const localX = clientX - viewerRect.left;
  const localY = clientY - viewerRect.top;
  viewerEl.scrollLeft = contentX * zoom - localX;
  viewerEl.scrollTop = contentY * zoom - localY;
}

function setZoom(next, anchorX, anchorY, { deferEnd = true } = {}) {
  const prev = state.zoom;
  const clamped = Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, next));
  if (Math.abs(clamped - prev) < 0.0001) return;

  if (deferEnd) markZoomGestureActive();

  if (viewerEl && anchorX != null && anchorY != null) {
    const focus = zoomContentPoint(anchorX, anchorY);
    state.zoom = clamped;
    applyZoom();
    scrollToContentPoint(anchorX, anchorY, focus.x, focus.y, clamped);
    if (deferEnd) markZoomGestureEnd();
    scheduleNavStateReplace();
    return;
  }

  state.zoom = clamped;
  applyZoom();
  if (deferEnd) markZoomGestureEnd();
  scheduleNavStateReplace();
}

function normalizeWheelDelta(deltaY, deltaMode) {
  let dy = deltaY;
  if (deltaMode === 1) dy *= 16;
  else if (deltaMode === 2) dy *= viewerEl?.clientHeight || 800;
  return dy;
}

function wheelStepFactor(deltaY, deltaMode) {
  const dy = normalizeWheelDelta(deltaY, deltaMode);
  const change = Math.max(-WHEEL_ZOOM_STEP_MAX, Math.min(WHEEL_ZOOM_STEP_MAX, -dy * WHEEL_ZOOM_GAIN));
  return 1 + change;
}

function markZoomGestureActive() {
  state.zooming = true;
  pagesEl.style.willChange = "transform";
  clearTimeout(state.zoomEndTimer);
}

function markZoomGestureEnd() {
  clearTimeout(state.zoomEndTimer);
  state.zoomEndTimer = setTimeout(() => {
    state.zooming = false;
    pagesEl.style.willChange = "";
  }, 180);
}

function zoomBy(factor, anchorX, anchorY, opts) {
  setZoom(state.zoom * factor, anchorX, anchorY, opts);
}

function touchDistance(touches) {
  const dx = touches[0].clientX - touches[1].clientX;
  const dy = touches[0].clientY - touches[1].clientY;
  return Math.hypot(dx, dy);
}

function wireZoomControls() {
  applyZoom();

  $("#zoom-in").addEventListener("click", () => {
    const r = viewerEl.getBoundingClientRect();
    zoomBy(ZOOM_STEP, r.left + r.width / 2, r.top + r.height / 2);
  });
  $("#zoom-out").addEventListener("click", () => {
    const r = viewerEl.getBoundingClientRect();
    zoomBy(1 / ZOOM_STEP, r.left + r.width / 2, r.top + r.height / 2);
  });
  $("#zoom-reset").addEventListener("click", () => {
    const r = viewerEl.getBoundingClientRect();
    setZoom(1, r.left + r.width / 2, r.top + r.height / 2, { deferEnd: false });
  });

  viewerEl.addEventListener("wheel", (ev) => {
    if (!ev.ctrlKey && !ev.metaKey) return;
    if (state.gestureActive) return;
    ev.preventDefault();
    zoomBy(wheelStepFactor(ev.deltaY, ev.deltaMode), ev.clientX, ev.clientY);
  }, { passive: false });

  viewerEl.addEventListener("gesturestart", (ev) => {
    ev.preventDefault();
    state.gestureActive = true;
    state.gestureBaseZoom = state.zoom;
    markZoomGestureActive();
  }, { passive: false });

  viewerEl.addEventListener("gesturechange", (ev) => {
    ev.preventDefault();
    setZoom(state.gestureBaseZoom * ev.scale, ev.clientX, ev.clientY);
  }, { passive: false });

  viewerEl.addEventListener("gestureend", (ev) => {
    ev.preventDefault();
    state.gestureActive = false;
    markZoomGestureEnd();
  }, { passive: false });

  viewerEl.addEventListener("touchstart", (ev) => {
    if (ev.touches.length === 2) {
      state.pinch = {
        distance: touchDistance(ev.touches),
        zoom: state.zoom,
        x: (ev.touches[0].clientX + ev.touches[1].clientX) / 2,
        y: (ev.touches[0].clientY + ev.touches[1].clientY) / 2,
      };
    }
  }, { passive: true });

  viewerEl.addEventListener("touchmove", (ev) => {
    if (!state.pinch || ev.touches.length !== 2) return;
    ev.preventDefault();
    markZoomGestureActive();
    const dist = touchDistance(ev.touches);
    const x = (ev.touches[0].clientX + ev.touches[1].clientX) / 2;
    const y = (ev.touches[0].clientY + ev.touches[1].clientY) / 2;
    setZoom(state.pinch.zoom * (dist / state.pinch.distance), x, y);
  }, { passive: false });

  viewerEl.addEventListener("touchend", () => {
    state.pinch = null;
    markZoomGestureEnd();
  });
}

function annotationMidY(ann) {
  const ys = ann.rects.flatMap((r) => [r[1], r[3]]);
  return (Math.min(...ys) + Math.max(...ys)) / 2;
}

function centerAnnotation(ann, { behavior = "smooth" } = {}) {
  if (!ann?.rects?.length) return;
  return navigateToPdfDest(ann.page, annotationMidY(ann), { behavior });
}

function pageRenderHeight(index) {
  return state.doc.page_sizes[index].height * state.doc.render_scale;
}

function pageRenderWidth(index) {
  return state.doc.page_sizes[index].width * state.doc.render_scale;
}

function buildPageLayout() {
  if (!state.doc?.page_sizes?.length) return;
  let y = PAGE_PAD_TOP;
  state.pageOffsets = [];
  for (let i = 0; i < state.doc.page_sizes.length; i += 1) {
    state.pageOffsets[i] = y;
    y += pageRenderHeight(i) + PAGE_GAP;
  }
  state.pagesTotalHeight = y + PAGE_PAD_BOTTOM - PAGE_GAP;
  pagesEl.style.position = "relative";
  pagesEl.style.minHeight = `${state.pagesTotalHeight}px`;
  applyZoom();
}

function pagesInViewport() {
  const zoom = state.zoom || 1;
  const viewTop = viewerEl.scrollTop;
  const viewBottom = viewTop + viewerEl.clientHeight;
  const n = state.doc.pages;
  let first = 0;
  let last = n - 1;
  for (let i = 0; i < n; i += 1) {
    const top = state.pageOffsets[i] * zoom;
    const bottom = top + (pageRenderHeight(i) + PAGE_GAP) * zoom;
    if (bottom >= viewTop) {
      first = i;
      break;
    }
  }
  for (let i = first; i < n; i += 1) {
    const top = state.pageOffsets[i] * zoom;
    if (top > viewBottom) {
      last = Math.max(first, i - 1);
      break;
    }
  }
  return [
    Math.max(0, first - PAGE_STUB_BUFFER),
    Math.min(n - 1, last + PAGE_STUB_BUFFER),
  ];
}

function isPageMounted(index) {
  const meta = state.pages.get(index);
  return Boolean(meta?.pageEl?.isConnected);
}

function invalidatePageIfDetached(index) {
  const meta = state.pages.get(index);
  if (meta && !meta.pageEl?.isConnected) {
    state.pages.delete(index);
    return true;
  }
  return false;
}

function canUnloadPage(index) {
  if (state.loadingPages.has(index)) return false;
  if (state.draft?.pageIndex === index) return false;
  if (state.focusId != null) {
    const ann = state.annotations.get(state.focusId);
    if (ann?.page === index) return false;
  }
  return true;
}

function cancelStubRemoval(index) {
  const timer = state.pendingStubRemoval.get(index);
  if (timer == null) return;
  clearTimeout(timer);
  state.pendingStubRemoval.delete(index);
}

function scheduleStubRemoval(index) {
  if (state.pendingStubRemoval.has(index)) return;
  const timer = setTimeout(() => {
    state.pendingStubRemoval.delete(index);
    if (!state.pageStubs.has(index)) return;
    const [lo, hi] = pagesInViewport();
    if (index >= lo && index <= hi) return;
    removePageStub(index);
  }, STUB_UNLOAD_DELAY_MS);
  state.pendingStubRemoval.set(index, timer);
}

function ensurePageStub(index) {
  cancelStubRemoval(index);
  if (state.pageStubs.has(index)) return state.pageStubs.get(index);
  const el = document.createElement("section");
  el.className = "page placeholder";
  el.dataset.page = String(index);
  el.style.position = "absolute";
  el.style.left = "50%";
  el.style.transform = "translateX(-50%)";
  el.style.top = `${state.pageOffsets[index]}px`;
  el.style.width = `${pageRenderWidth(index)}px`;
  el.style.minHeight = `${pageRenderHeight(index)}px`;
  const badge = document.createElement("div");
  badge.className = "page-badge";
  badge.textContent = `Page ${index + 1}`;
  el.appendChild(badge);
  pagesEl.appendChild(el);
  state.pageStubs.set(index, el);
  state.pageObserver?.observe(el);
  return el;
}

function unloadPage(index) {
  const meta = state.pages.get(index);
  if (!meta) return;
  state.pages.delete(index);
  const el = meta.pageEl;
  if (!el?.isConnected) return;
  el.className = "page placeholder";
  el.replaceChildren();
  const badge = document.createElement("div");
  badge.className = "page-badge";
  badge.textContent = `Page ${index + 1}`;
  el.appendChild(badge);
}

function removePageStub(index) {
  if (!canUnloadPage(index)) return;
  state.pageLoadGen.set(index, (state.pageLoadGen.get(index) || 0) + 1);
  unloadPage(index);
  const el = state.pageStubs.get(index);
  if (!el) return;
  state.pageObserver?.unobserve(el);
  el.remove();
  state.pageStubs.delete(index);
}

function pageNeedsLoad(index) {
  invalidatePageIfDetached(index);
  return !isPageMounted(index) && !state.loadingPages.has(index);
}

function requestPageLoad(index, { priority = false } = {}) {
  if (!state.doc?.pages || index < 0 || index >= state.doc.pages) return;
  if (!pageNeedsLoad(index)) return;
  if (priority) {
    state.pageLoadQueue = [index, ...state.pageLoadQueue.filter((i) => i !== index)];
  } else if (!state.pageLoadQueue.includes(index)) {
    state.pageLoadQueue.push(index);
  }
  drainPageLoadQueue();
}

function drainPageLoadQueue() {
  while (
    state.loadingPages.size < MAX_PAGE_LOADS_IN_FLIGHT
    && state.pageLoadQueue.length > 0
  ) {
    const index = state.pageLoadQueue.shift();
    if (!pageNeedsLoad(index)) continue;
    loadPage(index).catch((err) => toast(err.message || "Page load failed"));
  }
}

function repairVisiblePages() {
  const [lo, hi] = pagesInViewport();
  for (let i = lo; i <= hi; i += 1) {
    ensurePageStub(i);
    if (pageNeedsLoad(i)) requestPageLoad(i, { priority: true });
  }
}

function syncPageStubs() {
  if (!state.doc?.page_sizes?.length) return;
  if (!state.pageOffsets?.length) return;
  const [lo, hi] = pagesInViewport();
  for (let i = lo; i <= hi; i += 1) ensurePageStub(i);
  for (const index of [...state.pageStubs.keys()]) {
    if (index < lo || index > hi) {
      if (!state.zooming) scheduleStubRemoval(index);
    } else {
      cancelStubRemoval(index);
    }
  }
  repairVisiblePages();
  prefetchPages();
}

function prefetchPages() {
  if (!state.doc?.pages) return;
  const [lo, hi] = pagesInViewport();
  const want = [];
  for (let i = Math.max(0, lo - PAGE_PREFETCH); i <= Math.min(state.doc.pages - 1, hi + PAGE_PREFETCH); i += 1) {
    if (pageNeedsLoad(i)) want.push(i);
  }
  const mid = (lo + hi) / 2;
  want.sort((a, b) => Math.abs(a - mid) - Math.abs(b - mid));
  for (const idx of want) requestPageLoad(idx);
}

function scheduleStubSync() {
  if (state.stubSyncScheduled) return;
  state.stubSyncScheduled = true;
  window.requestAnimationFrame(() => {
    state.stubSyncScheduled = false;
    syncPageStubs();
  });
}

async function navigateToPdfDest(pageIndex, yPdf = 0, { behavior = "smooth" } = {}) {
  ensurePageStub(pageIndex);
  scheduleStubSync();
  if (!isPageMounted(pageIndex)) {
    await loadPage(pageIndex);
  }
  const zoom = state.zoom || 1;
  const y = (state.pageOffsets[pageIndex] + yPdf * state.doc.render_scale) * zoom;
  viewerEl.scrollTo({
    top: Math.max(0, y - viewerEl.clientHeight / 2),
    behavior,
  });
}

function viewerNavState() {
  return {
    reviewNav: true,
    scrollTop: viewerEl.scrollTop,
    scrollLeft: viewerEl.scrollLeft,
    zoom: state.zoom,
  };
}

function seedViewerNavHistory() {
  history.replaceState(viewerNavState(), "", location.href);
}

function scheduleNavStateReplace() {
  if (state.navRestoring) return;
  clearTimeout(state.navReplaceTimer);
  state.navReplaceTimer = setTimeout(() => {
    state.navReplaceTimer = null;
    if (state.navRestoring) return;
    history.replaceState(viewerNavState(), "", location.href);
  }, 180);
}

async function restoreViewerNavState(st) {
  if (!st?.reviewNav || !state.pageOffsets?.length) return;
  state.navRestoring = true;
  try {
    if (typeof st.zoom === "number") {
      state.zoom = Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, st.zoom));
      applyZoom();
    }
    const scrollTop = st.scrollTop ?? 0;
    const scrollLeft = st.scrollLeft ?? 0;
    await new Promise((resolve) => requestAnimationFrame(resolve));
    viewerEl.scrollTop = scrollTop;
    viewerEl.scrollLeft = scrollLeft;
    scheduleStubSync();
    await new Promise((resolve) => requestAnimationFrame(resolve));
    viewerEl.scrollTop = scrollTop;
    viewerEl.scrollLeft = scrollLeft;
    scheduleStubSync();
  } finally {
    state.navRestoring = false;
  }
}

function wireViewerNavHistory() {
  if (state.viewerNavBound) return;
  state.viewerNavBound = true;
  window.addEventListener("popstate", (ev) => {
    void restoreViewerNavState(ev.state);
  });
}

async function followInternalPdfLink(pageIndex, yPdf = 0) {
  history.pushState(viewerNavState(), "", location.href);
  await navigateToPdfDest(pageIndex, yPdf);
}

function openExternalLink(url, { duplicate = false } = {}) {
  const name = duplicate ? `${LINK_WINDOW_NAME}-${Date.now()}` : LINK_WINDOW_NAME;
  if (!duplicate && state.linkWindow && !state.linkWindow.closed) {
    try {
      state.linkWindow.location.href = url;
      state.linkWindow.focus();
      return state.linkWindow;
    } catch (_) {
      state.linkWindow = null;
    }
  }
  const win = window.open(url, name, LINK_WINDOW_FEATURES);
  if (!win) {
    toast("Allow pop-ups to open citation links", 3200);
    return null;
  }
  try { win.opener = null; } catch (_) { /* cross-origin */ }
  win.focus();
  if (!duplicate) state.linkWindow = win;
  return win;
}

function isStackedWorkspace() {
  return window.matchMedia("(max-width: 960px)").matches;
}

function setCommentsCollapsed(collapsed, { persist = true, sync = true } = {}) {
  state.commentsCollapsed = collapsed;
  workspaceEl?.classList.toggle("comments-collapsed", collapsed);
  if (commentsCollapseBtnEl) {
    commentsCollapseBtnEl.setAttribute("aria-expanded", String(!collapsed));
    commentsCollapseBtnEl.textContent = collapsed ? "‹" : "›";
    commentsCollapseBtnEl.title = collapsed ? "Expand comments" : "Collapse comments";
  }
  if (persist) {
    localStorage.setItem(LS_COMMENTS_COLLAPSED, collapsed ? "1" : "0");
  }
  if (sync) scheduleStubSync();
}

function restoreCommentsPaneSize() {
  const savedW = Number(localStorage.getItem(LS_COMMENTS_W));
  const savedH = Number(localStorage.getItem(LS_COMMENTS_H));
  if (savedW >= COMMENTS_W_MIN && savedW <= COMMENTS_W_MAX) {
    document.documentElement.style.setProperty("--comments-pane-w", `${savedW}px`);
  }
  if (savedH >= COMMENTS_H_MIN && savedH <= COMMENTS_H_MAX) {
    document.documentElement.style.setProperty("--comments-pane-h", `${savedH}px`);
  }
}

function wireWorkspaceLayout() {
  restoreCommentsPaneSize();
  if (localStorage.getItem(LS_COMMENTS_COLLAPSED) === "1") {
    setCommentsCollapsed(true, { sync: false });
  }

  commentsCollapseBtnEl?.addEventListener("click", () => {
    setCommentsCollapsed(!state.commentsCollapsed);
  });

  workspaceSplitterEl?.addEventListener("pointerdown", (ev) => {
    if (state.commentsCollapsed || ev.button !== 0) return;
    ev.preventDefault();
    workspaceSplitterEl.setPointerCapture(ev.pointerId);
    workspaceSplitterEl.classList.add("is-dragging");
    const stacked = isStackedWorkspace();
    const startY = ev.clientY;
    const startH = commentsPaneEl.getBoundingClientRect().height;

    const onMove = (e) => {
      const rect = workspaceEl.getBoundingClientRect();
      if (stacked) {
        const nextH = Math.round(
          Math.min(COMMENTS_H_MAX, Math.max(COMMENTS_H_MIN, startH + (e.clientY - startY))),
        );
        document.documentElement.style.setProperty("--comments-pane-h", `${nextH}px`);
      } else {
        // Comments sit on the right: width = distance from cursor to workspace edge.
        const nextW = Math.round(
          Math.min(COMMENTS_W_MAX, Math.max(COMMENTS_W_MIN, rect.right - e.clientX)),
        );
        document.documentElement.style.setProperty("--comments-pane-w", `${nextW}px`);
      }
      scheduleStubSync();
    };

    const onUp = (e) => {
      workspaceSplitterEl.classList.remove("is-dragging");
      workspaceSplitterEl.releasePointerCapture(e.pointerId);
      workspaceSplitterEl.removeEventListener("pointermove", onMove);
      workspaceSplitterEl.removeEventListener("pointerup", onUp);
      workspaceSplitterEl.removeEventListener("pointercancel", onUp);
      if (stacked) {
        const h = Math.round(commentsPaneEl.getBoundingClientRect().height);
        localStorage.setItem(LS_COMMENTS_H, String(h));
      } else {
        const w = Math.round(commentsPaneEl.getBoundingClientRect().width);
        localStorage.setItem(LS_COMMENTS_W, String(w));
      }
      scheduleStubSync();
    };

    workspaceSplitterEl.addEventListener("pointermove", onMove);
    workspaceSplitterEl.addEventListener("pointerup", onUp);
    workspaceSplitterEl.addEventListener("pointercancel", onUp);
  });

  workspaceSplitterEl?.addEventListener("keydown", (ev) => {
    if (state.commentsCollapsed) return;
    const stacked = isStackedWorkspace();
    const step = ev.shiftKey ? 40 : 16;
    let delta = 0;
    if (stacked) {
      if (ev.key === "ArrowUp") delta = -step;
      if (ev.key === "ArrowDown") delta = step;
    } else {
      if (ev.key === "ArrowLeft") delta = step;
      if (ev.key === "ArrowRight") delta = -step;
    }
    if (!delta) return;
    ev.preventDefault();
    if (stacked) {
      const h = Math.round(commentsPaneEl.getBoundingClientRect().height);
      const nextH = Math.min(COMMENTS_H_MAX, Math.max(COMMENTS_H_MIN, h + delta));
      document.documentElement.style.setProperty("--comments-pane-h", `${nextH}px`);
      localStorage.setItem(LS_COMMENTS_H, String(nextH));
    } else {
      const w = Math.round(commentsPaneEl.getBoundingClientRect().width);
      const nextW = Math.min(COMMENTS_W_MAX, Math.max(COMMENTS_W_MIN, w + delta));
      document.documentElement.style.setProperty("--comments-pane-w", `${nextW}px`);
      localStorage.setItem(LS_COMMENTS_W, String(nextW));
    }
    scheduleStubSync();
  });
}

function wireLinks(meta, links, scale) {
  meta.linkLayer.replaceChildren();
  for (const link of links) {
    const [x0, y0, x1, y1] = link.bbox;
    const a = document.createElement("a");
    a.className = "pdf-link";
    a.style.left = `${x0 * scale}px`;
    a.style.top = `${y0 * scale}px`;
    a.style.width = `${Math.max(2, (x1 - x0) * scale)}px`;
    a.style.height = `${Math.max(2, (y1 - y0) * scale)}px`;
    if (link.uri) {
      const citeLabel = link.cite != null ? `[${link.cite}] ` : "";
      a.href = link.uri;
      a.rel = "noopener noreferrer";
      a.title = `${citeLabel}${link.uri}\nOpens in new window · ⇧ for a second window`;
      a.addEventListener("click", (ev) => {
        if (ev.button !== 0) return;
        ev.preventDefault();
        ev.stopPropagation();
        openExternalLink(link.uri, { duplicate: ev.shiftKey });
      });
    } else {
      const destPage = link.page ?? 0;
      a.href = `#page-${destPage + 1}`;
      a.title = `Go to page ${destPage + 1} · browser back returns here`;
      a.addEventListener("click", (ev) => {
        if (ev.button !== 0) return;
        ev.preventDefault();
        ev.stopPropagation();
        void followInternalPdfLink(destPage, link.y ?? 0);
      });
    }
    meta.linkLayer.appendChild(a);
  }
}

function excerptFor(ann) {
  const meta = pageMeta(ann.page);
  if (!meta) return "";
  const hits = meta.spans.filter((sp) =>
    ann.rects.some(([x0, y0, x1, y1]) =>
      sp.bbox[0] >= x0 - 1 && sp.bbox[2] <= x1 + 1 && sp.bbox[1] >= y0 - 1 && sp.bbox[3] <= y1 + 1));
  const text = hits.map((h) => h.text).join("");
  if (!text) return "Highlighted text";
  return text.length > 160 ? `${text.slice(0, 160)}…` : text;
}

function buildDraftCard() {
  const card = document.createElement("article");
  card.className = "comment-card draft active";
  card.style.setProperty("--comment-color", colorHex(state.draft.color));

  const inner = document.createElement("div");
  inner.className = "comment-card-inner";

  const metaEl = document.createElement("div");
  metaEl.className = "comment-meta";
  metaEl.innerHTML = `<span>Draft</span><span>p.${state.draft.pageIndex + 1}</span>`;
  inner.appendChild(metaEl);

  const quote = document.createElement("p");
  quote.className = "comment-quote";
  quote.textContent = excerptFor({
    page: state.draft.pageIndex,
    rects: state.draft.rects,
  });
  inner.appendChild(quote);

  const hint = document.createElement("div");
  hint.className = "comment-editing-hint";
  hint.textContent = "Writing in editor…";
  inner.appendChild(hint);
  card.appendChild(inner);

  card.addEventListener("click", (ev) => {
    ev.stopPropagation();
    syncDraftTextFromEditor();
    syncCommentEditor();
    commentEditorTa?.focus();
  });

  return card;
}

function buildCommentCard(ann) {
  const editing = state.focusId === ann.id;
  const picked = state.selectedCommentIds.has(ann.id);
  const card = document.createElement("article");
  card.className = "comment-card";
  if (editing) card.classList.add("active");
  if (picked) card.classList.add("selected");
  if (editing && trimText(ann.content) === "") card.classList.add("deletable");
  card.dataset.id = String(ann.id);
  card.setAttribute("aria-selected", picked || editing ? "true" : "false");
  card.style.setProperty("--comment-color", ann.hex);

  const inner = document.createElement("div");
  inner.className = "comment-card-inner";

  const meta = document.createElement("div");
  meta.className = "comment-meta";
  const pick = document.createElement("input");
  pick.type = "checkbox";
  pick.className = "comment-pick";
  pick.checked = picked;
  pick.title = "Select comment";
  pick.setAttribute("aria-label", "Select comment");
  pick.addEventListener("click", (ev) => {
    ev.stopPropagation();
    toggleCommentSelection(ann.id, { additive: true });
  });
  const metaMain = document.createElement("div");
  metaMain.className = "comment-meta-main";
  const titleBtn = document.createElement("button");
  titleBtn.type = "button";
  titleBtn.className = "comment-locate";
  titleBtn.textContent = ann.title || state.doc?.reviewer || "Review";
  titleBtn.title = "Center highlight in document";
  titleBtn.addEventListener("click", (ev) => {
    ev.stopPropagation();
    locateAnnotation(ann.id);
  });
  const pageBtn = document.createElement("button");
  pageBtn.type = "button";
  pageBtn.className = "comment-locate";
  pageBtn.textContent = `p.${ann.page + 1}`;
  pageBtn.title = "Center highlight in document";
  pageBtn.addEventListener("click", (ev) => {
    ev.stopPropagation();
    locateAnnotation(ann.id);
  });
  metaMain.append(titleBtn, pageBtn);
  meta.append(pick, metaMain);
  inner.appendChild(meta);

  const quote = document.createElement("p");
  quote.className = "comment-quote comment-locate-hit";
  quote.textContent = excerptFor(ann);
  quote.title = "Show highlight in document";
  inner.appendChild(quote);

  if (editing) {
    const preview = document.createElement("div");
    preview.className = "comment-editing-preview";
    preview.textContent = trimText(ann.content) ? ann.content : "Empty comment";
    inner.appendChild(preview);
  } else {
    const body = document.createElement("div");
    body.className = "comment-body comment-edit-hit" + (trimText(ann.content) ? "" : " empty");
    body.textContent = trimText(ann.content) ? ann.content : "Empty comment";
    body.title = "Edit comment";
    inner.appendChild(body);
  }

  card.appendChild(inner);
  card.addEventListener("contextmenu", (ev) => openCtx(ev, ann));
  card.addEventListener("click", (ev) => {
    if (ev.target.closest(".comment-pick")) return;
    if (ev.target.closest(".comment-locate")) return;
    if (ev.metaKey || ev.ctrlKey) {
      ev.preventDefault();
      toggleCommentSelection(ann.id, { additive: true });
      return;
    }
    if (ev.shiftKey) {
      ev.preventDefault();
      toggleCommentSelection(ann.id, { range: true, additive: ev.altKey });
      return;
    }
    if (editing) {
      commentEditorTa?.focus();
      return;
    }
    if (ev.target.closest(".comment-locate-hit")) {
      ev.stopPropagation();
      settleDraftSync();
      void locateAnnotation(ann.id);
      return;
    }
    if (!ev.target.closest(".comment-edit-hit")) return;
    ev.stopPropagation();
    settleDraftSync();
    clearCommentSelection();
    focusAnnotation(ann.id, { edit: true });
  });

  return card;
}

function renderCommentsPane() {
  syncDraftTextFromEditor();
  const keepFocus = state.focusId;
  const draftOpen = state.draft && !state.draft.committed;
  if (draftOpen && commentsListEl.querySelector(".comment-card.draft")) {
    commentsCountEl.textContent = String(state.annotations.size);
    updateCommentSelectionUi();
    if (commentEditorEl?.hidden) syncCommentEditor();
    return;
  }
  state.pendingNote = null;
  commentsListEl.replaceChildren();

  const entries = [];
  if (state.draft && !state.draft.committed) {
    entries.push({ type: "draft", key: draftSortKey(state.draft) });
  }
  for (const ann of state.annotations.values()) {
    entries.push({ type: "ann", ann, key: annotationSortKey(ann) });
  }
  entries.sort((a, b) => compareSortKeys(a.key, b.key));

  if (!entries.length) {
    const empty = document.createElement("div");
    empty.className = "comments-empty";
    empty.textContent = "Select text in the document to add a comment.";
    commentsListEl.appendChild(empty);
  } else {
    for (const entry of entries) {
      if (entry.type === "draft") commentsListEl.appendChild(buildDraftCard());
      else commentsListEl.appendChild(buildCommentCard(entry.ann));
    }
  }
  commentsCountEl.textContent = String(state.annotations.size);

  if (keepFocus && state.annotations.has(keepFocus)) {
    const card = commentsListEl.querySelector(`.comment-card[data-id="${keepFocus}"]`);
    const ann = state.annotations.get(keepFocus);
    if (card && ann) {
      const editors = wireNoteEditing(ann, card);
      state.pendingNote = {
        id: keepFocus,
        ta: commentEditorTa,
        flush: editors.flush,
        cardEl: card,
        onInput: editors.onInput,
        onKeydown: editors.onKeydown,
      };
    }
  }

  syncCommentEditor();
  updateCommentSelectionUi();
}

function pageMeta(pageIndex) {
  return state.pages.get(pageIndex);
}

function colorHex(name) {
  if (!name) return "#ffea3a";
  if (name.startsWith("#")) return name;
  return mergedPalette(state.doc?.palette)[name] || "#ffea3a";
}

function paintRects(layer, rects, scale, hex, className) {
  layer.replaceChildren();
  const isDraft = className.includes("draft");
  for (const rect of rects) {
    const [x0, y0, x1, y1] = rect;
    const el = document.createElement("div");
    el.className = className;
    el.style.left = `${x0 * scale}px`;
    el.style.top = `${y0 * scale}px`;
    el.style.width = `${(x1 - x0) * scale}px`;
    el.style.height = `${(y1 - y0) * scale}px`;
    if (!isDraft) el.style.background = hex;
    layer.appendChild(el);
  }
}

function highlightRectsForRender(meta, ann, pageIndex) {
  const preview = state.extendPreview;
  if (preview && preview.annId === ann.id && preview.pageIndex === pageIndex) {
    return mergeLineRects(meta.spans, preview.spanIds);
  }
  return ann.rects;
}

function renderHighlights(pageIndex) {
  const meta = pageMeta(pageIndex);
  if (!meta) return;
  meta.annotLayer.innerHTML = "";
  for (const ann of state.annotations.values()) {
    if (ann.page !== pageIndex) continue;
    const focused = state.focusId === ann.id;
    const located = state.locateId === ann.id;
    const selected = state.selectedCommentIds.has(ann.id);
    const extending = state.extendPreview?.annId === ann.id;
    const deletable = state.pendingNote?.id === ann.id
      && trimText(state.pendingNote.ta?.value ?? ann.content) === "";
    const group = document.createElement("div");
    group.className = "highlight-group";
    group.style.cursor = "pointer";
    if (focused || extending) group.classList.add("active");
    if (selected) group.classList.add("selected");
    if (located) group.classList.add("locate");
    if (deletable) group.classList.add("deletable");
    group.dataset.id = String(ann.id);
    for (const rect of highlightRectsForRender(meta, ann, pageIndex)) {
      const [x0, y0, x1, y1] = rect;
      const el = document.createElement("div");
      el.className = "highlight";
      el.style.left = `${x0 * meta.scale}px`;
      el.style.top = `${y0 * meta.scale}px`;
      el.style.width = `${(x1 - x0) * meta.scale}px`;
      el.style.height = `${(y1 - y0) * meta.scale}px`;
      el.style.background = ann.hex;
      group.appendChild(el);
    }
    group.addEventListener("contextmenu", (ev) => openCtx(ev, ann));
    group.addEventListener("mousedown", (ev) => {
      if (ev.button !== 0) return;
      startHighlightGesture(ev, ann, meta, pageIndex);
    }, { capture: true });
    meta.annotLayer.appendChild(group);
  }
}

function renderAllHighlights() {
  for (const [idx] of state.pages) renderHighlights(idx);
}

function renderDraftOverlay(meta, rects) {
  if (!meta?.draftLayer) return;
  paintRects(meta.draftLayer, rects, meta.scale, DRAFT_GREY, "highlight draft");
}

function confirmDelete(text) {
  const t = trimText(text);
  if (!t) return true;
  const preview = t.length > 140 ? `${t.slice(0, 140)}…` : t;
  return window.confirm(`Delete this comment?\n\n“${preview}”`);
}

async function requestDelete(id, currentText) {
  const ann = state.annotations.get(id);
  const text = currentText ?? ann?.content ?? "";
  if (!confirmDelete(text)) return;
  await deleteAnnotation(id);
}

function showDraft(pageIndex, spanIds) {
  const meta = pageMeta(pageIndex);
  if (!meta) return;
  if (selectionOverlapsOthers(pageIndex, spanIds)) {
    meta.draftLayer?.replaceChildren();
    return;
  }
  const rects = mergeLineRects(meta.spans, spanIds);
  if (!rects.length) return;

  for (const [idx, m] of state.pages) {
    if (Number(idx) !== pageIndex) m.draftLayer?.replaceChildren();
  }

  state.draft = {
    pageIndex,
    spanIds,
    rects,
    color: state.color,
    committed: false,
    createdAt: Date.now(),
    text: "",
  };
  renderDraftOverlay(meta, rects);
  clearNativeSelection();
  renderCommentsPane();
  focusDraftNote();
}

function flashHighlight(id) {
  for (const el of document.querySelectorAll(`.highlight-group[data-id="${id}"]`)) {
    el.classList.remove("flash");
    void el.offsetWidth;
    el.classList.add("flash");
  }
}

async function locateAnnotation(id, { behavior = "smooth" } = {}) {
  if (state.pendingNote) await blurComment();
  await settleDraft();
  state.focusId = null;
  state.locateId = id;
  const ann = state.annotations.get(id);
  if (ann) {
    await navigateToPdfDest(ann.page, annotationMidY(ann), { behavior });
    renderAllHighlights();
  } else {
    renderAllHighlights();
  }
  renderCommentsPane();
  const card = commentsListEl.querySelector(`.comment-card[data-id="${id}"]`);
  card?.classList.add("locate-pulse");
  card?.scrollIntoView({ block: "nearest", behavior });
  flashHighlight(id);
  clearTimeout(state.locateTimer);
  state.locateTimer = setTimeout(() => {
    state.locateId = null;
    card?.classList.remove("locate-pulse");
    renderAllHighlights();
  }, 1300);
}

function focusAnnotation(id, {
  edit = true,
  toggle = false,
  center = false,
  scrollCard = true,
  behavior = "smooth",
} = {}) {
  if (!edit) {
    void locateAnnotation(id, { behavior });
    return;
  }
  settleDraftSync();
  state.locateId = null;
  state.focusId = id;
  const ann = state.annotations.get(id);
  if (ann?.color) {
    state.color = ann.color;
    updatePaletteSelection(ann.color);
  }
  renderAllHighlights();
  renderCommentsPane();
  if (center && ann) centerAnnotation(ann, { behavior });
  if (scrollCard) {
    const card = commentsListEl.querySelector(`.comment-card[data-id="${id}"]`);
    card?.scrollIntoView({ block: "nearest", behavior });
  }
  syncCommentEditor();
}

async function blurComment() {
  if (state.pendingNote?.flush) await state.pendingNote.flush();
  state.pendingNote = null;
  state.focusId = null;
  closeCommentEditor();
  renderAllHighlights();
  renderCommentsPane();
}

async function dismissComment() {
  await blurComment();
}

function wireNoteEditing(ann, cardEl) {
  let timer;
  const ta = () => commentEditorTa;
  const flush = async () => {
    clearTimeout(timer);
    const text = ta()?.value ?? "";
    if (ann.content === text) {
      state.localDirty = false;
      updateDocMeta();
      return;
    }
    ann.content = text;
    await patchAnnotation(ann.id, { content: text }, { quiet: true });
    state.localDirty = false;
    updateDocMeta();
  };

  const onInput = () => {
    autosizeCommentEditorTa();
    state.localDirty = true;
    updateDocMeta();
    renderHighlights(ann.page);
    const text = ta()?.value ?? "";
    cardEl?.classList.toggle("deletable", trimText(text) === "");
    const preview = cardEl?.querySelector(".comment-editing-preview");
    if (preview) preview.textContent = trimText(text) ? text : "Empty comment";
    clearTimeout(timer);
    timer = setTimeout(flush, 280);
  };

  const onKeydown = (ev) => {
    if (ev.key === "Escape") {
      ev.preventDefault();
      flush().finally(() => blurComment());
      return;
    }
    if ((ev.key === "Backspace" || ev.key === "Delete") && trimText(ta()?.value ?? "") === "") {
      ev.preventDefault();
      requestDelete(ann.id, ta()?.value ?? "");
    }
  };

  return { flush, onInput, onKeydown };
}

function cloneSnapshot(ann) {
  if (!ann) return null;
  const meta = pageMeta(ann.page);
  return {
    page: ann.page,
    rects: (ann.rects || []).map((r) => r.map(Number)),
    color: ann.color || "yellow",
    content: ann.content ?? "",
    title: ann.title ?? "",
    span_ids: meta ? spanIdsFromAnnotation(meta, ann) : [],
  };
}

function clearHistory() {
  state.undoStack = [];
  state.redoStack = [];
  updateUndoRedoUi();
}

function updateUndoRedoUi() {
  if (undoBtnEl) {
    undoBtnEl.disabled = state.undoStack.length === 0;
    undoBtnEl.title = state.undoStack.at(-1)
      ? `Undo: ${state.undoStack.at(-1).label} (⌘Z)`
      : "Undo (⌘Z)";
  }
  if (redoBtnEl) {
    redoBtnEl.disabled = state.redoStack.length === 0;
    redoBtnEl.title = state.redoStack.at(-1)
      ? `Redo: ${state.redoStack.at(-1).label} (⌘⇧Z)`
      : "Redo (⌘⇧Z)";
  }
}

function pushHistory(entry) {
  if (state.historyApplying) return;
  state.undoStack.push(entry);
  if (state.undoStack.length > HISTORY_MAX) state.undoStack.shift();
  state.redoStack = [];
  updateUndoRedoUi();
}

async function restoreSnapshots(snapshots) {
  const res = await withSave(() => api("/api/annotations/batch-restore", {
    method: "POST",
    body: JSON.stringify({ items: snapshots }),
  }));
  return res.items || [];
}

async function refreshAnnotationViews(pages) {
  state.extendPreview = null;
  clearPreviewLayers();
  renderAllHighlights();
  await Promise.all([...pages].map((page) => refreshPageBitmap(page)));
  renderCommentsPane();
  emergencyBackup();
  updateDocMeta();
}

async function ingestRestored(annotations) {
  const pages = new Set();
  for (const ann of annotations) {
    state.annotations.set(ann.id, ann);
    pages.add(ann.page);
  }
  await refreshAnnotationViews(pages);
  return annotations;
}

function makeDeleteHistoryEntry(snapshots, deletedIds) {
  const entry = {
    label: `Delete ${snapshots.length} comment${snapshots.length === 1 ? "" : "s"}`,
    snapshots: snapshots.map((s) => ({ ...s, rects: s.rects.map((r) => [...r]) })),
    liveIds: [...deletedIds],
  };
  entry.undo = async () => {
    const restored = await restoreSnapshots(entry.snapshots);
    await ingestRestored(restored);
    entry.liveIds = restored.map((ann) => ann.id);
  };
  entry.redo = async () => {
    if (!entry.liveIds.length) return;
    await deleteAnnotationsById(entry.liveIds, { quiet: true });
  };
  return entry;
}

function makeCreateHistoryEntry(snapshot, createdId) {
  const snap = { ...snapshot, rects: snapshot.rects.map((r) => [...r]) };
  const entry = {
    label: "Add comment",
    snapshot: snap,
    liveId: createdId,
  };
  entry.undo = async () => {
    await deleteAnnotationsById([entry.liveId], { quiet: true });
  };
  entry.redo = async () => {
    const restored = await restoreSnapshots([entry.snapshot]);
    await ingestRestored(restored);
    entry.liveId = restored[0]?.id ?? entry.liveId;
  };
  return entry;
}

function makeResizeHistoryEntry(beforeSnap, afterAnn) {
  const before = { ...beforeSnap, rects: beforeSnap.rects.map((r) => [...r]) };
  const after = cloneSnapshot(afterAnn);
  const entry = {
    label: "Resize highlight",
    before,
    after,
    liveId: afterAnn.id,
  };
  entry.undo = async () => {
    await deleteAnnotationsById([entry.liveId], { quiet: true });
    const restored = await restoreSnapshots([entry.before]);
    await ingestRestored(restored);
    entry.liveId = restored[0]?.id ?? entry.liveId;
  };
  entry.redo = async () => {
    await deleteAnnotationsById([entry.liveId], { quiet: true });
    const restored = await restoreSnapshots([entry.after]);
    await ingestRestored(restored);
    entry.liveId = restored[0]?.id ?? entry.liveId;
  };
  return entry;
}

async function performUndo() {
  const entry = state.undoStack.pop();
  if (!entry) return;
  state.historyApplying = true;
  updateUndoRedoUi();
  try {
    await entry.undo();
    state.redoStack.push(entry);
    toast(`Undo: ${entry.label}`, 1500);
  } catch (err) {
    state.undoStack.push(entry);
    toast(err.message || "Undo failed");
  } finally {
    state.historyApplying = false;
    updateUndoRedoUi();
  }
}

async function performRedo() {
  const entry = state.redoStack.pop();
  if (!entry) return;
  state.historyApplying = true;
  updateUndoRedoUi();
  try {
    await entry.redo();
    state.undoStack.push(entry);
    toast(`Redo: ${entry.label}`, 1500);
  } catch (err) {
    state.redoStack.push(entry);
    toast(err.message || "Redo failed");
  } finally {
    state.historyApplying = false;
    updateUndoRedoUi();
  }
}

function applyAnnotationUpdate(updated) {
  if (updated.replaced_id != null) {
    state.annotations.delete(updated.replaced_id);
    if (state.focusId === updated.replaced_id) state.focusId = updated.id;
    if (state.pendingNote?.id === updated.replaced_id) state.pendingNote = null;
    if (state.locateId === updated.replaced_id) state.locateId = updated.id;
  }
  state.annotations.set(updated.id, updated);
}

async function patchAnnotation(id, patch, { quiet = false } = {}) {
  const updated = await withSave(() => api(`/api/annotations/${id}`, {
    method: "PATCH",
    body: JSON.stringify(patch),
  }));
  applyAnnotationUpdate(updated);
  renderHighlights(updated.page);
  const colorOnly = Object.keys(patch).length === 1 && patch.color != null;
  const editingThis = state.focusId === id && (state.pendingNote || isCommentEditorActive());
  if (colorOnly && editingThis) {
    setCommentChromeColor(updated.hex);
    updatePaletteSelection(updated.color);
    await refreshPageBitmap(updated.page);
  } else if (!quiet || !editingThis) {
    await refreshPageBitmap(updated.page);
    renderCommentsPane();
  }
  emergencyBackup();
  updateDocMeta();
  if (!quiet && !colorOnly) toast("Saved");
  return updated;
}

async function deleteAnnotation(id, { quiet = false } = {}) {
  await deleteAnnotations([id], { quiet });
}

async function deleteAnnotationsById(ids, { quiet = false } = {}) {
  const unique = [...new Set(ids.map((id) => Number(id)))].filter((id) => state.annotations.has(id));
  if (!unique.length) return [];
  await withSave(() => api("/api/annotations/batch-delete", {
    method: "POST",
    body: JSON.stringify({ ids: unique }),
  }));
  const pages = new Set();
  for (const id of unique) {
    const ann = state.annotations.get(id);
    if (ann) pages.add(ann.page);
    state.annotations.delete(id);
    state.selectedCommentIds.delete(id);
    if (state.focusId === id) state.focusId = null;
    if (state.locateId === id) state.locateId = null;
    if (state.lastSelectedCommentId === id) state.lastSelectedCommentId = null;
  }
  state.pendingNote = null;
  closeCommentEditor();
  await refreshAnnotationViews(pages);
  if (!quiet) toast(`Removed ${unique.length} comment${unique.length === 1 ? "" : "s"}`);
  return unique;
}

async function deleteAnnotations(ids, { quiet = false } = {}) {
  const unique = [...new Set(ids.map((id) => Number(id)))].filter((id) => state.annotations.has(id));
  if (!unique.length) return;
  const snapshots = unique
    .map((id) => cloneSnapshot(state.annotations.get(id)))
    .filter(Boolean);
  const deleted = await deleteAnnotationsById(unique, { quiet });
  if (!state.historyApplying && deleted.length && snapshots.length) {
    pushHistory(makeDeleteHistoryEntry(snapshots, deleted));
  }
}

async function deleteSelectedComments() {
  pruneCommentSelection();
  const ids = [...state.selectedCommentIds];
  if (!ids.length) return;
  const label = ids.length === 1 ? "this comment" : `${ids.length} comments`;
  if (!window.confirm(`Delete ${label}?`)) return;
  await deleteAnnotations(ids);
  clearCommentSelection();
}

function positionContextMenu(x, y) {
  ctxMenu.hidden = false;
  ctxMenu.style.left = "0px";
  ctxMenu.style.top = "0px";
  const pad = 8;
  const rect = ctxMenu.getBoundingClientRect();
  let left = x;
  let top = y;
  if (left + rect.width > window.innerWidth - pad) {
    left = Math.max(pad, window.innerWidth - rect.width - pad);
  }
  if (top + rect.height > window.innerHeight - pad) {
    top = Math.max(pad, window.innerHeight - rect.height - pad);
  }
  ctxMenu.style.left = `${left}px`;
  ctxMenu.style.top = `${top}px`;
}

function contextMenuItems(ann) {
  const items = [
    { label: "Edit comment", action: () => focusAnnotation(ann.id, { center: true }) },
    { label: "Copy comment", action: () => navigator.clipboard.writeText(ann.content || "") },
    { label: "Copy highlight text", action: () => copyHighlightText(ann) },
  ];
  for (const [name] of Object.entries(mergedPalette(state.doc.palette))) {
    items.push({
      label: `Colour · ${name.startsWith("#") ? name : name}`,
      action: () => {
        void applyPaletteColor(name);
      },
    });
  }
  items.push({ sep: true });
  items.push({
    label: "Delete",
    danger: true,
    action: () => requestDelete(ann.id, ann.content),
  });
  return items;
}

function openCtx(ev, ann) {
  ev.preventDefault();
  ev.stopPropagation();
  hideCtx();
  settleDraftSync();
  focusAnnotation(ann.id, { center: false, scrollCard: false, behavior: "auto" });

  const items = contextMenuItems(ann);

  for (const item of items) {
    if (item.sep) {
      ctxMenu.appendChild(document.createElement("hr"));
      continue;
    }
    const btn = document.createElement("button");
    btn.type = "button";
    btn.textContent = item.label;
    if (item.danger) btn.classList.add("danger");
    btn.addEventListener("click", () => { hideCtx(); item.action(); });
    ctxMenu.appendChild(btn);
  }
  positionContextMenu(ev.clientX, ev.clientY);
}

async function copyHighlightText(ann) {
  const meta = pageMeta(ann.page);
  if (!meta) return;
  const hits = meta.spans.filter((sp) =>
    ann.rects.some(([x0, y0, x1, y1]) =>
      sp.bbox[0] >= x0 - 1 && sp.bbox[2] <= x1 + 1 && sp.bbox[1] >= y0 - 1 && sp.bbox[3] <= y1 + 1));
  await navigator.clipboard.writeText(hits.map((h) => h.text).join(""));
  toast("Highlight text copied");
}

function startHighlightGesture(ev, ann, meta, pageIndex) {
  const anchorId = spanIdAtClient(meta, pageIndex, ev.clientX, ev.clientY);
  if (anchorId == null) return;
  ev.preventDefault();
  ev.stopPropagation();
  hideCtx();
  state.highlightGesture = {
    annId: ann.id,
    ann,
    pageIndex,
    meta,
    startX: ev.clientX,
    startY: ev.clientY,
    anchorId,
    baseSpanIds: spanIdsFromAnnotation(meta, ann),
    previewSpanIds: spanIdsFromAnnotation(meta, ann),
    moved: false,
  };
}

async function commitHighlightExtend(gesture) {
  const ids = gesture.previewSpanIds;
  if (spanIdsEqual(ids, gesture.baseSpanIds)) return;
  const before = cloneSnapshot(gesture.ann);
  try {
    const updated = await withSave(() => api(`/api/annotations/${gesture.annId}`, {
      method: "PATCH",
      body: JSON.stringify({ span_ids: ids }),
    }));
    applyAnnotationUpdate(updated);
    if (!state.historyApplying && before) {
      pushHistory(makeResizeHistoryEntry(before, updated));
    }
    state.extendPreview = null;
    renderAllHighlights();
    await refreshPageBitmap(updated.page);
    syncDocFlags(await api("/api/document"));
    emergencyBackup();
    focusAnnotation(updated.id, { center: false, edit: true, scrollCard: true, behavior: "auto" });
  } catch (err) {
    state.extendPreview = null;
    renderAllHighlights();
    toast(err.message || "Could not resize highlight");
  }
}

function finishHighlightGesture() {
  const gesture = state.highlightGesture;
  if (!gesture) return;
  state.highlightGesture = null;
  state.selecting = false;
  setSelectingUi(false);
  if (!gesture.moved) {
    settleDraftSync();
    focusAnnotation(gesture.annId, {
      center: true,
      edit: true,
      scrollCard: true,
      behavior: "auto",
    });
    return;
  }
  void commitHighlightExtend(gesture);
}

function wireSelection(pageIndex, meta) {
  meta._dragSpanIds = null;
  meta.pageEl.addEventListener("mousedown", (ev) => {
    if (ev.button !== 0) return;
    if (ev.target.closest(".pdf-link")) return;
    if (ev.target.closest(".highlight-group")) return;
    const anchorId = spanIdAtClient(meta, pageIndex, ev.clientX, ev.clientY, { strict: true });
    if (anchorId == null) {
      if (editorIsOpen()) {
        ev.preventDefault();
        ev.stopPropagation();
        void dismissEditorFromViewerBackground();
      }
      return;
    }
    ev.preventDefault();
    clearNativeSelection();
    settleDraftSync();
    void blurComment();
    state.focusId = null;
    hideCtx();
    state.selecting = true;
    state.activeSelection = { pageIndex, meta, anchorId, focusId: anchorId };
    setSelectingUi(true, meta.pageEl);
    updateSelectionOverlay(state.activeSelection, anchorId);
  }, { capture: true });
}

function bindGlobalSelectionHandlers() {
  if (state.globalSelectionBound) return;
  state.globalSelectionBound = true;

  window.addEventListener("mousemove", (ev) => {
    const gesture = state.highlightGesture;
    if (gesture) {
      const dx = ev.clientX - gesture.startX;
      const dy = ev.clientY - gesture.startY;
      if (!gesture.moved && Math.hypot(dx, dy) >= DRAG_THRESHOLD) {
        gesture.moved = true;
        state.selecting = true;
        setSelectingUi(true, gesture.meta.pageEl);
        settleDraftSync();
        void blurComment();
        state.focusId = null;
      }
      if (gesture.moved) {
        const focusId = spanIdAtClient(gesture.meta, gesture.pageIndex, ev.clientX, ev.clientY);
        if (focusId == null) return;
        updateExtendPreview(gesture, focusId);
      }
      return;
    }

    const sel = state.activeSelection;
    if (!state.selecting || !sel) return;
    const focusId = spanIdAtClient(sel.meta, sel.pageIndex, ev.clientX, ev.clientY);
    if (focusId == null) return;
    if (focusId === sel.focusId && sel.meta._dragSpanIds?.length) return;
    updateSelectionOverlay(sel, focusId);
  });

  window.addEventListener("mouseup", () => {
    if (state.highlightGesture) {
      finishHighlightGesture();
      clearNativeSelection();
      return;
    }

    const sel = state.activeSelection;
    if (!state.selecting || !sel) return;
    state.selecting = false;
    setSelectingUi(false);
    const spanIds = sel.meta._dragSpanIds || spanRangeOrdered(sel.meta.spans, sel.anchorId, sel.anchorId);
    sel.meta._dragSpanIds = null;
    state.activeSelection = null;
    clearNativeSelection();
    if (spanIds.length) showDraft(sel.pageIndex, spanIds);
    else sel.meta.draftLayer?.replaceChildren();
  });
}

async function reloadAnnotations() {
  const list = await api("/api/annotations");
  mergeAnnotationsFromServer(list);
}

function registerAnnotationColors(list) {
  const custom = loadCustomPalette();
  let changed = false;
  const known = mergedPalette(state.doc?.palette);
  for (const ann of list) {
    const color = ann.color;
    if (typeof color === "string" && color.startsWith("#") && !known[color] && !custom[color]) {
      custom[color] = (ann.hex || color).toLowerCase();
      changed = true;
    }
  }
  if (changed) {
    saveCustomPalette(custom);
    buildPalette(state.doc?.palette || {});
  }
}

function mergeAnnotationsFromServer(list) {
  const prevFocus = state.focusId;
  const prevKey = prevFocus ? annotKey(state.annotations.get(prevFocus)) : null;
  const editingText = state.pendingNote?.ta?.value;

  registerAnnotationColors(list);
  state.annotations.clear();
  for (const ann of list) {
    if (prevKey && annotKey(ann) === prevKey && editingText != null) {
      state.annotations.set(ann.id, { ...ann, content: editingText });
    } else {
      state.annotations.set(ann.id, ann);
    }
  }

  if (prevKey) {
    const match = list.find((a) => annotKey(a) === prevKey);
    state.focusId = match ? match.id : null;
    if (!match) {
      state.pendingNote = null;
    } else if (state.pendingNote && state.pendingNote.id !== match.id) {
      state.pendingNote = null;
    }
  }

  renderAllHighlights();
  if (!isCommentEditorActive()) {
    renderCommentsPane();
  } else {
    updateCommentSelectionUi();
  }
  emergencyBackup();
  void refreshLoadedPageBitmaps();
}

async function pullServerState({ quiet = false } = {}) {
  if (state.savePending > 0) return;
  if (state.draft && !state.draft.committed) return;
  try {
    const res = await api(`/api/sync?since=${state.serverRevision}`);
    applyServerRevision(res.revision);
    state.fileMtime = res.mtime ?? state.fileMtime;
    if (res.unsaved != null) state.doc.unsaved = res.unsaved;
    updateDocMeta();
    if (!res.changed) return;
    if (!state.historyApplying) clearHistory();
    const prevKeys = new Set([...state.annotations.values()].map(annotKey));
    mergeAnnotationsFromServer(res.annotations || []);
    if (!quiet) {
      const added = [...state.annotations.values()].filter((a) => !prevKeys.has(annotKey(a))).length;
      if (added > 0) toast(`Synced ${added} comment${added === 1 ? "" : "s"}`, 1800);
    }
  } catch (_) {
    /* offline / server stopped */
  }
}

function startDiskSync() {
  if (state.syncTimer) clearInterval(state.syncTimer);
  if (!state.doc?.open) {
    state.syncTimer = null;
    return;
  }
  state.syncTimer = setInterval(() => { void pullServerState({ quiet: true }); }, 1000);
}

async function syncDocFlags(doc) {
  state.doc = doc;
  state.fileMtime = doc.file_mtime ?? state.fileMtime;
  setServerRevision(doc.revision);
  if (!doc.unsaved) state.localDirty = false;
  setAppVersion(doc.app_version);
  updateDocMeta();
}

async function switchReviewer(name) {
  if (!confirmUnsaved(`Switch reviewer to “${name}”`)) return;
  const doc = await api("/api/reviewer", {
    method: "POST",
    body: JSON.stringify({ reviewer: name }),
  });
  await syncDocFlags(doc);
  populateReviewers();
  reviewerEl.value = doc.reviewer;
  resetPageViewport();
  clearHistory();
  await reloadAnnotations();
  scheduleStubSync();
  seedViewerNavHistory();
  toast(editingInPlace(doc) ? `Reviewer: ${doc.reviewer}` : `Opened ${basename(doc.save_path)}`);
}

function resetPageViewport() {
  for (const timer of state.pendingStubRemoval.values()) clearTimeout(timer);
  state.pendingStubRemoval.clear();
  state.pages.clear();
  state.pageStubs.clear();
  state.loadingPages.clear();
  state.pageLoadGen.clear();
  state.pageLoadQueue = [];
  if (state.pageObserver) {
    state.pageObserver.disconnect();
    state.pageObserver = null;
  }
  pagesEl.replaceChildren();
  buildPageLayout();
  initPageViewport();
}

async function refreshPageBitmap(index) {
  const meta = state.pages.get(index);
  if (!meta) return;
  try {
    const data = await api(`/api/page/${index}`);
    const img = meta.pageEl?.querySelector("img");
    if (img) img.src = `data:image/png;base64,${data.image}`;
  } catch (_) {
    /* page may have been unloaded */
  }
}

async function refreshLoadedPageBitmaps() {
  await Promise.all([...state.pages.keys()].map((idx) => refreshPageBitmap(idx)));
}

async function loadPage(index) {
  invalidatePageIfDetached(index);
  if (isPageMounted(index)) return;
  if (state.loadingPages.has(index)) return;

  state.loadingPages.add(index);
  const generation = (state.pageLoadGen.get(index) || 0) + 1;
  state.pageLoadGen.set(index, generation);
  const pageEl = ensurePageStub(index);
  try {
    pageEl.className = "page placeholder loading";
    pageEl.replaceChildren();
    pageEl.textContent = `Loading page ${index + 1}…`;

    const data = await api(`/api/page/${index}`);
    if (state.pageLoadGen.get(index) !== generation) return;
    if (!pageEl.isConnected || !state.pageStubs.has(index)) return;
    pageEl.className = "page";
    pageEl.replaceChildren();
    pageEl.style.width = `${pageRenderWidth(index)}px`;
    pageEl.style.minHeight = `${pageRenderHeight(index)}px`;

    const badge = document.createElement("div");
    badge.className = "page-badge";
    badge.textContent = `Page ${index + 1}`;
    pageEl.appendChild(badge);

    const img = document.createElement("img");
    img.alt = `Page ${index + 1}`;
    img.decoding = "async";
    img.loading = "eager";
    img.src = `data:image/png;base64,${data.image}`;
    pageEl.appendChild(img);

    const layer = document.createElement("div");
    layer.className = "page-layer";
    pageEl.appendChild(layer);

    const textLayer = document.createElement("div");
    textLayer.className = "text-layer";
    layer.appendChild(textLayer);

    for (const sp of data.spans) {
      const [x0, y0, x1, y1] = sp.bbox;
      const span = document.createElement("span");
      span.className = "text-span";
      span.dataset.id = String(sp.id);
      span.textContent = sp.text;
      span.style.left = `${x0 * data.scale}px`;
      span.style.top = `${y0 * data.scale}px`;
      span.style.fontSize = `${Math.max(8, (y1 - y0) * data.scale * 0.92)}px`;
      textLayer.appendChild(span);
    }

    const draftLayer = document.createElement("div");
    draftLayer.className = "draft-layer";
    layer.appendChild(draftLayer);

    const annotLayer = document.createElement("div");
    annotLayer.className = "annot-layer";
    layer.appendChild(annotLayer);

    const linkLayer = document.createElement("div");
    linkLayer.className = "link-layer";
    layer.appendChild(linkLayer);

    const meta = {
      pageEl,
      textLayer,
      draftLayer,
      annotLayer,
      linkLayer,
      scale: data.scale,
      spans: data.spans,
    };
    state.pages.set(index, meta);
    wireLinks(meta, data.links || [], data.scale);
    wireSelection(index, meta);
    renderHighlights(index);
  } finally {
    if (state.pageLoadGen.get(index) === generation) {
      state.loadingPages.delete(index);
    }
    drainPageLoadQueue();
    repairVisiblePages();
    prefetchPages();
  }
}

function initPageViewport() {
  if (state.pageObserver) state.pageObserver.disconnect();
  state.pageObserver = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        if (!entry.isIntersecting) continue;
        const idx = Number(entry.target.dataset.page);
        requestPageLoad(idx, { priority: true });
      }
    },
    { root: viewerEl, rootMargin: PAGE_LOAD_MARGIN, threshold: 0 },
  );
  scheduleStubSync();
}

function routeDraftTyping(ev) {
  if (ev.metaKey || ev.ctrlKey || ev.altKey) return false;
  if (!state.draft || state.draft.committed) return false;
  if (Date.now() - (state.draft.createdAt ?? 0) < 300) return false;
  const ta = state.draft.ta ?? commentEditorTa;
  if (!ta || document.activeElement === ta) return false;
  if (ev.target.closest("textarea, input, select, [contenteditable]")) return false;
  if (ev.key === "Escape") return false;
  if (ev.key.length !== 1 && ev.key !== "Backspace" && ev.key !== "Enter") return false;
  ev.preventDefault();
  syncDraftTextFromEditor();
  syncCommentEditor();
  ta.focus();
  const start = ta.selectionStart ?? ta.value.length;
  const end = ta.selectionEnd ?? start;
  if (ev.key === "Backspace") {
    if (start === end && start > 0) {
      ta.value = ta.value.slice(0, start - 1) + ta.value.slice(end);
      ta.setSelectionRange(start - 1, start - 1);
    } else if (start !== end) {
      ta.value = ta.value.slice(0, start) + ta.value.slice(end);
      ta.setSelectionRange(start, start);
    }
  } else if (ev.key === "Enter") {
    ta.value = ta.value.slice(0, start) + "\n" + ta.value.slice(end);
    ta.setSelectionRange(start + 1, start + 1);
  } else {
    ta.value = ta.value.slice(0, start) + ev.key + ta.value.slice(end);
    ta.setSelectionRange(start + 1, start + 1);
  }
  syncDraftTextFromEditor();
  ta.dispatchEvent(new Event("input", { bubbles: true }));
  return true;
}

async function init() {
  const cleanUrl = new URL(location.href);
  if (cleanUrl.searchParams.delete("layout")) {
    history.replaceState(null, "", cleanUrl);
  }
  wireOpenPdf();
  state.doc = await waitForApp();
  setServerRevision(state.doc.revision ?? 0);
  $("#doc-name").textContent = state.doc.open ? state.doc.name : "PeerFold";
  setAppVersion(state.doc.app_version);
  reviewerEl.value = state.doc.reviewer;
  updateDocMeta();
  populateReviewers();
  buildPalette(state.doc.palette);

  reviewerEl.addEventListener("change", async () => {
    try {
      await switchReviewer(reviewerEl.value);
    } catch (err) {
      toast(err.message || "Invalid reviewer");
      reviewerEl.value = state.doc.reviewer;
    }
  });

  commentsDeleteSelectedEl?.addEventListener("click", () => { void deleteSelectedComments(); });
  commentsClearSelectionEl?.addEventListener("click", clearCommentSelection);
  undoBtnEl?.addEventListener("click", () => { void performUndo(); });
  redoBtnEl?.addEventListener("click", () => { void performRedo(); });

  window.addEventListener("keydown", (ev) => {
    if (routeDraftTyping(ev)) return;
    if ((ev.metaKey || ev.ctrlKey) && ev.key.toLowerCase() === "z") {
      if (ev.target.closest("#reviewer")) return;
      const redo = ev.shiftKey;
      if (redo && !state.redoStack.length) return;
      if (!redo && !state.undoStack.length) return;
      ev.preventDefault();
      if (redo) void performRedo();
      else void performUndo();
      return;
    }
    if ((ev.metaKey || ev.ctrlKey) && ev.key.toLowerCase() === "o") {
      ev.preventDefault();
      void pickAndOpenPdf();
      return;
    }
    if (ev.key === "Escape") {
      if (state.selectedCommentIds.size > 0) {
        ev.preventDefault();
        clearCommentSelection();
        return;
      }
      if (state.draft && !state.draft.committed) {
        ev.preventDefault();
        void settleDraft();
      }
      return;
    }
    if ((ev.metaKey || ev.ctrlKey) && ev.key.toLowerCase() === "a") {
      if (ev.target.closest("textarea, input, select")) return;
      if (!commentEditorEl?.hidden && document.activeElement === commentEditorTa) return;
      ev.preventDefault();
      state.selectedCommentIds = new Set(sortedAnnotations().map((ann) => ann.id));
      state.lastSelectedCommentId = sortedAnnotations().at(-1)?.id ?? null;
      updateCommentSelectionUi();
      return;
    }
    if ((ev.key === "Delete" || ev.key === "Backspace") && state.selectedCommentIds.size > 0) {
      if (ev.target.closest("textarea, input, select")) return;
      if (!commentEditorEl?.hidden) return;
      ev.preventDefault();
      void deleteSelectedComments();
    }
  });

  window.addEventListener("beforeunload", (ev) => {
    if (!hasUnsavedChanges()) return;
    ev.preventDefault();
    ev.returnValue = "You have unsaved changes.";
  });

  buildPageLayout();
  wireWorkspaceLayout();
  bindGlobalSelectionHandlers();
  wireZoomControls();
  viewerEl.addEventListener("scroll", () => {
    scheduleStubSync();
    scheduleNavStateReplace();
  }, { passive: true });
  window.addEventListener("resize", scheduleStubSync);
  if (syncChannel) {
    syncChannel.onmessage = (ev) => {
      if (ev.data.tabId === state.tabId) return;
      if (ev.data.save_path !== state.doc?.save_path) return;
      if (ev.data.revision <= state.serverRevision) return;
      void pullServerState({ quiet: true });
    };
  }
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") void pullServerState({ quiet: true });
  });
  wireViewerNavHistory();
  if (state.doc.open) {
    await bootViewer();
  } else {
    showWelcomeScreen();
    renderCommentsPane();
  }
  startDiskSync();
  updateUndoRedoUi();
  void checkForUpdates();
  window.addEventListener("load", () => scheduleStubSync(), { once: true });
  window.addEventListener("pageshow", (ev) => {
    if (ev.persisted) scheduleStubSync();
  });
}

init().catch((err) => {
  const msg = err.message || "Failed to load viewer";
  toast(msg, 5000);
  if (viewerEl) {
    viewerEl.innerHTML = `<div class="viewer-error"><strong>Could not load PDF</strong><p>${msg}</p><p class="muted">Check the server is running and hard-refresh (⌘⇧R).</p></div>`;
  }
  console.error(err);
});
