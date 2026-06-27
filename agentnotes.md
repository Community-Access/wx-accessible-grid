# Agent notes — wx-accessible-grid

Handoff log. Read this first; update it as you go.

## What this is

A reusable, accessible data grid for wxPython, spun out the same way as its
siblings `wx-accessible-webview` and `wx-accessible-menubar`. Community Access
open-source, MIT, created by Taylor Arndt. First consumer is VRP (the accessible
radio programmer), whose channel grid is the motivating use case.

The hard problem it solves: the stock `wx.grid.Grid` is inaccessible in NVDA/JAWS.

## Architecture (native, as of 2026-06-27)

The library is a **native** grid: a virtual `wx.ListCtrl` (`LC_REPORT |
LC_VIRTUAL`). The platform accessibility layer (UIA / NSAccessibility / AT-SPI)
exposes the rows directly to NVDA, JAWS, and VoiceOver. No WebView, no HTML, no
injected JS.

- `model.py` — `GridModel` (subclass it) and `Column`. Required: `columns()`,
  `row_count()`, `cell_text(row, column)`. Optional: `row_label(row)` (defaults
  to the row-header cell text, else 1-based number), `column_names()`. Pure
  Python, no wx, unit-tested headless. `Column(name, label, is_row_header=False,
  width_hint="auto"|"narrow"|"wide")`.
- `grid.py` — `AccessibleGrid`. Wraps an internal `_GridListCtrl(wx.ListCtrl)`
  whose `OnGetItemText(item, column)` pulls text from the model. Public API:
  `.control` (the wx.ListCtrl, goes in a sizer), `.model`, `.refresh()`,
  `.refresh_rows(rows)`, `.selected_rows()`, `.focused_row()`, `.select_rows()`,
  `.focus_row(row)`, plus the cell cursor: `.current_column()`, `.current_cell()`.
  `focus_row` takes keyboard focus to the grid so a native list item is actually
  spoken.
- Navigation (0.6.0): Up/Down move by row (native list reads the row). Left/Right
  move a cell cursor across columns; the grid handles those keys, tracks
  `_current_col` (clamped via `model.clamp_column`, no wrap), and voices the cell
  as "value, column label" through the `announce(str)` callback passed to
  `AccessibleGrid(..., announce=...)`. A native list cannot announce per-cell, so
  without an `announce` callback Left/Right move silently. VRP wires `announce` to
  its prism-backed `Announcer` (`vrp/native/announce.py`).
- `examples/demo.py` — STALE. Still the old WebView API (imports removed names
  like CHECKBOX/COMBO/ContextMenuItem and passes `row_select=`/`on_context=`). It
  will crash until rewritten to the native API. My rewrite was declined; left for
  Taylor to direct.
- `tests/` — `test_model.py` (headless model tests) + `test_grid.py` (wx smoke
  tests, skip without a display). 9 pass via `uv run --extra dev pytest`.

Editing is **host-driven**: the native list does not edit in place. The host
reads `selected_rows()`/`focused_row()`, opens a real native control (an edit
dialog), writes back into its own model, and calls `refresh_rows([...])`. The
library deliberately does not emulate in-cell editors.

## Reference implementation

The native approach was proven first inside VRP at `~/developer/vrp/vrp/native/`
(`channel_grid.py` = the virtual ListCtrl widget, `grid_model.py` = the pure
data/selection model). The library generalizes those. VRP's copy is
radio-specific (depends on `chirp_backend`); the library's is generic.

## History

Versions 0.1.0–0.4.1 were a WebView-hosted ARIA grid (`role="grid"` rendered into
an `AccessibleWebView`, vanilla-JS runtime, aria-activedescendant, paging). 0.5.0
is the native rewrite. The WebView files (`render.py`, `assets.py`, the
`wx-accessible-webview` dependency) were removed. Open issue #1 (Doug / VRP) asked
whether a native backend was on the roadmap; it is now the whole design.

## Status (2026-06-27)

- 0.5.0 native rewrite done and PUBLISHED to PyPI. 0.6.0 adds the Left/Right cell
  cursor (in working tree, not yet committed or published). Package imports,
  builds (no webview dep), 11 tests pass (model + nav + wx smoke).
- NOT yet manually driven with VoiceOver/NVDA in a real window — that is the real
  bar and is still owed (`examples/demo.py` needs its native rewrite first).
- README rewritten to the native design. No git commits yet (Taylor commits
  himself). No PyPI release.

## Testing

- `uv run --extra dev pytest -q` — model + wx smoke.
- Real test is manual: a native window with a screen reader, arrowing rows,
  multi-select, and a host edit dialog. Owed once the demo is rebuilt.

## Conventions

Mirror the sibling libs: hatchling build, `src/` layout, MIT, ruff line length
100, dependency-light (now just wxPython). No emojis, no markdown tables in docs
(screen-reader rule).
