# wx-accessible-grid

An accessible data grid for wxPython that a blind person can actually use. It is a
**real native wx control**: a `wx.dataview.DataViewListCtrl`. On macOS that wraps
`NSTableView`, so VoiceOver reads the table, its rows, and each cell value out of
the box. On Windows and Linux it is the native list view, read by NVDA, JAWS, and
Orca. No WebView, no HTML, and nothing to announce by hand: the screen reader does
row and cell navigation itself.

The control matters. The stock `wx.grid.Grid` reads poorly in NVDA and JAWS. A
plain `wx.ListCtrl` in report mode is worse: on macOS it falls back to wx's
generic, custom-drawn implementation, which exposes nothing to NSAccessibility, so
it is **silent under VoiceOver**. An earlier version of this library used a WebView
to get around that. `DataViewListCtrl` wraps a real native table on each platform
instead, so it carries the platform's own accessibility for free, no workaround
needed.

It is built for data entry, not a spreadsheet engine. There are no formulas. What
there is, is a native grid that is fully keyboard-operable and announced correctly,
with editing that round-trips through your model.

## What you get

- A native table. Arrow up and down to move by row, and the screen reader reads
  the row. On macOS, VoiceOver also reads across the cells of a row by column
  ("Frequency, 146.520"), because `NSTableView` exposes every cell, not just the
  row.
- Native multi-select. Selecting rows for a bulk operation (move, reorder, delete
  a region) is a real native selection the user already knows how to drive. The
  host reads the selected rows, acts through the model, and refreshes.
- Selection and focus helpers that keep the screen reader honest. Moving to a row
  sets it as the current item before taking focus, so it is read once and not
  announced stale-then-correct.
- Editing round-trips through your model, so the value the screen reader confirms
  is the validated, normalized one, never the raw keystrokes.
- A pure-Python model with no wx in it. Columns, row count, and cell text are all
  plain Python, so they are unit-testable headless, without a display.

## Install

```bash
pip install wx-accessible-grid
```

That pulls in wxPython.

## Use it

Describe your columns and provide the row data through a model, then drop the grid
into a sizer. The grid asks your model for each cell's text as it builds.

```python
import wx
from wx_accessible_grid import AccessibleGrid, GridModel, Column

class ChannelModel(GridModel):
    def __init__(self, rows):
        self._rows = rows
        self._cols = [
            Column("num", "#", is_row_header=True),
            Column("name", "Name"),
            Column("mode", "Mode"),
            Column("active", "Active"),
            Column("volume", "Volume"),
        ]

    def columns(self):
        return self._cols

    def row_count(self):
        return len(self._rows)

    def cell_text(self, row, column):
        # the text the table shows and the screen reader reads for this cell
        if column == "num":
            return str(row + 1)
        val = self._rows[row][column]
        if column == "active":
            return "Yes" if val else "No"
        return str(val)

grid = AccessibleGrid(panel, ChannelModel(rows), label="Memory channels")
sizer.Add(grid.control, 1, wx.EXPAND)
```

The grid exposes the native selection so the host can act on it:

```python
nums = grid.selected_rows()      # selected rows, or the focused row if none
grid.select_rows([3, 4, 5])      # replace the selection
grid.focus_row(3)                # make that the current row and ensure it is read
grid.refresh_rows([3])           # update just those rows' cells after an edit
grid.refresh()                   # update every cell (or rebuild if rows changed)
grid.set_columns()               # rebuild columns when the dataset's shape changes
```

The `dev` extra (`pip install "wx-accessible-grid[dev]"`) adds pytest for the
model tests, which run without wx.

## Keyboard

- Arrow up and down: move the current row. The screen reader reads the row.
- On macOS, VoiceOver reads across the cells of the focused row by column using
  its own table navigation; the app does not have to do anything for that.
- Standard native `DataViewListCtrl` selection (Shift and Ctrl with arrows or
  click) extends or toggles the multi-selection.
- Editing and row actions are wired by the host through the selection and focus
  helpers (for example a native edit dialog, or a context menu on `Shift+F10`),
  so they use real native controls that read correctly.

## How it works

`AccessibleGrid` wraps a `wx.dataview.DataViewListCtrl`. On macOS that is a
`NSTableView`; on Windows and Linux it is the platform's native list view. Because
it is a real native table, the platform accessibility layer (NSAccessibility, UIA,
AT-SPI) exposes the table, its rows, and each cell to the screen reader directly.
No HTML, no WebView bridge, no injected JavaScript, and no hand-rolled
announcements.

`DataViewListCtrl` is not a virtual control: it stores the rows, so the grid reads
your model's `cell_text(row, column)` once per cell when it builds, and again only
for the rows you refresh. For very large data sets you would move to a
`DataViewCtrl` with a custom model; that is out of scope here. The model carries
all the data in plain Python with no wx, so it can be tested headless. Editing is
host-driven: read the selection, edit through your model with a native control,
then call `refresh_rows`.

## Status

Version 0.7.0. The library is built on `DataViewListCtrl` after the earlier
`wx.ListCtrl` version was found to be silent under VoiceOver on macOS (a structural
limitation of wx's generic list on macOS, not a bug that could be patched). The
native channel grid in Versatile Radio Programmer proved this control out on real
hardware. Tested here with headless unit tests for the model and wx smoke tests for
the widget. A full manual pass with VoiceOver on macOS and NVDA/JAWS on Windows is
the next milestone; reports welcome.

## License

MIT. A Community Access open-source project, created by Taylor Arndt.
