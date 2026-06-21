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
table.wag-grid tbody tr[aria-selected="true"] {
  background: var(--wag-sel-bg, #cde4ff); color: var(--wag-sel-fg, #000);
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
_RUNTIME = r"""
(function () {
  if (window.__wag && window.__wag.__installed) { return; }
  var HANDLER = "__HANDLER__";
  var cols = [];        // column metadata, pushed by Python
  var editing = null;   // the cell currently in edit mode, or null
  var activeId = null;  // id of the active (descendant) cell

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
    el.textContent = "";
    var set = function () { el.textContent = text; };
    if (window.requestAnimationFrame) { window.requestAnimationFrame(set); }
    else { setTimeout(set, 16); }
  }

  function bodyRows() {
    var g = grid();
    return g && g.tBodies.length ? Array.prototype.slice.call(g.tBodies[0].rows) : [];
  }
  function headRow() { var g = grid(); return g && g.tHead ? g.tHead.rows[0] : null; }
  function cellsOf(tr) { return tr ? Array.prototype.slice.call(tr.cells) : []; }
  function activeCell() { return activeId ? document.getElementById(activeId) : null; }
  function colIndexOf(cell) { return parseInt(cell.getAttribute("data-col"), 10) || 0; }
  function rowOf(cell) {
    var tr = cell.closest("tr"); var r = tr && tr.getAttribute("data-row");
    return r == null ? -1 : parseInt(r, 10);   // -1 means the header row
  }

  // Make a cell the active descendant — no .focus() on the cell, so NVDA stays
  // in focus mode on the table and focus never transits document.body.
  function setActive(cell) {
    if (!cell) { return; }
    activeId = cell.id;
    var g = grid();
    if (g) {
      g.setAttribute("aria-activedescendant", cell.id);
      var prev = g.querySelector(".wag-active");
      if (prev && prev !== cell) { prev.classList.remove("wag-active"); }
    }
    cell.classList.add("wag-active");
    try { cell.scrollIntoView({ block: "nearest", inline: "nearest" }); } catch (e) {}
  }
  function focusGrid() { var g = grid(); if (g) { g.focus(); } }

  function moveTo(tr, colIdx) {
    if (!tr) { return; }
    var cells = cellsOf(tr);
    if (!cells.length) { return; }
    colIdx = Math.max(0, Math.min(colIdx, cells.length - 1));
    setActive(cells[colIdx]);
  }

  function navigate(cell, key, ctrl) {
    var tr = cell.closest("tr");
    var inHead = tr.parentNode && tr.parentNode.tagName === "THEAD";
    var rows = bodyRows();
    var ci = cellsOf(tr).indexOf(cell);
    if (key === "ArrowRight") { moveTo(tr, ci + 1); }
    else if (key === "ArrowLeft") { moveTo(tr, ci - 1); }
    else if (key === "ArrowDown") {
      if (inHead) { if (rows.length) { moveTo(rows[0], ci); } }
      else {
        var ri = rows.indexOf(tr);
        if (ri < rows.length - 1) { moveTo(rows[ri + 1], ci); }
        else { focusGrid(); post({ action: "page", dir: "next", col: ci, fromRow: rowOf(cell) }); }
      }
    }
    else if (key === "ArrowUp") {
      if (inHead) { announce("Top of grid"); }
      else {
        var ri2 = rows.indexOf(tr);
        if (ri2 > 0) { moveTo(rows[ri2 - 1], ci); }
        else { var hr = headRow(); if (hr) { moveTo(hr, ci); } }
      }
    }
    else if (key === "Home") { moveTo(ctrl ? rows[0] : tr, 0); }
    else if (key === "End") { moveTo(ctrl ? rows[rows.length - 1] : tr, cellsOf(tr).length - 1); }
    else if (key === "PageDown") { focusGrid(); post({ action: "page", dir: "next", col: ci }); }
    else if (key === "PageUp") { focusGrid(); post({ action: "page", dir: "prev", col: ci }); }
    else { return false; }
    return true;
  }

  function toggleSelect(cell) {
    var row = rowOf(cell);
    if (row < 0) { announce("Move to a data row to select"); return; }
    var tr = cell.closest("tr");
    var now = tr.getAttribute("aria-selected") !== "true";
    tr.setAttribute("aria-selected", now ? "true" : "false");
    cellsOf(tr).forEach(function (c) { c.setAttribute("aria-selected", now ? "true" : "false"); });
    var count = grid().querySelectorAll('tbody tr[aria-selected="true"]').length;
    var label = tr.querySelector('[role="rowheader"]');
    label = label ? label.textContent.trim() : String(row + 1);
    announce("Row " + label + (now ? " selected" : " unselected") +
             ", " + count + (count === 1 ? " row" : " rows") + " selected");
    post({ action: "select", row: row, selected: now, count: count });
  }

  // ----- editing -------------------------------------------------------

  function buildEditor(cell) {
    var meta = cols[colIndexOf(cell)] || {};
    var kind = meta.editor || "text";
    var raw = cell.getAttribute("data-raw");
    var value = raw != null ? raw : cell.textContent.trim();
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

  function enterEdit(cell) {
    if (editing) { return; }
    if (cell.getAttribute("data-editable") !== "1") { announce("This cell is read only"); return; }
    cell.__orig = cell.innerHTML;
    var el = buildEditor(cell);
    cell.innerHTML = "";
    cell.appendChild(el);
    editing = cell;
    el.focus();
    if (el.select) { try { el.select(); } catch (e) {} }
  }

  // Always restore the grid as the focused element and the cell as its active
  // descendant *before* tearing the editor out, so focus never lands on body.
  function leaveEdit(cell) {
    editing = null;
    focusGrid();
    setActive(cell);
  }

  function commitEdit() {
    if (!editing) { return; }
    var cell = editing;
    var el = cell.querySelector(".wag-editor");
    var value = readEditor(el);
    var isCheck = el.type === "checkbox";
    post({ action: "edit", row: rowOf(cell), col: colIndexOf(cell), value: value });
    // Optimistic text; Python's setCell() delivers the authoritative value.
    cell.innerHTML = isCheck ? (value === "true" ? "Yes" : "No") : el.value;
    leaveEdit(cell);
  }

  function cancelEdit() {
    if (!editing) { return; }
    var cell = editing;
    cell.innerHTML = cell.__orig != null ? cell.__orig : cell.innerHTML;
    leaveEdit(cell);
    announce("Edit cancelled");
  }

  // ----- key handling --------------------------------------------------

  document.addEventListener("keydown", function (e) {
    if (editing) {
      var ed = editing.querySelector(".wag-editor");
      if (e.key === "Enter") {
        // A SELECT confirms its own option on Enter; commit on change instead.
        if (ed && ed.tagName === "SELECT") { return; }
        e.preventDefault(); commitEdit();
      } else if (e.key === "Escape") { e.preventDefault(); cancelEdit(); }
      else if (e.key === "Tab") { commitEdit(); }  // commit, then let Tab move on
      return;
    }
    var g = grid();
    if (!g || document.activeElement !== g) { return; }
    var cell = activeCell();
    if (!cell) {
      var first = g.querySelector('tbody [role="gridcell"], tbody [role="rowheader"]');
      if (first) { setActive(first); }
      return;
    }
    var k = e.key;
    if (k === "F2" || k === "Enter") {
      if (!e.repeat) { e.preventDefault(); enterEdit(cell); }
      return;
    }
    if (k === " " || k === "Spacebar") { e.preventDefault(); toggleSelect(cell); return; }
    if (k === "Delete") {
      e.preventDefault();
      var sel = Array.prototype.slice.call(
        g.querySelectorAll('tbody tr[aria-selected="true"]'))
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
    if (navigate(cell, k, e.ctrlKey)) { e.preventDefault(); }
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
      if (c) { c.textContent = display; }
      if (message) { announce(message, false); }
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
      g.tBodies[0].innerHTML = html;
      if (rowcount != null) { g.setAttribute("aria-rowcount", rowcount); }
      g.focus();
      window.__wag.focusCell(focusRow, focusCol);
    },
    removeRow: function (row) {
      var tr = document.querySelector('#wag-grid tbody tr[data-row="' + row + '"]');
      if (tr) { tr.parentNode.removeChild(tr); }
    },
    announce: function (t, assertive) { announce(t, !!assertive); },
    // Move the active descendant to an absolute cell (after a page change).
    focusCell: function (row, col) {
      var c = document.getElementById("wag-r" + row + "-c" + (col || 0));
      if (!c) { var tr = grid() && grid().querySelector("tbody tr"); c = tr && tr.cells[col || 0]; }
      if (c) { focusGrid(); setActive(c); }
    }
  };

  // Anchor the active descendant on the first cell so Tab into the grid (and
  // the first arrow) has somewhere to start.
  (function () {
    var g = grid();
    if (g && !activeCell()) {
      var first = g.querySelector('tbody [role="gridcell"], tbody [role="rowheader"]');
      if (first) {
        activeId = first.id;
        g.setAttribute("aria-activedescendant", first.id);
        first.classList.add("wag-active");
      }
    }
  })();
})();
"""


def runtime_js(handler_name: str) -> str:
    """The runtime script, bound to a specific WebView bridge handler name."""
    return _RUNTIME.replace("__HANDLER__", handler_name)
