"""wx-accessible-grid — an accessible data grid for wxPython.

A blind person can actually use this grid because it is a **real native wx
control**: a virtual ``wx.ListCtrl`` in report mode. NVDA, JAWS, and VoiceOver
read it directly, the way they read any native list, with no WebView and no HTML
in the path.

The stock ``wx.grid.Grid`` reads poorly (or not at all) in NVDA and JAWS, and an
earlier version of this library rendered an ARIA grid into a WebView to get
around that. The native virtual ``wx.ListCtrl`` reads each row correctly as you
arrow through it, populates instantly at any size, and needs no browser runtime,
so that is the library's approach now.

What you get, read correctly in NVDA/JAWS/VoiceOver:

* A native virtual list. Rows are pulled on demand through one ``OnGetItemText``
  callback, so thousands of rows populate instantly and there is no paging.
* Real native rows. Arrow up and down and the screen reader reads the focused
  row with its column headers, because it is a genuine native list item.
* Native multi-select, plus selection and focus helpers that make sure a moved
  or edited row is both selected and actually spoken.

Quick start::

    from wx_accessible_grid import AccessibleGrid, GridModel, Column

    class MyModel(GridModel):
        def columns(self): ...
        def row_count(self): ...
        def cell_text(self, row, column): ...

    grid = AccessibleGrid(panel, MyModel(), label="Memory channels")
    sizer.Add(grid.control, 1, wx.EXPAND)

Editing is host-driven: read ``grid.selected_rows()``, edit through your own
model with a native control, then call ``grid.refresh_rows(...)``.

A Community Access open-source project, created by Taylor Arndt. First built for
VRP, the accessible radio programmer.
"""

from __future__ import annotations

from wx_accessible_grid.grid import AccessibleGrid
from wx_accessible_grid.model import AUTO, NARROW, WIDE, Column, GridModel

__version__ = "0.6.1"
__all__ = [
    "AccessibleGrid",
    "GridModel",
    "Column",
    "NARROW",
    "WIDE",
    "AUTO",
    "__version__",
]
