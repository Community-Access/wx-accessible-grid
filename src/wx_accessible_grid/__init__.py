"""wx-accessible-grid — an accessible data grid for wxPython.

A blind person can actually use this grid because it is a **real native wx
control**: a ``wx.dataview.DataViewListCtrl``. On macOS it wraps ``NSTableView``,
so VoiceOver reads the table, its rows, and each cell value out of the box (e.g.
"Frequency, 146.520"); on Windows and Linux it is the native list view for NVDA,
JAWS, and Orca. No WebView, no HTML, and nothing to announce by hand: the screen
reader does row and cell navigation itself.

The stock ``wx.grid.Grid`` reads poorly in NVDA/JAWS, and a plain ``wx.ListCtrl``
in report mode is silent under VoiceOver on macOS (it falls back to wx's generic
custom-drawn control, which exposes nothing to NSAccessibility). DataViewListCtrl
wraps a real native table on each platform instead, which carries the platform's
accessibility for free.

What you get:

* Up and down move by row; the screen reader reads the row. On macOS, VoiceOver
  also reads across the cells of a row natively, by column.
* Native multi-select, plus selection and focus helpers that make sure a moved or
  edited row is both selected and actually spoken.
* A pure-Python model with no wx in it, so columns, row counts, and cell text are
  unit-testable headless.

Quick start::

    from wx_accessible_grid import AccessibleGrid, GridModel, Column

    class MyModel(GridModel):
        def columns(self): ...
        def row_count(self): ...
        def cell_text(self, row, column): ...

    grid = AccessibleGrid(panel, MyModel(), label="Memory channels")
    sizer.Add(grid.control, 1, wx.EXPAND)

Editing is host-driven: read ``grid.selected_rows()``, edit through your own model
with a native control, then call ``grid.refresh_rows(...)``.

A Community Access open-source project, created by Taylor Arndt. First built for
VRP, the accessible radio programmer.
"""

from __future__ import annotations

from wx_accessible_grid.grid import AccessibleGrid
from wx_accessible_grid.model import AUTO, NARROW, WIDE, Column, GridModel

__version__ = "0.7.0"
__all__ = [
    "AccessibleGrid",
    "GridModel",
    "Column",
    "NARROW",
    "WIDE",
    "AUTO",
    "__version__",
]
