# Agent notes — wx-accessible-grid

Handoff log. Read this first; update it as you go.

## What this is

A reusable, accessible, editable data grid for wxPython, spun out the same way as
its siblings `wx-accessible-webview` and `wx-accessible-menubar`. Community Access
open-source, MIT, created by Taylor Arndt. First consumer is VRP (the accessible
radio programmer), whose channel grid is the motivating use case.

The hard problem it solves: native `wx.grid.Grid` is inaccessible, and earlier
in-grid editing attempts in VRP made NVDA re-read the whole table on every
keystroke (so they fell back to a read-only table plus a native edit dialog).
The fix here is a real `<table role="grid">` with a roving tabindex, so NVDA goes
into focus mode and reads only the focused cell plus the headers that changed.

## Architecture

- `model.py` — `GridModel` (subclass it), `Column` (with one of five editors:
  text, combo, checkbox, slider, stepper, plus `none`), `SetResult`. The model
  owns all data, validation, and persistence; the grid never mutates data
  directly. wx-free, unit tested.
- `render.py` — renders the model to ARIA grid HTML one page at a time.
  `aria-rowcount` = total + 1 (header), `aria-rowindex` absolute (header = 1,
  first data row = 2). wx-free, unit tested.
- `assets.py` — `GRID_CSS` and the vanilla-JS runtime (`runtime_js(handler)`).
  The runtime is delegated off `document` so it survives re-renders; it manages
  the roving tabindex, navigation, selection, the five in-cell editors, and the
  Python bridge. `window.__wag` exposes setColumns/setCell/editFailed/removeRow/
  announce/focusCell for Python to call back.
- `grid.py` — `AccessibleGrid` widget. Owns an `AccessibleWebView`, installs the
  runtime on load (EVT_WEBVIEW_LOADED + CallAfter), pushes column metadata,
  renders pages, and brokers edit/select/delete/page/context bridge messages to
  the model. `grid.control` goes in a sizer.
- `examples/demo.py` — standalone 2,500-row demo with all five editors (run it
  with NVDA on Windows). `tests/` — model + renderer tests (no wx needed).

## Bridge protocol

Page to Python (all `{type:"wag", action, ...}`): `edit{row,col,value}`,
`select{row,selected,count}`, `delete{rows}`, `page{dir,col,fromRow}`,
`context{row,col}`. `col` is the 0-based column index; `row` is the absolute
0-based row index.

## Focus model (important — read before editing assets.py/render.py)

The grid uses the **aria-activedescendant** pattern, NOT roving tabindex. The
`<table>` is the only focusable element (`tabindex=0`) and owns
`aria-activedescendant`; the runtime moves that to the active cell's id instead
of calling `cell.focus()`. This is deliberate: the accessibility-lead review
found a focused `role=gridcell` with roving tabindex does NOT reliably put NVDA
in focus mode under WebView2 (arrows would be dead), and every innerHTML swap
bounced focus through document.body and out of focus mode. activedescendant fixes
both. Do not "simplify" back to roving tabindex + cell.focus().

Paging and delete replace ONLY the tbody (`window.__wag.setRows`) so the table
element — and thus focus + focus mode — survives. Full `set_content` is only used
for the initial render and `refresh()`.

## Status (2026-06-20)

- Built v0.1.0. accessibility-lead review done (4 specialists). It was a NO-SHIP;
  all three Criticals fixed: (1) migrated to aria-activedescendant; (2) edit/
  delete/page no longer drop focus to body; (3) two real aria-live regions are
  rendered (polite + assertive) and success edits now announce the authoritative
  value. Should-fix items also applied: Tab/blur edit trap, read-only announce on
  F2, header-row navigation, page-edge guards, cell-level aria-selected,
  aria-invalid + message-in-name on reject, identical-text re-announce. (A few
  nice-to-haves from the review remain, noted in the review output.)
- 11 unit tests pass (`PYTHONPATH=src pytest`). Mac WKWebView smoke passes:
  build, edit (incl. reject keeps old value), paging, delete, runtime install.
- WIRED INTO VRP and tested against a real CHIRP image (Baofeng UV-5R, 128
  channels): all real columns render, name edit persisted (and the UV-5R's name
  truncation came back as the authoritative display — the round-trip works), bad
  frequency rejected. VRP files: `vrp/channel_grid_model.py` (ChannelGridModel),
  `tools/grid_preview.py` (launcher), dep added to VRP pyproject + installed
  editable. VRP's own 63 tests still pass.
- NOT yet verified on Windows + NVDA/WebView2 — the make-or-break test, next
  milestone. On the Parallels VM: `uv run python tools/grid_preview.py` in the
  VRP clone (see windows-parallels-prlctl memory). The review's step-by-step VM
  test script is in that review output; step 1 (Tab in, press Down, expect a
  sibling cell, not a document line) is the focus-mode gate.
- VRP's read-only table + native edit dialog are left in place; the grid is a
  preview/beta path until NVDA proves out, then it replaces the channels view
  (keep the dialog as the full-row fallback).
- No git commits yet (Taylor commits/pushes himself). No PyPI release yet.

## Testing

- `PYTHONPATH=src <python-with-wx> -m pytest -q` — model + renderer.
- `pip install -e ".[dev]"` then `pytest` in a clean env.
- Real test is manual: `python examples/demo.py` with a screen reader. Drive the
  arrow navigation, F2/Enter editing for each editor, Space selection, Delete,
  and the context-menu key, and confirm the announcements.

## Conventions

Mirror the sibling libs: hatchling build, `src/` layout, MIT, ruff line length
100, dependency-light (wxPython + wx-accessible-webview). No emojis, no markdown
tables in docs (screen-reader rule).
