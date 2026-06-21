# wx-accessible-grid

An accessible, editable data grid for wxPython that a blind person can actually
use. Native `wx.grid.Grid` reads poorly or not at all in NVDA and JAWS, and a
hand-built grid of `<div>`s is worse. This library takes the approach proven by
its sibling [wx-accessible-webview](https://github.com/Community-Access/wx-accessible-webview):
render a real, semantic ARIA grid into a WebView and let the screen reader follow
it like any web data table, then layer spreadsheet-style keyboard behavior on top.

It is built for data entry, not a spreadsheet engine. There are no formulas. What
there is, is every control you actually edit data with, fully keyboard-operable
and announced correctly.

## What you get

- Arrow keys move a single focused cell, not the document. Moving across a row
  speaks the column header. Moving down a column speaks the row header. Only the
  focused cell is read, so a grid with thousands of rows stays fast instead of
  making the screen reader re-read the whole table on every keystroke.
- `F2` or `Enter` edits a cell in place with the right control for the data: edit
  box, combo box, checkbox, slider, or stepper. `Enter` commits, `Escape` cancels.
- `Space`, or `Ctrl+Space`, selects a row. `Delete` deletes the selection. The
  context menu key, or `Shift+F10`, fires a callback so you can show a native menu.
- Editing round-trips through your model, so the value the screen reader confirms
  is the validated, normalized one, never the raw keystrokes. If an edit is
  rejected the user hears why and the editor reopens so they can fix it.
- Only one page of rows is ever in the DOM, but `aria-rowcount` keeps the user's
  sense of "row N of many" correct. Arrow past the bottom and the next page loads
  and navigation just keeps going.

## Install

```bash
pip install wx-accessible-grid
```

That pulls in wxPython and wx-accessible-webview.

## Use it

Subclass `GridModel` to describe your columns and provide the data, then drop an
`AccessibleGrid` into a sizer.

```python
import wx
from wx_accessible_grid import AccessibleGrid, GridModel, Column, SetResult
from wx_accessible_grid import TEXT, COMBO, CHECKBOX, SLIDER, STEPPER, NONE

class ChannelModel(GridModel):
    def __init__(self, rows):
        self._rows = rows
        self._cols = [
            Column("num", "#", editor=NONE, is_row_header=True),
            Column("name", "Name", editor=TEXT),
            Column("mode", "Mode", editor=COMBO, choices=["FM", "AM", "USB"]),
            Column("active", "Active", editor=CHECKBOX),
            Column("volume", "Volume", editor=SLIDER, min=0, max=100, step=1),
            Column("priority", "Priority", editor=STEPPER, min=0, max=10),
        ]

    def columns(self):
        return self._cols

    def row_count(self):
        return len(self._rows)

    def display(self, row, column):
        if column == "num":
            return str(row + 1)
        val = self._rows[row][column]
        return "Yes" if (column == "active" and val) else "No" if column == "active" else str(val)

    def edit_value(self, row, column):
        # the form the editor wants, when it differs from the shown text
        if column == "active":
            return "true" if self._rows[row]["active"] else "false"
        return self.display(row, column)

    def set_cell(self, row, column, value):
        # validate and normalize here; what you return is what gets announced
        self._rows[row][column] = value
        return SetResult(True, display=value, message=f"{column} updated")

grid = AccessibleGrid(panel, ChannelModel(rows), label="Memory channels",
                      page_size=100)
sizer.Add(grid.control, 1, wx.EXPAND)
```

The `dev` extra (`pip install "wx-accessible-grid[dev]"`) adds pytest for the
model and renderer tests, which run without wx.

## The editors

- `TEXT`: a single-line edit box. Type, then Enter to commit.
- `COMBO`: a drop-down of fixed choices, which also stands in for a radio group.
  Arrow through the list, Enter to commit.
- `CHECKBOX`: a boolean toggle. Space toggles it, Enter commits.
- `SLIDER`: a range control adjusted with the arrow keys.
- `STEPPER`: a number spinner. Type a value or step it with the arrows.
- `NONE`: read-only, for ids and computed columns. Not editable.

`edit_value` gives the editor its starting value when that differs from the
displayed text (a checkbox wants `true`/`false`, a slider wants a bare number,
even if the cell shows `Yes` or `146.520 MHz`).

## Keyboard

- Arrows: move the focused cell. `Home` / `End`: first / last cell in the row.
  `Ctrl+Home` / `Ctrl+End`: first / last cell in the grid. `Page Up` / `Page Down`:
  previous / next page.
- `F2` or `Enter`: edit the focused cell. `Enter`: commit. `Escape`: cancel.
- `Space` or `Ctrl+Space`: select or unselect the row.
- `Delete`: delete the selected rows, or the focused row if none are selected.
- Context menu key or `Shift+F10`: ask the host for a row menu.

## How it works

The grid is a `<table role="grid">` with `<th scope="col">` column headers,
a `<th scope="row">` row header, and `<td role="gridcell">` cells, rendered into
an `AccessibleWebView`. A roving `tabindex` gives exactly one cell focus at a
time, which puts the screen reader in focus mode so it reads that cell and the
headers that changed, not the whole table. A small vanilla-JS runtime, installed
once, handles navigation, editing, and selection, and talks to Python over the
WebView bridge. Your `GridModel` does the validation and persistence on the
Python side.

## Status

Version 0.1.0, first release, built for VRP (the accessible radio programmer) and
extracted as a reusable library. Tested on macOS WebView with VoiceOver and in
unit tests for the model and renderer. NVDA and JAWS verification on Windows
WebView2 is the next milestone; reports welcome.

## License

MIT. A Community Access open-source project, created by Taylor Arndt.
