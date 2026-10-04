// Drives the comment editor through the situations that used to lose focus,
// keystrokes or text, and reports what happened. Runs inside the page, in dev
// mode only (it needs `window.__peerfold`). Used two ways:
//
//   - pasted into a browser console on a dev build, then `await __runEditorHarness()`;
//   - injected into the real desktop window by scripts/check_editor_session.py,
//     which is the point: PeerFold ships in WKWebView, and focus is exactly the
//     kind of behaviour where engines differ.
//
// Typing goes through execCommand("insertText"), which inserts at the caret and
// fires the same input events a keystroke does -- closer to a person than
// setting `.value`, which is what earlier probes did and why they missed things.

(() => {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const P = () => window.__peerfold;
  const ta = () => P().ta();
  const editorOpen = () => !document.querySelector("#comment-editor").hidden;

  async function api(path, opts) {
    const r = await fetch(path, opts);
    return r.json();
  }

  function freshSpans(page, count) {
    // Consecutive spans on one line, none of them under an existing highlight.
    // Annotations carry rects, not span ids, so "under" is a rectangle overlap.
    const meta = P().state.pages.get(page);
    const rects = [];
    for (const a of P().state.annotations.values()) {
      if (a.page === page) rects.push(...(a.rects || []));
    }
    const overlaps = (b) => rects.some((r) => b[0] < r[2] && b[2] > r[0] && b[1] < r[3] && b[3] > r[1]);
    const spans = meta.spans;
    for (let i = 0; i + count <= spans.length; i += 5) {
      const pick = spans.slice(i, i + count);
      const oneLine = pick.every((s) => Math.abs(s.bbox[1] - pick[0].bbox[1]) < 2);
      if (oneLine && pick.every((s) => s.text && s.text.trim() && !overlaps(s.bbox))) return pick;
    }
    return null;
  }

  async function openDraft(page = 0) {
    // Pages are materialised as they scroll into view; wait for this one's text.
    for (let i = 0; i < 100 && !P().state.pages.get(page)?.spans?.length; i += 1) {
      document.querySelector(`[data-page-index="${page}"]`)?.scrollIntoView({ block: "center" });
      await sleep(100);
    }
    if (!P().state.pages.get(page)?.spans?.length) throw new Error(`page ${page} never loaded its text`);
    const pick = freshSpans(page, 3);
    if (!pick) throw new Error("no free spans on page " + page);
    const a = pick[0], f = pick[pick.length - 1];
    P().showDraft(page, pick.map((s) => s.id), a.id, a.bbox[0], a.bbox[1], f.id, f.bbox[2], f.bbox[1]);
    await sleep(300);
    if (!editorOpen()) throw new Error("draft editor did not open");
    // A selection that starts inside an existing highlight opens THAT comment
    // instead of a draft -- correct for a person, fatal for a test that then
    // types into the wrong comment. Say so rather than measure the wrong thing.
    if (!P().state.draft || P().session?.()?.annId != null) {
      throw new Error(`page ${page}: the selection opened an existing comment, not a new draft`);
    }
    ta().focus();
    return pick;
  }

  function watchFocus() {
    // Samples who has the caret every 20 ms, so a loss shorter than a frame
    // that a later check would miss is still caught.
    const losses = [];
    let stop = false;
    (async () => {
      while (!stop) {
        if (editorOpen() && document.activeElement !== ta()) {
          losses.push({ t: Math.round(performance.now()), active: document.activeElement?.id || document.activeElement?.tagName });
        }
        await sleep(20);
      }
    })();
    return { losses, stop: () => { stop = true; } };
  }

  let missedKeys = 0;
  async function typeSlowly(text, { minMs = 40, maxMs = 160 } = {}) {
    // Counts keystrokes that did not land. A field can be document.activeElement
    // and still refuse input -- when the document selection has been emptied
    // under it -- so "who has focus" alone is not the test; "did the key go in"
    // is. That is the failure the earlier probes could not see.
    for (const ch of text) {
      const before = ta().value.length;
      document.execCommand("insertText", false, ch);
      if (ta().value.length !== before + ch.length) missedKeys += 1;
      await sleep(minMs + Math.random() * (maxMs - minMs));
    }
  }

  async function settle() {
    // Let the debounce fire and the last save finish. Builds before the
    // session model have no handle on their autosaver, so they get time.
    const s = P().session?.();
    if (s) await s.autosaver.flush();
    else await sleep(2500);
    await sleep(200);
  }

  async function serverContent(id) {
    const list = await api("/api/annotations");
    return list.find((a) => a.id === id)?.content ?? null;
  }

  const results = [];
  const check = (name, ok, detail = {}) => results.push({ name, ok: Boolean(ok), ...detail });

  async function t1_continuousTypingAcrossSaves() {
    await openDraft(1);
    const w = watchFocus();
    const text = "The engine keeps the caret while it saves, many times over, mid-sentence.";
    await typeSlowly(text);                       // ~7 s: several debounces and maxWait saves
    w.stop();
    await settle();
    const s = P().session?.();
    const saved = s
      ? await serverContent(s.annId)
      : ((await api("/api/annotations")).find((a) => a.content === text)?.content ?? null);
    check("continuous typing: every keystroke landed", missedKeys === 0, { missedKeys });
    check("continuous typing: focus never left", w.losses.length === 0, { losses: w.losses.slice(0, 5) });
    check("continuous typing: editor still open", editorOpen());
    check("continuous typing: caret at the end", ta().selectionStart === ta().value.length);
    check("continuous typing: server has exactly what was typed", saved === text, { saved });
    return s?.annId;
  }

  async function t2_rogueBlurIsUndone() {
    if (!document.hasFocus()) {
      // The guard deliberately stands down when the window itself is not
      // focused (switching apps blurs the field too, and that is not a theft).
      // An automated browser pane is such a window, so this needs the real one.
      check("rogue blur: skipped, the window is not focused", true, { skipped: true });
      return;
    }
    await typeSlowly(" more");
    const before = ta().selectionStart;
    ta().blur();                                  // nobody clicked, nobody pressed a key
    await sleep(80);
    check("rogue blur: focus restored", document.activeElement === ta());
    check("rogue blur: caret where it was", ta().selectionStart === before, { before, after: ta().selectionStart });
    await settle();
  }

  async function t3_switchCommentMidDebounce(firstId) {
    // Type into the first comment, then open a second one before the debounce
    // fires. The first must keep its own text; the second must not inherit it.
    const tail = " tail-of-first";
    await typeSlowly(tail, { minMs: 20, maxMs: 30 });
    const firstExpected = P().session().text;
    await sleep(100);                             // well inside the debounce
    await openDraft(2);                           // a click elsewhere, then a new selection
    await typeSlowly("second comment");
    await settle();
    const firstSaved = await serverContent(firstId);
    const secondId = P().session()?.annId;
    const secondSaved = secondId != null ? await serverContent(secondId) : null;
    check("switch mid-debounce: first kept its own text", firstSaved === firstExpected, { firstSaved, firstExpected });
    check("switch mid-debounce: second has only its own", secondSaved === "second comment", { secondSaved });
    return secondId;
  }

  async function t4_escapeClosesAndSaves() {
    await typeSlowly(" esc");
    const expected = P().session().text;
    const id = P().session().annId;
    ta().dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    await sleep(600);
    check("escape: editor closed", !editorOpen());
    check("escape: text saved", (await serverContent(id)) === expected);
  }

  async function t5_enterClosesNewComment() {
    await openDraft(3);
    await typeSlowly("enter closes");
    ta().dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
    await sleep(800);
    const list = await api("/api/annotations");
    check("enter: new comment closed", !editorOpen());
    check("enter: new comment saved", list.some((a) => a.content === "enter closes"));
  }

  async function t6_deleteWhileEditing() {
    await openDraft(4);
    await typeSlowly("to be deleted");
    await settle();
    const id = P().session().annId;
    await typeSlowly(" and more", { minMs: 20, maxMs: 30 });   // a save is pending
    const errors = [];
    const onErr = (e) => errors.push(String(e.reason?.message || e.message));
    window.addEventListener("unhandledrejection", onErr);
    await fetch("/api/annotations/batch-delete", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ids: [id] }),
    });
    P().state.annotations.delete(id);             // what the UI's delete does locally
    document.querySelector("#comment-editor-delete")?.click?.();
    await sleep(2500);
    window.removeEventListener("unhandledrejection", onErr);
    check("delete while editing: no errors, no retry loop", errors.length === 0, { errors });
  }

  window.__runEditorHarness = async () => {
    results.length = 0;
    const consoleErrors = [];
    const onErr = (e) => consoleErrors.push(String(e.reason?.message || e.message));
    window.addEventListener("unhandledrejection", onErr);
    window.addEventListener("error", onErr);
    try {
      const first = await t1_continuousTypingAcrossSaves();
      if (!P().session) {
        check("older build: only the typing test applies", true, { skipped: true });
        throw { older: true };
      }
      await t2_rogueBlurIsUndone();
      await t3_switchCommentMidDebounce(first);
      await t4_escapeClosesAndSaves();
      await t5_enterClosesNewComment();
      await t6_deleteWhileEditing();
    } catch (err) {
      if (!err?.older) check("harness ran to the end", false, { error: `${err?.message ?? err} @ ${err?.stack ?? ""}` });
    } finally {
      window.removeEventListener("unhandledrejection", onErr);
      window.removeEventListener("error", onErr);
    }
    check("no uncaught errors during the run", consoleErrors.length === 0, { consoleErrors });
    const failed = results.filter((r) => !r.ok);
    window.__harnessResult = { passed: results.length - failed.length, failed: failed.length, results };
    return window.__harnessResult;
  };
})();
