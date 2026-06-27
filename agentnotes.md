# Agent notes — wx-accessible-grid

Handoff log. Read this first; update it as you go.

## What this is

A reusable, accessible data grid for wxPython, spun out the same way as its
siblings `wx-accessible-webview` and `wx-accessible-menubar`. Community Access
open-source, MIT, created by Taylor Arndt. First consumer is VRP (the accessible
radio programmer), whose channel grid is the motivating use case.

The hard problem: `wx.grid.Grid` reads poorly in NVDA/JAWS, and a `wx.ListCtrl`
report grid is silent under VoiceOver on macOS.

## Architecture (DataViewListCtrl, as of 2026-06-27)

The library wraps a `wx.dataview.DataViewListCtrl`. It is a real native control on
each platform — `NSTableView` on macOS (VoiceOver reads rows AND cells for free),
the native list view on Windows/Linux (NVDA/JAWS/Orca). No WebView, no manual
announcements; the screen reader does cell navigation itself.

- `model.py` — `GridModel` (subclass it) and `Column`. Required: `columns()`,
  `row_count()`, `cell_text(row, column)`. Optional: `row_label(row)`,
  `column_names()`. Pure Python, no wx, unit-tested headless.
  `Column(name, label, is_row_header=False, width_hint="auto"|"narrow"|"wide")`.
- `grid.py` — `AccessibleGrid(parent, model, label, announce=None)` wraps the
  DataViewListCtrl. API: `.control`, `.model`, `.set_columns()` (rebuild columns +
  rows when the dataset shape changes), `.refresh()` (update all cells in place;
  rebuild if row count changed), `.refresh_rows(rows)`, `.selected_rows()`,
  `.focused_row()`, `.select_rows()`, `.focus_row(row)`. `focus_row` does
  `SetCurrentItem` BEFORE `SetFocus` to avoid a stale-then-correct double
  announcement. DataViewListCtrl is NOT virtual — it stores rows (`AppendItem`);
  fine for hundreds/low-thousands.
- Opt-in Left/Right cell cursor (0.8.0, issue #2): pass `announce=callable(str)`
  and the grid binds `EVT_KEY_DOWN`, tracks `_current_col` (via
  `model.clamp_column`), consumes unmodified Left/Right, and voices "value, column
  label" through `announce`. Plus `current_column()`/`current_cell()`. With
  `announce=None` (default) NOTHING is bound — identical to 0.7.0. This is for
  Windows/NVDA, where DataViewCtrl is wx's generic control and does not speak a
  per-cell cursor; on macOS leave it off so VoiceOver (VO+Left/Right) is the only
  voice.
- `tests/` — `test_model.py` (headless) + `test_grid.py` (wx smoke; skips without
  a display). 12 pass via `uv run --extra dev pytest`.

Editing is host-driven: the host reads `selected_rows()`/`focused_row()`, opens a
native control (edit dialog), writes back into its model, and calls
`refresh_rows([...])`.

## Reference implementation

Generalized from VRP's upstream native grid `vrp/native/channel_grid.py`
(`dv.DataViewListCtrl`) in douglangley/vrp, plus its pure `grid_model.py`. The
VoiceOver rationale is documented in that repo at
`docs/research/2026-06-24-native-grid-voiceover-feasibility.md`.

## History (important — do not regress)

- 0.1.0–0.4.1: WebView-hosted ARIA grid (removed).
- 0.5.0–0.6.1: native **wx.ListCtrl** report grid + a manual Left/Right cell
  cursor with an `announce` hook. WRONG for macOS: `wx.ListCtrl` report mode is
  structurally silent under VoiceOver (falls back to wx's generic custom-drawn
  list, exposes nothing to NSAccessibility). The manual Left/Right was a
  workaround for the lack of native per-cell reading.
- 0.7.0: rebased onto **DataViewListCtrl** (NSTableView). I over-corrected and
  REMOVED the Left/Right cursor + announce hook entirely, reasoning VoiceOver reads
  cells natively. That regressed Windows/NVDA, where DataViewCtrl is generic and
  does NOT speak a per-cell cursor — and NVDA is VRP's primary user. (Doug, issue
  #2.)
- 0.8.0: restored the cursor as OPT-IN on the DataViewListCtrl backend. They
  compose: announce-driven cursor on plain Left/Right (Windows) vs VoiceOver's
  VO+Left/Right (macOS), different key channels. Default `announce=None` keeps
  0.7.0's VoiceOver-correct behavior. This is the current, correct design.

## VRP integration status

VRP does NOT yet import the library. Upstream (douglangley/vrp) already migrated
its own grid to DataViewListCtrl in-tree. An attempt this session to make VRP use
the library was reverted because (a) it was based on the wx.ListCtrl library and
(b) Taylor's local VRP is ~19 commits behind upstream. If VRP is to consume the
library, do it on top of upstream's DataViewListCtrl base, mapping VRP's
channel-number API onto the library's row-index API (see the reverted adapter
sketch in git reflog if needed).

## Testing

- `uv run --extra dev pytest -q` — model + wx smoke.
- Real bar (owed): VoiceOver on macOS and NVDA/JAWS on Windows, in a real window.

## Conventions

hatchling build, `src/` layout, MIT, ruff line length 100, dependency-light
(wxPython only). No emojis, no markdown tables in docs (screen-reader rule).
Publishing to PyPI is the agent's job (token recoverable from Claude history).
