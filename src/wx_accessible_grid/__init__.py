"""wx-accessible-grid — an accessible, editable data grid for wxPython.

Native ``wx.grid.Grid`` reads poorly (or not at all) in NVDA and JAWS, and
hand-built ``<div>`` grids are worse. This library takes the approach proven by
its sibling :mod:`wx_accessible_webview`: render a real, semantic **ARIA grid**
into a WebView and let the screen reader follow it like any web data table, then
layer application-style keyboard behaviour on top.

What you get, fully keyboard-operable and read correctly in NVDA/JAWS:

* Arrow keys move a single focused cell (a roving ``tabindex``). The reader
  speaks the column header moving across a row and the row header moving down a
  column — and only the focused cell, so a huge dataset stays fast.
* ``F2`` or ``Enter`` edits a cell in place with the right control: edit box,
  combo box, checkbox, slider, or stepper. ``Enter`` commits, ``Escape`` cancels.
* ``Space`` (or ``Ctrl+Space``) selects a row; ``Delete`` deletes the selection;
  the context-menu key fires a callback so the host can show a native menu.
* Editing round-trips through your :class:`GridModel`, so the value the screen
  reader confirms is the validated, normalized one — never the raw keystrokes.

Quick start::

    from wx_accessible_grid import AccessibleGrid, GridModel, Column

    class MyModel(GridModel):
        def columns(self): ...
        def row_count(self): ...
        def display(self, row, column): ...
        def set_cell(self, row, column, value): ...

    grid = AccessibleGrid(panel, MyModel(), label="Memory channels")
    sizer.Add(grid.control, 1, wx.EXPAND)

A Community Access open-source project, created by Taylor Arndt. First built for
VRP, the accessible radio programmer.
"""

from __future__ import annotations

from wx_accessible_grid.grid import AccessibleGrid, ContextMenuItem
from wx_accessible_grid.model import (
    CHECKBOX,
    COMBO,
    NONE,
    SLIDER,
    STEPPER,
    TEXT,
    Column,
    GridModel,
    SetResult,
)

__version__ = "0.2.0"
__all__ = [
    "AccessibleGrid",
    "ContextMenuItem",
    "GridModel",
    "Column",
    "SetResult",
    "TEXT",
    "COMBO",
    "CHECKBOX",
    "SLIDER",
    "STEPPER",
    "NONE",
    "__version__",
]
