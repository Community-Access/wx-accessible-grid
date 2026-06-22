"""Static front-end assets: the grid stylesheet and the runtime behaviour.

The runtime is injected once after the page loads (a ``<script>`` set via
``innerHTML`` never executes, so the host installs this with ``run_js``). It
attaches *delegated* listeners to ``document`` so they survive every re-render of
the grid body, drives the grid through ``aria-activedescendant`` (the table is
the only focusable element; the runtime moves the active descendant rather than
focusing cells, which keeps NVDA in focus mode and never bounces focus through
``document.body``), builds the right editor for each cell, and talks to Python
over the bridge.

``__HANDLER__`` is replaced with the WebView's bridge handler name by
:func:`runtime_js`.
"""

from __future__ import annotations

GRID_CSS = """
.wag-sr-only {
  position: absolute !important; width: 1px; height: 1px; padding: 0; margin: -1px;
  overflow: hidden; clip: rect(0 0 0 0); clip-path: inset(50%); white-space: nowrap;
  border: 0;
}
table.wag-grid { border-collapse: collapse; width: 100%; font: inherit; }
table.wag-grid:focus { outline: 2px solid var(--wag-focus, #0a5ad6); outline-offset: 2px; }
table.wag-grid caption { text-align: left; font-weight: 600; margin: 0 0 .5rem; }
table.wag-grid .wag-desc { font-weight: 400; }
table.wag-grid th, table.wag-grid td {
  border: 1px solid var(--wag-border, #888); padding: .25rem .5rem; text-align: left;
  white-space: nowrap;
}
table.wag-grid thead th {
  position: sticky; top: 0; background: var(--wag-head-bg, #f0f0f0);
  color: var(--wag-head-fg, #000);
}
table.wag-grid tbody tr.wag-rowsel {
  /* Selected rows use a dark fill with light text: the fill is clearly distinct
     from the white rows (well past 3:1 region contrast, unlike the old faint blue)
     and the text stays readable (>= 4.5:1). Selection is also conveyed without
     color — the row checkbox state and a spoken "selected" — so it never relies on
     color alone. Override --wag-sel-bg / --wag-sel-fg to theme it. */
  background: var(--wag-sel-bg, #00478f); color: var(--wag-sel-fg, #fff);
}
table.wag-grid tbody tr.wag-rowsel a { color: var(--wag-sel-fg, #fff); }
table.wag-grid tbody [aria-selected="true"] {
  /* Cell-range selection: a mid blue distinct from both the white rows and the
     dark row-selection fill, with black text kept readable. */
  background: var(--wag-range-bg, #3b78d8); color: var(--wag-range-fg, #000);
}
table.wag-grid .wag-active {
  outline: 3px solid var(--wag-focus, #0a5ad6); outline-offset: -3px;
}
table.wag-grid .wag-editor { width: 100%; box-sizing: border-box; font: inherit; }
@media (prefers-contrast: more) {
  table.wag-grid th, table.wag-grid td { border-color: CanvasText; }
}
"""


# The behaviour. Framework-free vanilla JS. Comments explain the *why*.
# Excel/Word-style data grid: arrows move a cell and announce column+row, Tab and
# Shift+Tab walk cells and wrap at row ends, Enter commits and drops down a row,
# F2 or typing edits in place, F6 leaves the grid; Shift+F10/Apps key/VO+Shift+M
# (a `contextmenu` event) all open the native row menu, where selection lives.
_RUNTIME = r"""
(function () {
  if (window.__wag && window.__wag.__installed) { return; }
  var HANDLER = "__HANDLER__";
  var cols = [];        // column metadata, pushed by Python
  var editing = null;   // the cell currently in edit mode, or null
  var activeId = null;  // id of the active (descendant) cell
  var navTimer = null;  // throttle for the navigate event
  var anchor = null;    // {ri, ci} DOM coords where a cell range began
  var PAGE_ROWS = 20;   // PageUp/PageDown jump size (no pagination)

  function grid() { return document.getElementById("wag-grid"); }
  function post(msg) {
    msg.type = "wag";
    try { window[HANDLER].postMessage(JSON.stringify(msg)); } catch (e) {}
  }
  function liveEl(assertive) {
    return document.getElementById(assertive ? "wag-live-assertive" : "wag-live");
  }
  // assertive=true for errors/blocking messages; polite (default) for the rest.
  // Clear then re-set on the next frame so identical consecutive text still
  // re-announces (a screen reader ignores a live region whose text didn't change).
  function announce(text, assertive) {
    var el = liveEl(assertive) || document.getElementById("awv-status") || liveEl(false);
    if (!el) { return; }
    // Clear then re-set on a real timer task so identical text re-announces and
    // it fires reliably even right as the window appears (rAF is throttled when
    // the page isn't actively rendering — e.g. the announce-on-open case).
    el.textContent = "";
    setTimeout(function () { el.textContent = text; }, 0);
  }

  function bodyRows() {
    var g = grid();
    return g && g.tBodies.length ? Array.prototype.slice.call(g.tBodies[0].rows) : [];
  }
  function headRow() { var g = grid(); return g && g.tHead ? g.tHead.rows[0] : null; }
  function cellsOf(tr) { return tr ? Array.prototype.slice.call(tr.cells) : []; }
  function isCell(el) {
    if (!el || !el.getAttribute) { return false; }
    var r = el.getAttribute("role");
    return (r === "gridcell" || r === "rowheader") && !!(el.closest && el.closest("#wag-grid"));
  }
  // Prefer the real focused cell (model B uses real DOM focus), else the tracked id.
  function activeCell() {
    var ae = document.activeElement;
    if (isCell(ae)) { return ae; }
    return activeId ? document.getElementById(activeId) : null;
  }
  function colIndexOf(cell) { return parseInt(cell.getAttribute("data-col"), 10) || 0; }
  // The cell's VALUE text only, excluding the visually-hidden control-type suffix
  // span (rendered as ", edit box" etc. so VoiceOver speaks the control type as
  // part of the cell name). Everything that needs the raw value — the editor seed,
  // the live-region value, the checkbox optimistic text — reads through this so the
  // suffix never leaks into a value or gets double-spoken.
  function escapeHtml(s) {
    return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }
  function suffixSpan(cell) { return cell.querySelector(":scope > .wag-sr-only"); }
  // The value now lives in its own span (id ending "-v") so aria-labelledby can
  // reference it by id; read and write the value THROUGH it so the value span id
  // and the control-type suffix span both survive and the composed name keeps
  // resolving.
  function valueSpan(cell) { return cell.querySelector(':scope > [id$="-v"]'); }
  function cellText(cell) {
    var v = valueSpan(cell);
    if (v) { return v.textContent.trim(); }
    // Fallback for cells with no value span (e.g. the row-select checkbox cell).
    var sx = suffixSpan(cell);
    if (!sx) { return cell.textContent.trim(); }
    var t = "";
    for (var i = 0; i < cell.childNodes.length; i++) {
      var n = cell.childNodes[i];
      if (n !== sx) { t += n.textContent; }
    }
    return t.trim();
  }
  // Set the cell's visible value while KEEPING its value-span id and suffix span
  // intact (so aria-labelledby still resolves and the control-type word survives an
  // authoritative setCell / optimistic edit text).
  function setCellText(cell, value) {
    var v = valueSpan(cell);
    if (v) { v.textContent = value; return; }
    var sx = suffixSpan(cell);
    if (!sx) { cell.textContent = value; return; }
    var n = cell.childNodes, i;
    for (i = n.length - 1; i >= 0; i--) { if (n[i] !== sx) { cell.removeChild(n[i]); } }
    cell.insertBefore(document.createTextNode(value), sx);
  }
  function rowOf(cell) {
    var tr = cell.closest("tr"); var r = tr && tr.getAttribute("data-row");
    return r == null ? -1 : parseInt(r, 10);   // -1 means the header row
  }
  function inHeader(cell) {
    var tr = cell.closest("tr");
    return !!(tr && tr.parentNode && tr.parentNode.tagName === "THEAD");
  }

  // Model B: roving tabindex with REAL DOM focus on the gridcell, so VoiceOver
  // and NVDA both follow the cursor and read each cell on every arrow. The active
  // cell gets tabindex=0 and .focus(); all others tabindex=-1; no
  // aria-activedescendant. CRITICAL: focus the CELL itself, never a child element
  // (NVDA #8395 — focusing a child flips NVDA to browse mode and kills the
  // arrows). The one exception is editing, where the editor input must hold focus.
  function setActive(cell) {
    if (!cell) { return; }
    var g = grid(); if (!g) { return; }
    var prev = activeId ? document.getElementById(activeId) : null;
    if (prev && prev !== cell) { prev.setAttribute("tabindex", "-1"); prev.classList.remove("wag-active"); }
    activeId = cell.id;
    cell.setAttribute("tabindex", "0");
    cell.classList.add("wag-active");
    if (!editing) { try { cell.focus(); } catch (e) {} }
    try { cell.scrollIntoView({ block: "nearest", inline: "nearest" }); } catch (e) {}
  }

  // ----- coordinates + announcements -----------------------------------
  function rowLabelOf(tr) {
    var rh = tr.querySelector('[role="rowheader"]');
    if (rh) { return rh.textContent.trim(); }
    var r = tr.getAttribute("data-row");
    return r != null ? "Row " + (parseInt(r, 10) + 1) : "";
  }
  // Spreadsheet coordinate of a cell, e.g. "B5", from its column index + row.
  function coordOf(cell) {
    var ci = parseInt(cell.getAttribute("aria-colindex"), 10) || 1;
    var r = rowOf(cell), letter = "";
    while (ci > 0) { letter = String.fromCharCode(65 + (ci - 1) % 26) + letter; ci = Math.floor((ci - 1) / 26); }
    return letter + (r + 1);
  }
  // The column header for a cell, from the pushed column metadata.
  function colHeader(cell) {
    if (cell.hasAttribute("data-select")) { return "Select"; }
    var d = cell.getAttribute("data-col");
    if (d != null && cols[parseInt(d, 10)]) { return cols[parseInt(d, 10)].label || ""; }
    return "";
  }
  // The live-region announcement ALWAYS carries the header explicitly (we don't
  // trust the screen reader to add it — VoiceOver often doesn't). Horizontal:
  // "{header}, {value}". Vertical: "{row label}, {header}, {value}". A vertical
  // move leads with the row label ("Channel 5"); plain moves never speak about
  // selection.
  // The spoken control type for a cell ("edit box", "combo box", "read only"…),
  // taken from the cell's hidden suffix span (the renderer's source of truth) so
  // the live-region announcement matches what VoiceOver reads from the name.
  function editorWord(cell) {
    var sx = suffixSpan(cell);
    return sx ? sx.textContent.replace(/^,\s*/, "").trim() : "";
  }
  function announceCell(cell, vertical) {
    if (!cell) { return; }
    if (inHeader(cell)) { announce(cell.textContent.trim() + ", column header"); return; }
    var tr = cell.closest("tr");
    var value = cellText(cell);
    var hdr = colHeader(cell);
    var word = editorWord(cell);          // appended so VO + the live region agree
    var tail = word ? ", " + word : "";
    if (cell.getAttribute("role") === "rowheader") {
      announce(vertical ? rowLabelOf(tr) : ((hdr ? hdr + ", " : "") + value + tail));
      return;
    }
    var hv = (hdr ? hdr + ", " : "") + (value || coordOf(cell)) + tail;
    announce(vertical ? (rowLabelOf(tr) + ", " + hv) : hv);
  }
  function postNavigate(cell) {
    var row = rowOf(cell), col = colIndexOf(cell);
    if (navTimer) { clearTimeout(navTimer); }
    navTimer = setTimeout(function () { post({ action: "navigate", row: row, col: col }); }, 60);
  }

  // ----- cell-range selection (aria-selected="true" only, never "false") -
  function domCoords(cell) {
    var rows = bodyRows(), tr = cell.closest("tr");
    return { ri: rows.indexOf(tr), ci: cellsOf(tr).indexOf(cell) };
  }
  function cellByDom(ri, ci) { var tr = bodyRows()[ri]; return tr ? cellsOf(tr)[ci] : null; }
  function clearRange() {
    var g = grid(); if (!g) { return; }
    Array.prototype.forEach.call(g.querySelectorAll('tbody [aria-selected]'),
      function (c) { c.removeAttribute("aria-selected"); });   // omit it, never "false"
  }
  function paintRange(a, b) {
    clearRange();
    var rows = bodyRows();
    var r0 = Math.min(a.ri, b.ri), r1 = Math.max(a.ri, b.ri);
    var c0 = Math.min(a.ci, b.ci), c1 = Math.max(a.ci, b.ci), n = 0;
    for (var rr = r0; rr <= r1; rr++) {
      var cs = cellsOf(rows[rr]);
      for (var cc = c0; cc <= c1; cc++) { if (cs[cc]) { cs[cc].setAttribute("aria-selected", "true"); n++; } }
    }
    return n;
  }
  function announceRange(a, b, n) {
    var ca = cellByDom(a.ri, a.ci), cb = cellByDom(b.ri, b.ci);
    if (ca && cb) {
      announce("Selected " + coordOf(ca) + " to " + coordOf(cb) + ", " + n + (n === 1 ? " cell" : " cells"));
    }
  }

  // Plain move: set active, COLLAPSE any range and re-anchor. Data cells are NOT
  // echoed to the live region: each carries an aria-labelledby name (channel,
  // column header, value, control type) that BOTH VoiceOver (computed name) and
  // NVDA (focus-mode name) speak on focus. Echoing here would make NVDA
  // double-speak. The live region stays reserved for events with no name to ride
  // on — ranges, edges, edit results. Header cells have no composed name, so they
  // still announce here.
  function goTo(cell, vertical) {
    if (!cell) { return; }
    setActive(cell);
    if (inHeader(cell)) { clearRange(); anchor = null; announceCell(cell, vertical); }
    else { clearRange(); anchor = domCoords(cell); }
    postNavigate(cell);
  }
  function moveTo(tr, colIdx, vertical) {
    if (!tr) { return; }
    var cells = cellsOf(tr);
    if (!cells.length) { return; }
    colIdx = Math.max(0, Math.min(colIdx, cells.length - 1));
    goTo(cells[colIdx], vertical);
  }
  // Shift+arrow: extend the rectangle from the anchor to the target cell.
  function extendTo(cell) {
    if (!cell || inHeader(cell)) { return; }
    if (!anchor) { var a = activeCell(); anchor = domCoords(a && !inHeader(a) ? a : cell); }
    setActive(cell);
    var b = domCoords(cell);
    var n = paintRange(anchor, b);
    announceRange(anchor, b, n);
    postNavigate(cell);
  }

  // Arrows clamp (no wrap — wrapping is Tab's job); the whole grid is in the DOM.
  // Shift extends the cell range; Ctrl jumps to the region edge; a plain arrow
  // moves and collapses the range.
  function navigate(cell, key, ctrl, shift) {
    var rows = bodyRows();
    if (!rows.length) { return false; }
    var head = inHeader(cell);
    var tr = cell.closest("tr");
    var ri = head ? -1 : rows.indexOf(tr);
    var ci = cellsOf(tr).indexOf(cell);
    var ncols = cellsOf(rows[Math.max(0, ri)]).length;
    var nr = ri, nc = ci, vertical = false, toHeader = false;
    if (key === "ArrowRight") { nc = ctrl ? ncols - 1 : ci + 1; }
    else if (key === "ArrowLeft") { nc = ctrl ? 0 : ci - 1; }
    else if (key === "ArrowDown") { vertical = true; nr = head ? 0 : (ctrl ? rows.length - 1 : ri + 1); }
    else if (key === "ArrowUp") {
      vertical = true;
      if (head) { announce("Top of grid"); return true; }
      if (ri > 0) { nr = ctrl ? 0 : ri - 1; }
      else if (shift) { nr = 0; }
      else { toHeader = true; }
    }
    else if (key === "Home") { nc = 0; if (ctrl) { nr = 0; vertical = true; } }
    else if (key === "End") { nc = ncols - 1; if (ctrl) { nr = rows.length - 1; vertical = true; } }
    else if (key === "PageDown") { vertical = true; nr = Math.min(rows.length - 1, (head ? 0 : ri) + PAGE_ROWS); }
    else if (key === "PageUp") { vertical = true; nr = Math.max(0, (head ? 0 : ri) - PAGE_ROWS); }
    else { return false; }
    if (toHeader) {
      var hr = headRow();
      if (hr) { clearRange(); anchor = null; var hc = cellsOf(hr)[ci]; setActive(hc); announceCell(hc, true); }
      return true;
    }
    nr = Math.max(0, Math.min(nr, rows.length - 1));
    nc = Math.max(0, Math.min(nc, ncols - 1));
    var target = cellsOf(rows[nr])[nc];
    if (shift && key.indexOf("Arrow") === 0) { extendTo(target); } else { goTo(target, vertical); }
    return true;
  }

  // Tab / Shift+Tab: move cell to cell, wrapping to the next/previous row;
  // stop and announce at the grid corners (Tab never silently leaves — F6 does).
  function tabMove(forward) {
    var cell = activeCell();
    if (!cell) { return; }
    var rows = bodyRows();
    if (inHeader(cell)) { if (rows.length) { goTo(cellsOf(rows[0])[0], true); } return; }
    var tr = cell.closest("tr");
    var ri = rows.indexOf(tr);
    var cells = cellsOf(tr);
    var ci = cells.indexOf(cell);
    if (forward) {
      if (ci < cells.length - 1) { goTo(cells[ci + 1], false); }
      else if (ri < rows.length - 1) { goTo(cellsOf(rows[ri + 1])[0], false); }
      else { announce("End of grid"); }
    } else {
      if (ci > 0) { goTo(cells[ci - 1], false); }
      else if (ri > 0) { var pc = cellsOf(rows[ri - 1]); goTo(pc[pc.length - 1], false); }
      else { announce("Start of grid"); }
    }
  }

  function moveDown(cell) {
    var rows = bodyRows();
    var ri = rows.indexOf(cell.closest("tr"));
    var ci = cellsOf(cell.closest("tr")).indexOf(cell);
    if (ri >= 0 && ri < rows.length - 1) { goTo(cellsOf(rows[ri + 1])[ci], true); }
    else { announce("Last row"); }
  }

  // F6 / Escape (when not editing): the documented way OUT of the grid (since Tab
  // is owned). Blur the active cell so normal Tab order resumes — the user is
  // never trapped (WCAG 2.1.2). The host may also move focus elsewhere.
  function leaveGrid() {
    announce("Left grid");
    var a = activeCell();
    if (a) { try { a.blur(); } catch (e) {} }
  }

  // ----- bulk ROW selection (the checkbox column; for delete/move ops) --
  // Tracked with a row class + the checkbox, NOT aria-selected, so it stays out
  // of the cell-range system and plain navigation never speaks "selected".
  var rowSelAnchor = null;   // last row index toggled ON, for "select range to here"
  function selectedRowCount() { return grid().querySelectorAll('tbody tr.wag-rowsel').length; }
  function rowLabelFor(tr, row) {
    var label = tr.querySelector('[role="rowheader"]');
    return label ? label.textContent.trim() : String(row + 1);
  }
  // Set one row's selected state (class + checkbox + Python). Pure mechanism, no
  // announcement, so it can be reused by the toggle key and the context-menu
  // commands (which compose their own, range-aware, announcement).
  function setRowSelected(tr, on) {
    if (!tr) { return; }
    if (on) { tr.classList.add("wag-rowsel"); } else { tr.classList.remove("wag-rowsel"); }
    var box = tr.querySelector('[data-select] input');
    if (box) { box.checked = on; }
    var row = parseInt(tr.getAttribute("data-row"), 10);
    if (on) { rowSelAnchor = row; }
    post({ action: "select", row: row, selected: on, count: selectedRowCount() });
  }
  function trByRow(row) {
    return grid().querySelector('tbody tr[data-row="' + row + '"]');
  }
  function toggleSelect(cell) {
    var row = rowOf(cell);
    if (row < 0) { return; }
    var tr = cell.closest("tr");
    var now = !tr.classList.contains("wag-rowsel");
    setRowSelected(tr, now);
    var count = selectedRowCount();
    announce("Row " + rowLabelFor(tr, row) + (now ? " selected" : " unselected") +
             ", " + count + (count === 1 ? " row" : " rows") + " selected");
  }
  // Context-menu path (the route that works under VoiceOver, where plain arrows and
  // Shift+arrow are intercepted by VO and never reach the page). "Select this row"
  // adds the given row to the bulk selection and sets the range anchor.
  function selectRow(row) {
    var tr = trByRow(row);
    if (!tr) { return; }
    setRowSelected(tr, true);
    var count = selectedRowCount();
    announce("Row " + rowLabelFor(tr, row) + " selected, " +
             count + (count === 1 ? " row" : " rows") + " selected");
  }
  // "Select range to here": select every row from the last selected row (anchor)
  // through the given row, inclusive — a checkbox-free way to select a span.
  function selectRowRangeTo(row) {
    var rows = bodyRows();
    if (!rows.length) { return; }
    var byIndex = {};
    for (var i = 0; i < rows.length; i++) {
      byIndex[parseInt(rows[i].getAttribute("data-row"), 10)] = rows[i];
    }
    var start = (rowSelAnchor != null && byIndex[rowSelAnchor] != null) ? rowSelAnchor : row;
    var lo = Math.min(start, row), hi = Math.max(start, row);
    for (var r = lo; r <= hi; r++) { if (byIndex[r]) { setRowSelected(byIndex[r], true); } }
    rowSelAnchor = start;   // setRowSelected moved it; restore the span's anchor
    var count = selectedRowCount();
    var trEnd = byIndex[row];
    announce("Selected rows " + rowLabelFor(byIndex[lo], lo) + " to " +
             rowLabelFor(byIndex[hi], hi) + ", " +
             count + (count === 1 ? " row" : " rows") + " selected");
  }

  // ----- range commands: Ctrl+Space column, Shift+Space row, Ctrl+A all --
  function selectColumn() {
    var cell = activeCell(); if (!cell || inHeader(cell)) { return; }
    var rows = bodyRows(); var ci = cellsOf(cell.closest("tr")).indexOf(cell);
    var n = paintRange({ ri: 0, ci: ci }, { ri: rows.length - 1, ci: ci });
    anchor = domCoords(cell);
    var letter = coordOf(cellByDom(0, ci)).replace(/[0-9]+$/, "");
    announce("Selected column " + letter + ", " + n + (n === 1 ? " cell" : " cells"));
  }
  function selectRowRange() {
    var cell = activeCell(); if (!cell || inHeader(cell)) { return; }
    var tr = cell.closest("tr"); var ri = bodyRows().indexOf(tr);
    var last = cellsOf(tr).length - 1;
    var n = paintRange({ ri: ri, ci: 0 }, { ri: ri, ci: last });
    anchor = domCoords(cell);
    announce("Selected row " + rowLabelOf(tr) + ", " + n + (n === 1 ? " cell" : " cells"));
  }
  function selectAllCells() {
    var rows = bodyRows(); if (!rows.length) { return; }
    var last = cellsOf(rows[rows.length - 1]).length - 1;
    var n = paintRange({ ri: 0, ci: 0 }, { ri: rows.length - 1, ci: last });
    announce("Selected all, " + n + (n === 1 ? " cell" : " cells"));
  }

  // Bulk ROW select-all / clear, for the host's Edit menu (Select All / Clear) and
  // for Ctrl+A. They set every row's class/checkbox/status span directly and report
  // the result to Python in ONE message rather than one per row.
  function selectAllRows() {
    var rows = bodyRows(); if (!rows.length) { return; }
    var nums = [];
    for (var i = 0; i < rows.length; i++) {
      var tr = rows[i];
      tr.classList.add("wag-rowsel");
      var box = tr.querySelector('[data-select] input');
      if (box) { box.checked = true; }
      nums.push(parseInt(tr.getAttribute("data-row"), 10));
    }
    rowSelAnchor = nums[nums.length - 1];
    post({ action: "selectAllRows", rows: nums });
    announce("Selected all, " + nums.length + (nums.length === 1 ? " row" : " rows") + " selected");
  }
  function clearAllSelection() {
    var rows = bodyRows();
    for (var i = 0; i < rows.length; i++) {
      var tr = rows[i];
      tr.classList.remove("wag-rowsel");
      var box = tr.querySelector('[data-select] input');
      if (box) { box.checked = false; }
    }
    clearRange();
    rowSelAnchor = null;
    post({ action: "clearSelection" });
    announce("Selection cleared");
  }

  // ----- editing -------------------------------------------------------

  function buildEditor(cell) {
    var meta = cols[colIndexOf(cell)] || {};
    var kind = meta.editor || "text";
    var raw = cell.getAttribute("data-raw");
    var value = raw != null ? raw : cellText(cell);
    var el;
    if (kind === "combo") {
      el = document.createElement("select");
      (meta.choices || []).forEach(function (opt) {
        var o = document.createElement("option");
        o.value = opt; o.textContent = opt;
        if (opt === value) { o.selected = true; }
        el.appendChild(o);
      });
    } else if (kind === "checkbox") {
      el = document.createElement("input");
      el.type = "checkbox";
      el.checked = (value === "true" || value === "1" || value === "yes");
    } else if (kind === "slider" || kind === "stepper") {
      el = document.createElement("input");
      el.type = (kind === "slider") ? "range" : "number";
      if (meta.min != null) { el.min = meta.min; }
      if (meta.max != null) { el.max = meta.max; }
      if (meta.step != null) { el.step = meta.step; }
      el.value = value;
    } else {
      el = document.createElement("input");
      el.type = "text";
      el.value = value;
    }
    el.className = "wag-editor";
    el.setAttribute("aria-label", meta.label || "value");
    return el;
  }

  function readEditor(el) {
    return el.type === "checkbox" ? (el.checked ? "true" : "false") : el.value;
  }

  // A checkbox flips in one keystroke (Enter/F2) rather than opening an editor:
  // toggle the value, persist it, and announce the new state. No edit mode.
  function toggleCheckbox(cell, meta) {
    var raw = cell.getAttribute("data-raw");
    var on = !(raw === "true" || raw === "1" || raw === "yes");
    var value = on ? "true" : "false";
    cell.setAttribute("data-raw", value);
    setCellText(cell, on ? "Yes" : "No");  // optimistic; setCell delivers the truth (keeps suffix)
    // The single confirmation comes back through setCell (model round-trip), so
    // the screen reader doesn't double-speak.
    post({ action: "edit", row: rowOf(cell), col: colIndexOf(cell), value: value });
  }

  // seed: optional first character (Excel type-to-replace) — when present the
  // editor opens with that character instead of the cell's current value.
  function enterEdit(cell, seed) {
    if (editing) { return; }
    // The leading selection checkbox toggles the row rather than opening an editor.
    if (cell.hasAttribute("data-select")) { toggleSelect(cell); return; }
    if (cell.getAttribute("data-editable") !== "1") { announce("This cell is read only"); return; }
    var meta0 = cols[colIndexOf(cell)] || {};
    if (meta0.editor === "checkbox") { toggleCheckbox(cell, meta0); return; }
    cell.__orig = cell.innerHTML;
    // Remember the hidden control-type suffix so commitEdit can restore it after it
    // rebuilds the cell's value (cancelEdit restores it for free via __orig).
    var sx0 = suffixSpan(cell);
    cell.__suffix = sx0 ? sx0.outerHTML : "";
    // Drop the composed name for the duration: its aria-labelledby points at the
    // value/suffix spans we are about to replace with the editor input (which
    // carries its own aria-label). Restored on commit/cancel.
    cell.__lbl = cell.getAttribute("aria-labelledby");
    if (cell.__lbl != null) { cell.removeAttribute("aria-labelledby"); }
    var el = buildEditor(cell);
    cell.innerHTML = "";
    cell.appendChild(el);
    // Capture-phase listener on the editor itself: a native <select> consumes
    // Escape/Tab to close its dropdown, so the document listener would never see
    // them. Capturing here lets the grid cancel/commit on a single Escape.
    el.addEventListener("keydown", onEditorKeydown, true);
    editing = cell;
    if (seed != null) {
      if (el.tagName === "SELECT") {
        var s = seed.toLowerCase();
        for (var i = 0; i < el.options.length; i++) {
          if (el.options[i].text.toLowerCase().indexOf(s) === 0) { el.selectedIndex = i; break; }
        }
      } else if (el.type !== "checkbox") { el.value = seed; }
    }
    el.focus();
    if (seed == null && el.select) { try { el.select(); } catch (e) {} }
  }

  // mode: "down" (Enter), "tab"/"shifttab" (Tab during edit), or null (stay).
  // Always restore the grid as the focused element and the cell as its active
  // descendant *before* tearing the editor out, so focus never lands on body.
  function commitEdit(mode) {
    if (!editing) { return; }
    var cell = editing;
    var el = cell.querySelector(".wag-editor");
    var value = readEditor(el);
    var isCheck = el.type === "checkbox";
    post({ action: "edit", row: rowOf(cell), col: colIndexOf(cell), value: value });
    // Optimistic text; Python's setCell() delivers the authoritative value. Rebuild
    // the value span with its stable id (so aria-labelledby resolves), re-append the
    // hidden control-type suffix so the cell still announces "…, edit box", and
    // restore the composed name.
    var shown = isCheck ? (value === "true" ? "Yes" : "No") : el.value;
    cell.innerHTML = '<span id="' + cell.id + '-v">' + escapeHtml(shown) + "</span>" +
                     (cell.__suffix || "");
    if (cell.__lbl != null) { cell.setAttribute("aria-labelledby", cell.__lbl); }
    editing = null;
    setActive(cell);   // editing cleared first, so this re-focuses the CELL
    if (mode === "down") { moveDown(cell); }
    else if (mode === "tab") { tabMove(true); }
    else if (mode === "shifttab") { tabMove(false); }
  }

  function cancelEdit() {
    if (!editing) { return; }
    var cell = editing;
    cell.innerHTML = cell.__orig != null ? cell.__orig : cell.innerHTML;
    // __orig already holds the original value/suffix spans; re-add the name attr.
    if (cell.__lbl != null) { cell.setAttribute("aria-labelledby", cell.__lbl); }
    editing = null;
    setActive(cell);   // editing cleared first, so this re-focuses the CELL
    announce("Edit cancelled");
  }

  // ----- key handling --------------------------------------------------

  function isPrintable(e) {
    return !e.ctrlKey && !e.altKey && !e.metaKey && typeof e.key === "string" && e.key.length === 1;
  }

  // The keys that control an open editor: Escape cancels, Tab commits + moves,
  // Enter commits + drops down (except a SELECT, which confirms its own option on
  // Enter — there we commit via the change event instead). Returns true if it
  // handled the key. Shared by the document listener AND a capture-phase listener
  // bound to the editor element, so a native <select> can't swallow Escape/Tab to
  // close its own dropdown before the grid sees it (one Escape always exits).
  function handleEditorKey(e, ed) {
    if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); cancelEdit(); return true; }
    if (e.key === "Tab") {
      e.preventDefault(); e.stopPropagation();
      commitEdit(e.shiftKey ? "shifttab" : "tab"); return true;
    }
    if (e.key === "Enter") {
      if (ed && ed.tagName === "SELECT") { return false; }  // SELECT commits via change
      e.preventDefault(); e.stopPropagation(); commitEdit("down"); return true;
    }
    return false;
  }

  // Bound to the editor in capture phase so Escape/Tab/Enter reach the grid before
  // the control's own handling (a <select> otherwise eats Escape to shut its list).
  function onEditorKeydown(e) {
    if (!editing) { return; }
    handleEditorKey(e, e.currentTarget);
  }

  document.addEventListener("keydown", function (e) {
    if (editing) {
      var ed = editing.querySelector(".wag-editor");
      handleEditorKey(e, ed);
      return;
    }
    var g = grid();
    // Model B: a gridcell holds real focus, so the gate is "focus is in the grid"
    // (the active cell), not "the table is focused".
    if (!g || !g.contains(document.activeElement)) { return; }
    var cell = activeCell();
    if (!cell) {
      var first = g.querySelector('tbody [role="gridcell"], tbody [role="rowheader"]');
      if (first) { setActive(first); }
      return;
    }
    var k = e.key;
    if (k === "Tab") { e.preventDefault(); tabMove(!e.shiftKey); return; }  // wrap, never leaves
    if (k === "F6") { e.preventDefault(); leaveGrid(); return; }           // the way out
    if (k === "Escape") { e.preventDefault(); leaveGrid(); return; }       // not editing -> leave
    if (k === "F2") { if (!e.repeat) { e.preventDefault(); enterEdit(cell); } return; }
    if (k === "Enter") {
      if (!e.repeat) {
        e.preventDefault();
        if (cell.getAttribute("data-editable") === "1" || cell.hasAttribute("data-select")) {
          enterEdit(cell);
        } else { post({ action: "activate", row: rowOf(cell), col: colIndexOf(cell) }); }
      }
      return;
    }
    if (k === "a" || k === "A") {
      // Ctrl+A selects all ROWS (channels) — the unit bulk operations act on —
      // matching the host's Edit > Select All. (selectAllCells remains for a
      // range-oriented host that wants whole-grid cell selection instead.)
      if (e.ctrlKey && !e.shiftKey && !e.altKey) { e.preventDefault(); selectAllRows(); return; }
    }
    if (k === " " || k === "Spacebar") {
      e.preventDefault();
      if (e.ctrlKey) { selectColumn(); }           // Ctrl+Space: column range
      else if (e.shiftKey) { selectRowRange(); }   // Shift+Space: row range
      else { toggleSelect(cell); }                 // Space: bulk row (checkbox)
      return;
    }
    if (k === "Delete") {
      e.preventDefault();
      var sel = Array.prototype.slice.call(
        g.querySelectorAll('tbody tr.wag-rowsel'))
        .map(function (tr) { return parseInt(tr.getAttribute("data-row"), 10); });
      if (!sel.length) { var r = rowOf(cell); if (r >= 0) { sel = [r]; } }
      if (sel.length) { post({ action: "delete", rows: sel }); }
      return;
    }
    if (k === "ContextMenu" || (e.shiftKey && k === "F10")) {
      e.preventDefault();
      post({ action: "context", row: rowOf(cell), col: colIndexOf(cell) });
      return;
    }
    // Type-to-replace (Excel): a printable key on an editable cell starts editing
    // with that character. Space is reserved for selection, not editing.
    if (isPrintable(e) && e.key !== " " && cell.getAttribute("data-editable") === "1") {
      var meta = cols[colIndexOf(cell)] || {};
      if (meta.editor !== "checkbox") { e.preventDefault(); enterEdit(cell, e.key); return; }
    }
    if (navigate(cell, k, e.ctrlKey, e.shiftKey)) { e.preventDefault(); }
  });

  // Context menu via the DOM `contextmenu` event, not just the ContextMenu key.
  // This is the path that works under VoiceOver on macOS: there is no Applications
  // key, and VoiceOver's "open menu" gesture (VO+Shift+M) — plus a right-click and
  // a trackpad secondary-click — dispatches a `contextmenu` event, never a keydown.
  // Because VoiceOver also intercepts the arrows, this event is the ONLY way a
  // VoiceOver user can reach the native row menu where row selection lives. Map it
  // to the cell under the pointer, else the active cell, and hand off to the host.
  document.addEventListener("contextmenu", function (e) {
    var g = grid();
    if (!g) { return; }
    var t = e.target;
    var cell = (t && t.closest)
      ? t.closest('#wag-grid [role="gridcell"], #wag-grid [role="rowheader"]')
      : null;
    if (!cell) { cell = activeCell(); }
    if (!cell || !g.contains(cell)) { return; }
    e.preventDefault();
    if (!editing) { setActive(cell); }
    post({ action: "context", row: rowOf(cell), col: colIndexOf(cell) });
  });

  // A SELECT commits when its value changes; any editor commits if focus
  // genuinely leaves it (clicked away), so we never strand the edit state.
  document.addEventListener("change", function (e) {
    if (editing && e.target === editing.querySelector(".wag-editor") &&
        e.target.tagName === "SELECT") { commitEdit(); }
  });
  document.addEventListener("focusout", function (e) {
    if (editing && e.target === editing.querySelector(".wag-editor")) {
      setTimeout(function () {
        if (editing && !editing.contains(document.activeElement) &&
            document.activeElement !== grid()) { commitEdit(); }
      }, 0);
    }
  });

  // Entering the table with no active descendant yet: anchor on the first cell.
  document.addEventListener("focusin", function (e) {
    var g = grid();
    if (g && e.target === g && !activeCell()) {
      var f = g.querySelector('tbody [role="gridcell"], tbody [role="rowheader"]');
      if (f) { setActive(f); }
    }
  });

  // ----- API Python calls back -----------------------------------------

  window.__wag = {
    __installed: true,
    setColumns: function (meta) { cols = meta || []; },
    // Authoritative display after a validated edit; announce the result politely.
    setCell: function (row, col, display, message) {
      var c = document.getElementById("wag-r" + row + "-c" + col);
      if (c) {
        setCellText(c, display);  // keeps the hidden control-type suffix span intact
        // keep data-raw in step for editors (checkbox/slider/stepper) that read it
        if (c.hasAttribute("data-raw")) {
          c.setAttribute("data-raw", display === "Yes" ? "true" : display === "No" ? "false" : display);
        }
      }
      // Always confirm: the model's message if any, else the authoritative value,
      // so the user never hears silence after an edit (and never a double-speak).
      announce(message || display, false);
    },
    // Edit rejected: say why (assertively), reopen the editor, and bake the
    // reason into its name so it's still spoken when focus lands on the field.
    editFailed: function (row, col, message) {
      announce(message, true);
      var c = document.getElementById("wag-r" + row + "-c" + col);
      if (c) {
        setActive(c); enterEdit(c);
        var el = c.querySelector(".wag-editor");
        if (el) {
          el.setAttribute("aria-invalid", "true");
          el.setAttribute("aria-label", (el.getAttribute("aria-label") || "value") + ", " + message);
        }
      }
    },
    // Replace just the tbody (paging / delete): the table element survives, so
    // focus and focus mode are never lost.
    setRows: function (html, focusRow, focusCol, rowcount) {
      var g = grid();
      if (!g || !g.tBodies.length) { return; }
      g.tBodies[0].innerHTML = html;        // new cells render tabindex=-1
      if (rowcount != null) { g.setAttribute("aria-rowcount", rowcount); }
      window.__wag.focusCell(focusRow, focusCol);   // sets the roving 0 + real focus
    },
    removeRow: function (row) {
      var tr = document.querySelector('#wag-grid tbody tr[data-row="' + row + '"]');
      if (tr) { tr.parentNode.removeChild(tr); }
    },
    announce: function (t, assertive) { announce(t, !!assertive); },
    // Move the roving focus to an absolute cell (after a re-render). A plain
    // landing: collapse any range and re-anchor.
    focusCell: function (row, col) {
      var c = document.getElementById("wag-r" + row + "-c" + (col || 0));
      if (!c) { var tr = grid() && grid().querySelector("tbody tr"); c = tr && tr.cells[col || 0]; }
      if (c) { setActive(c); clearRange(); anchor = inHeader(c) ? null : domCoords(c); }
    },
    // Open the editor on an absolute cell (used by the host's context-menu "Edit").
    editCell: function (row, col) {
      var c = document.getElementById("wag-r" + row + "-c" + (col || 0));
      if (c) { setActive(c); enterEdit(c); }
    },
    // Checkbox-free row selection for the host's context menu (the path that works
    // under VoiceOver). selectRow adds one row; selectRowRange selects from the last
    // selected row through this one.
    selectRow: function (row) { selectRow(row); },
    selectRowRange: function (row) { selectRowRangeTo(row); },
    // Bulk select-all / clear for the host's Edit menu.
    selectAllRows: function () { selectAllRows(); },
    clearSelection: function () { clearAllSelection(); },
    // Make the grid LIVE: put REAL focus on a cell (default the first, or the
    // given one) and announce it. The host calls this on open / focus() so arrows
    // and Tab work immediately, without the user having to tab onto the grid.
    enterGrid: function (row, col) {
      var g = grid(); if (!g) { return; }
      var c = (row != null) ? document.getElementById("wag-r" + row + "-c" + (col || 0)) : null;
      if (!c) { c = g.querySelector('tbody [role="gridcell"], tbody [role="rowheader"]'); }
      if (c) { setActive(c); clearRange(); anchor = inHeader(c) ? null : domCoords(c); announceCell(c, true); }
    }
  };

  // Give the first body cell the roving tabindex=0 so there is a tab stop into
  // the grid even before the host calls enterGrid().
  (function () {
    var g = grid();
    if (g && !g.querySelector('tbody [tabindex="0"]')) {
      var first = g.querySelector('tbody [role="gridcell"], tbody [role="rowheader"]');
      if (first) { activeId = first.id; first.setAttribute("tabindex", "0"); first.classList.add("wag-active"); }
    }
  })();
})();
"""


def runtime_js(handler_name: str) -> str:
    """The runtime script, bound to a specific WebView bridge handler name."""
    return _RUNTIME.replace("__HANDLER__", handler_name)
