# wx-accessible-grid

An accessible, editable data grid for wxPython that a blind person can actually
use. It is a **real native wx control**: a virtual `wx.ListCtrl` in report mode.
NVDA, JAWS, and VoiceOver read it directly, the way they read any native list,
with no WebView and no HTML in the path.

Earlier versions rendered a semantic ARIA grid into a WebView. That worked, but
it put a browser document between your data and the screen reader, depended on a
WebView2/WKWebView runtime, and paged the DOM to stay fast. The native virtual
`wx.ListCtrl`, proven in Versatile Radio Programmer's channel grid, reads each
row correctly as you arrow through it, populates instantly at any size, and needs
no browser runtime. That is the library's approach now.

It is built for data entry, not a spreadsheet engine. There are no formulas. What
there is, is a native grid that is fully keyboard-operable and announced
correctly, with editing that round-trips through your model.

## What you get

- A native virtual list (`LC_REPORT | LC_VIRTUAL`). Virtual means rows are pulled
  on demand through a single `OnGetItemText` callback, so a grid with thousands
  of rows populates instantly and there is no paging. The screen reader still
  gets a correct sense of "row N of many" from the native list itself.
- Real native rows. Arrow up and down and the screen reader reads the focused row
  with its column headers, because it is a genuine native list item, not a styled
  `<div>` or an ARIA emulation. Nothing is injected; the platform reads the
  control.
- Multi-select by default. Selecting rows for a bulk operation (move, reorder,
  delete a region) is a native selection the user already knows how to drive. The
  host reads the selected rows, acts through the model, and refreshes.
- Selection and focus helpers that keep the screen reader honest. A native list
  item is only spoken when its control has system focus, so moving to a row takes
  focus to the grid, makes the row visible, and ensures it is read. Restoring a
  moved block re-selects the whole block and focuses the first row.
- Editing round-trips through your model, so the value the screen reader confirms
  is the validated, normalized one, never the raw keystrokes. If an edit is
  rejected the user hears why.
- A pure-Python model with no wx in it. Columns, row data, selection math, and
  cell formatting are all plain Python, so they are unit-testable headless,
  without a display.

## Install

```bash
pip install wx-accessible-grid
```

That pulls in wxPython.

## Use it

Describe your columns and provide the row data through a model, then drop the
grid into a sizer. The grid is a virtual `wx.ListCtrl`, so it asks your model for
each cell's text as it paints, rather than holding every row in the control.

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
        # the text the list paints and the screen reader reads for this cell
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
grid.focus_row(3)                # move focus there and make sure it is read
grid.refresh_rows([3])           # repaint just those rows after an edit
```

The `dev` extra (`pip install "wx-accessible-grid[dev]"`) adds pytest for the
model tests, which run without wx.

## Keyboard

- Arrow up and down: move the focused row. The screen reader reads the row and
  its column headers as a native list item.
- `Home` / `End`: first / last row. `Page Up` / `Page Down`: a screenful at a
  time. All standard native `wx.ListCtrl` navigation works, because it is a
  native list.
- Space and `Ctrl+Space`: extend or toggle the native selection.
- Editing and row actions are wired by the host through the selection and focus
  helpers (for example, a native edit dialog or a context menu on `Shift+F10`),
  so they use real native controls that read correctly.

## How it works

`AccessibleGrid` wraps a `wx.ListCtrl` created with `LC_REPORT | LC_VIRTUAL`.
Report mode gives it real column headers; virtual mode means it never stores the
rows itself: it calls your model's `cell_text(row, column)` for each visible cell
as it paints. Because it is a native control, the platform accessibility layer
(UIA on Windows, NSAccessibility on macOS, AT-SPI on Linux) exposes the rows
directly to the screen reader. No HTML, no WebView bridge, no injected JavaScript.

The model carries all the data and the index/number and selection arithmetic, in
plain Python with no wx, so it can be tested headless. The grid widget is a thin
shell over the native list plus the selection and focus helpers that make sure a
moved or edited row is both selected and actually spoken.

## Status

This is the native rewrite. The library moved off the WebView-hosted ARIA grid to
a native virtual `wx.ListCtrl` after the native approach proved out in Versatile
Radio Programmer's channel grid (instant population at full radio size, correct
per-row reading, native multi-select). Tested on macOS with VoiceOver and in
headless unit tests for the model. NVDA and JAWS verification on Windows is the
next milestone; reports welcome.

## License

MIT. A Community Access open-source project, created by Taylor Arndt.
