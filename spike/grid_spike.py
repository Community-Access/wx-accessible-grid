"""Standalone decision spike for the accessible grid — run on Windows with NVDA,
then JAWS, to settle two open questions before the real rebuild.

    python spike/grid_spike.py

This is a THROWAWAY comparison harness. It does NOT use the wx-accessible-grid
library runtime; it implements both candidate models inline so you can flip
between them live and hear how each reads. One file, one small grid (8 rows x 5
columns: a channel-number row header, a human "Channel N" label, and editable
text / combo / number columns).

What you are comparing, switchable live from inside the grid and announced:

  CURSOR MODEL  (press F8 to switch)
    A  aria-activedescendant: the table is the only focusable element; the active
       cell is the active descendant; cells are never .focus()ed.
    B  roving tabindex: the active gridcell gets tabindex=0 and REAL DOM focus;
       every other cell is tabindex=-1; the table has no aria-activedescendant.

  TAB BEHAVIOUR  (press F9 to switch)
    walk    Tab / Shift+Tab move cell to cell and wrap; the grid owns Tab.
    single  Tab exits the grid; arrows move within it.

There are NO buttons. The window opens with focus already inside the grid on the
first cell, so you never have to tab into the webview.

Agreed behaviours, the same in both cursor models:
  * Escape is the exit. While editing, Escape cancels the edit and stays in the
    grid; while navigating, Escape LEAVES the grid (focus moves to the "Outside
    the grid" line in the page; Tab from there returns to the grid). So "Escape
    once to cancel, Escape again to leave." F6 also leaves.
  * Plain arrows move and say nothing about selection. Shift+arrow extends a
    rectangular range from the anchor and announces "Selected B2 to B5, N cells"
    through a polite live region. A plain arrow collapses back to one cell.
  * F2 or just typing edits in place (real focus into an input). Enter commits
    and moves down a row. Escape cancels.
  * Moving speaks the cell value; a vertical move leads with the row label
    ("Channel 5"). No "column N" noise.
"""

from __future__ import annotations

import wx

from wx_accessible_webview import DEFAULT_STYLES, AccessibleWebView

MODES = ["FM", "NFM", "AM", "USB", "LSB"]
ROWS = 8
HANDLER = "spike"

SPIKE_CSS = """
.sr-only { position: absolute !important; width: 1px; height: 1px; overflow: hidden;
  clip: rect(0 0 0 0); clip-path: inset(50%); white-space: nowrap; border: 0; margin: -1px; padding: 0; }
table.spike { border-collapse: collapse; width: 100%; font: inherit; }
table.spike caption { text-align: left; font-weight: 600; }
table.spike th, table.spike td { border: 1px solid #888; padding: .25rem .5rem; text-align: left; }
table.spike thead th { position: sticky; top: 0; background: #eee; }
table.spike:focus { outline: 2px solid #0a5ad6; }
table.spike .active { outline: 3px solid #0a5ad6; outline-offset: -3px; }
table.spike [aria-selected="true"] { background: #cde4ff; }
.spike-help { margin: .25rem 0 .5rem; }
"""


def _grid_html() -> str:
    rows = []
    for r in range(ROWS):
        num = r + 1
        label = f"Channel {num}"
        freq = f"{146 + r}.{(500 + r * 5) % 1000:03d}"
        mode = MODES[r % len(MODES)]
        power = r % 6
        rows.append(
            f'<tr role="row" data-row="{r}" data-label="{label}">'
            f'<th role="rowheader" id="c-{r}-0" data-r="{r}" data-c="0">{num}</th>'
            f'<td role="gridcell" id="c-{r}-1" data-r="{r}" data-c="1">{label}</td>'
            f'<td role="gridcell" id="c-{r}-2" data-r="{r}" data-c="2" data-edit="text">{freq}</td>'
            f'<td role="gridcell" id="c-{r}-3" data-r="{r}" data-c="3" data-edit="combo">{mode}</td>'
            f'<td role="gridcell" id="c-{r}-4" data-r="{r}" data-c="4" data-edit="number">{power}</td>'
            f"</tr>"
        )
    body = "".join(rows)
    return (
        "<h1>Grid cursor and tab spike</h1>"
        '<p class="spike-help">It starts you inside the grid. F8 switches cursor model '
        "(A active-descendant / B roving focus). F9 switches Tab behaviour (walk cells / single "
        "tab stop). Arrows move, F2 or type to edit, Shift+arrow selects, Escape leaves the grid.</p>"
        '<p id="spike-exit" tabindex="-1">Outside the grid. Tab to return to it.</p>'
        '<div id="spike-move" class="sr-only" aria-live="polite" aria-atomic="true"></div>'
        '<div id="spike-sel" class="sr-only" aria-live="polite" aria-atomic="true"></div>'
        '<table id="spike-grid" class="spike" role="grid" aria-label="Sample channels" tabindex="0">'
        "<caption>Sample channels</caption>"
        '<thead><tr role="row">'
        '<th role="columnheader">#</th><th role="columnheader">Label</th>'
        '<th role="columnheader">Freq</th><th role="columnheader">Mode</th>'
        '<th role="columnheader">Power</th></tr></thead>'
        f"<tbody>{body}</tbody></table>"
    )


_SPIKE_JS = r"""
(function () {
  if (window.__spike) { return; }
  var H = "__HANDLER__";
  var MODES = ["FM", "NFM", "AM", "USB", "LSB"];
  var ROWS = __ROWS__, COLS = 5;
  var mode = "A", tab = "walk";
  var active = { r: 0, c: 0 }, anchor = { r: 0, c: 0 }, editing = null;

  function grid() { return document.getElementById("spike-grid"); }
  function post(m) { m.type = "spike"; try { window[H].postMessage(JSON.stringify(m)); } catch (e) {} }
  function say(id, t) {
    var el = document.getElementById(id); if (!el) { return; }
    // Clear then re-set on a real timer task so identical text re-announces and
    // it works even when the window isn't actively rendering (rAF is throttled).
    el.textContent = "";
    setTimeout(function () { el.textContent = t; }, 0);
  }
  function sayMove(t) { say("spike-move", t); }
  function saySel(t) { say("spike-sel", t); }

  function cellAt(r, c) { return document.getElementById("c-" + r + "-" + c); }
  function rowLabel(r) {
    var tr = document.querySelector('#spike-grid tbody tr[data-row="' + r + '"]');
    return tr ? tr.getAttribute("data-label") : ("Row " + (r + 1));
  }
  function colLetter(c) { return String.fromCharCode(65 + c); }
  function coord(r, c) { return colLetter(c) + (r + 1); }
  function cellText(cell) { return cell ? cell.textContent.trim() : ""; }
  function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)); }
  function focusInGrid() { var g = grid(); return !!(g && (document.activeElement === g || g.contains(document.activeElement))); }

  // The whole point of the spike: the two cursor models, swapped in place.
  function applyCursor(focusIt) {
    var g = grid(); if (!g) { return; }
    var act = cellAt(active.r, active.c);
    var prev = g.querySelector(".active"); if (prev) { prev.classList.remove("active"); }
    if (act) { act.classList.add("active"); }
    var allCells = g.querySelectorAll('tbody [role="gridcell"], tbody [role="rowheader"]');
    if (mode === "A") {
      g.setAttribute("tabindex", "0");
      if (act) { g.setAttribute("aria-activedescendant", act.id); }
      Array.prototype.forEach.call(allCells, function (c) { c.removeAttribute("tabindex"); });
      if (focusIt) { g.focus(); }
    } else {
      g.removeAttribute("aria-activedescendant");
      g.setAttribute("tabindex", "-1");
      Array.prototype.forEach.call(allCells, function (c) { c.setAttribute("tabindex", c === act ? "0" : "-1"); });
      if (focusIt && act) { act.focus(); }
    }
  }

  function announceMove(vertical) {
    var v = cellText(cellAt(active.r, active.c));
    if (vertical) { sayMove(rowLabel(active.r) + (v ? ", " + v : "")); }
    else { sayMove(v || coord(active.r, active.c)); }
  }
  function clearSelection() {
    Array.prototype.forEach.call(grid().querySelectorAll('[aria-selected="true"]'),
      function (c) { c.removeAttribute("aria-selected"); });   // omit, never set "false"
  }
  function moveTo(r, c, vertical) {
    r = clamp(r, 0, ROWS - 1); c = clamp(c, 0, COLS - 1);
    active = { r: r, c: c }; anchor = { r: r, c: c };
    clearSelection(); applyCursor(true); announceMove(vertical);
  }
  function extend(r, c) {
    r = clamp(r, 0, ROWS - 1); c = clamp(c, 0, COLS - 1);
    active = { r: r, c: c }; applyCursor(true); clearSelection();
    var r0 = Math.min(anchor.r, r), r1 = Math.max(anchor.r, r);
    var c0 = Math.min(anchor.c, c), c1 = Math.max(anchor.c, c);
    var n = 0;
    for (var rr = r0; rr <= r1; rr++) {
      for (var cc = c0; cc <= c1; cc++) {
        var cel = cellAt(rr, cc); if (cel) { cel.setAttribute("aria-selected", "true"); n++; }
      }
    }
    saySel("Selected " + coord(anchor.r, anchor.c) + " to " + coord(r, c) + ", " + n + (n === 1 ? " cell" : " cells"));
  }

  function editCell(cell, seed) {
    if (editing) { return; }
    var type = cell.getAttribute("data-edit"); if (!type) { sayMove("Read only"); return; }
    cell.__orig = cell.innerHTML;
    var el;
    if (type === "combo") {
      el = document.createElement("select");
      MODES.forEach(function (m) {
        var o = document.createElement("option"); o.value = m; o.textContent = m;
        if (m === cellText(cell)) { o.selected = true; } el.appendChild(o);
      });
    } else {
      el = document.createElement("input"); el.type = (type === "number") ? "number" : "text";
      el.value = cellText(cell);
    }
    el.setAttribute("aria-label", "edit"); el.style.width = "100%";
    cell.innerHTML = ""; cell.appendChild(el); editing = cell;
    if (seed != null) {
      if (el.tagName === "SELECT") {
        var s = seed.toLowerCase();
        for (var i = 0; i < el.options.length; i++) {
          if (el.options[i].text.toLowerCase().indexOf(s) === 0) { el.selectedIndex = i; break; }
        }
      } else { el.value = seed; }
    }
    el.focus(); if (seed == null && el.select) { try { el.select(); } catch (e) {} }
  }
  function commitEdit(moveDown) {
    if (!editing) { return; }
    var cell = editing; var el = cell.querySelector("input,select");
    cell.textContent = el.value; editing = null;
    if (moveDown) {
      active = { r: clamp(active.r + 1, 0, ROWS - 1), c: active.c };
      anchor = { r: active.r, c: active.c }; clearSelection(); applyCursor(true); announceMove(true);
    } else { applyCursor(true); announceMove(false); }
  }
  function cancelEdit() {
    if (!editing) { return; }
    var cell = editing; cell.innerHTML = cell.__orig; editing = null;
    applyCursor(true); sayMove("Edit cancelled");
  }
  function leaveGrid() {
    // Move DOM focus to a real, non-button focusable target IN the page (the
    // "Outside the grid" line, tabindex=-1) so focus leaves the grid without a
    // button and without any native/web focus dance. Tab from there re-enters.
    var ex = document.getElementById("spike-exit");
    if (ex) { try { ex.focus(); } catch (e) {} }
    sayMove("Left grid. Tab to return to the grid.");
  }

  function tabMove(forward) {
    var r = active.r, c = active.c;
    if (forward) {
      if (c < COLS - 1) { moveTo(r, c + 1, false); }
      else if (r < ROWS - 1) { moveTo(r + 1, 0, false); }
      else { sayMove("End of grid"); }
    } else {
      if (c > 0) { moveTo(r, c - 1, false); }
      else if (r > 0) { moveTo(r - 1, COLS - 1, false); }
      else { sayMove("Start of grid"); }
    }
  }

  document.addEventListener("keydown", function (e) {
    if (editing) {
      if (e.key === "Enter") { if (editing.querySelector("select")) { return; } e.preventDefault(); commitEdit(true); }
      else if (e.key === "Escape") { e.preventDefault(); cancelEdit(); }       // cancel, STAY
      else if (e.key === "Tab") {
        if (tab === "walk") { e.preventDefault(); commitEdit(false); tabMove(!e.shiftKey); }
        else { commitEdit(false); }                                            // single: let Tab exit
      }
      return;
    }
    if (!focusInGrid()) { return; }
    var k = e.key;
    if (k === "F8") { e.preventDefault(); mode = (mode === "A" ? "B" : "A"); applyCursor(true); sayMove("Cursor model " + mode + (mode === "A" ? ", active descendant" : ", roving focus")); return; }
    if (k === "F9") { e.preventDefault(); tab = (tab === "walk" ? "single" : "walk"); sayMove("Tab " + (tab === "walk" ? "walks cells" : "single tab stop")); return; }
    if (k === "F6") { e.preventDefault(); leaveGrid(); return; }
    if (k === "Escape") { e.preventDefault(); leaveGrid(); return; }            // navigating: LEAVE
    if (k === "Tab") { if (tab === "walk") { e.preventDefault(); tabMove(!e.shiftKey); } return; }
    if (k === "F2") { e.preventDefault(); editCell(cellAt(active.r, active.c)); return; }
    if (k === "Enter") { e.preventDefault(); editCell(cellAt(active.r, active.c)); return; }
    if (k === "ArrowRight") { e.preventDefault(); e.shiftKey ? extend(active.r, active.c + 1) : moveTo(active.r, active.c + 1, false); return; }
    if (k === "ArrowLeft") { e.preventDefault(); e.shiftKey ? extend(active.r, active.c - 1) : moveTo(active.r, active.c - 1, false); return; }
    if (k === "ArrowDown") { e.preventDefault(); e.shiftKey ? extend(active.r + 1, active.c) : moveTo(active.r + 1, active.c, true); return; }
    if (k === "ArrowUp") { e.preventDefault(); e.shiftKey ? extend(active.r - 1, active.c) : moveTo(active.r - 1, active.c, true); return; }
    if (k === "Home") { e.preventDefault(); e.ctrlKey ? moveTo(0, 0, true) : moveTo(active.r, 0, false); return; }
    if (k === "End") { e.preventDefault(); e.ctrlKey ? moveTo(ROWS - 1, COLS - 1, true) : moveTo(active.r, COLS - 1, false); return; }
    if (!e.ctrlKey && !e.altKey && !e.metaKey && typeof e.key === "string" && e.key.length === 1) {
      var cell = cellAt(active.r, active.c);
      if (cell.getAttribute("data-edit")) { e.preventDefault(); editCell(cell, e.key); }
      return;
    }
  });

  window.__spike = {
    setMode: function (m) { mode = m; applyCursor(true); sayMove("Cursor model " + m + (m === "A" ? ", active descendant" : ", roving focus")); },
    setTab: function (t) { tab = t; applyCursor(true); sayMove("Tab " + (t === "walk" ? "walks cells" : "single tab stop")); },
    getMode: function () { return mode; },
    getTab: function () { return tab; },
    enterGrid: function () {
      active = { r: 0, c: 0 }; anchor = { r: 0, c: 0 }; clearSelection(); applyCursor(true);
      sayMove("Arrows move, F2 or type to edit, Shift+arrow selects, Escape leaves the grid. Cursor model " +
              mode + ", Tab " + (tab === "walk" ? "walks cells" : "single tab stop"));
    }
  };
})();
"""


def spike_js() -> str:
    return _SPIKE_JS.replace("__HANDLER__", HANDLER).replace("__ROWS__", str(ROWS))


class SpikeFrame(wx.Frame):
    """No buttons. The webview fills the window and you start INSIDE the grid;
    F8/F9 switch the models, Escape/F6 leave to the in-page "Outside the grid"
    line, and Tab re-enters. No control to tab into a webview (the macOS
    Full-Keyboard-Access trap), because focus starts in the grid."""

    def __init__(self) -> None:
        super().__init__(None, title="Grid cursor + tab spike", size=(900, 560))
        panel = wx.Panel(self)
        self.view = AccessibleWebView(
            panel,
            title="Grid spike",
            handler_name=HANDLER,
            live_region=False,
            on_message=self._on_message,
            styles=DEFAULT_STYLES + SPIKE_CSS,
            initial_html=_grid_html(),
        )
        if self.view.using_webview:
            import wx.html2 as webview

            self._installed = False
            self.view.view.Bind(webview.EVT_WEBVIEW_LOADED, self._on_loaded)

        outer = wx.BoxSizer(wx.VERTICAL)
        outer.Add(self.view.control, 1, wx.EXPAND)
        panel.SetSizer(outer)
        self.Show()

    def _on_loaded(self, event) -> None:
        event.Skip()
        if getattr(self, "_installed", True):
            return
        self._installed = True

        def install():
            # Install the runtime, then auto-enter the grid so the cursor starts
            # on the first cell (no button, no tabbing into the webview). Off the
            # loaded-event call stack (CallLater, not CallAfter) to dodge the
            # nested-loaded RunScript bug.
            self.view.run_js(spike_js())
            self.view.focus()
            self.view.run_js("window.__spike&&window.__spike.enterGrid();")

        wx.CallLater(60, install)

    def _on_message(self, data) -> None:
        # The bridge is only used by the test harness (probe messages); leaving
        # the grid is handled entirely in-page now.
        return


def main() -> None:
    app = wx.App()
    SpikeFrame()
    app.MainLoop()


if __name__ == "__main__":
    main()
