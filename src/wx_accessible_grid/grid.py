"""``AccessibleGrid`` — a native, screen-reader-first data grid widget.

It wraps a virtual ``wx.ListCtrl`` (``LC_REPORT | LC_VIRTUAL``) over your
:class:`~wx_accessible_grid.model.GridModel`. Report mode gives real column
headers; virtual mode means the control never stores the rows, it asks the model
for each visible cell as it paints. Because it is a native control, the platform
accessibility layer (UIA on Windows, NSAccessibility on macOS, AT-SPI on Linux)
exposes the rows directly to NVDA, JAWS, and VoiceOver. No WebView, no HTML, no
injected JavaScript.

Navigation model:

* Up/Down move by row. The native list reads the focused row for free.
* Left/Right move a cell cursor across the columns of the focused row. A native
  list does not announce per cell, so the grid voices the moved-to cell itself,
  as ``"<value>, <column label>"``, through an ``announce`` callback you pass in
  (wire it to your app's speech: prism, the status bar, whatever you use). With
  no ``announce`` callback the cursor still moves but says nothing.

Add :attr:`control` to a sizer like any wx window. Editing and row actions are
host-driven: read the selection with :meth:`selected_rows` and the cell cursor
with :meth:`current_cell`, act through your own model, then call
:meth:`refresh_rows` (or :meth:`refresh`) to repaint.
"""

from __future__ import annotations

from typing import Callable

import wx

from wx_accessible_grid.model import GridModel, clamp_column

# Width hints -> pixel widths.
_WIDTH = {"narrow": 90, "wide": 200, "auto": 130}


class _GridListCtrl(wx.ListCtrl):
    """The virtual ``wx.ListCtrl`` that pulls cell text from the model.

    ``OnGetItemText`` is wxWidgets' virtual-list callback; it must be a method on
    the control subclass, which is why this is its own class rather than a plain
    ``wx.ListCtrl`` the wrapper configures.
    """

    def __init__(self, parent: wx.Window, model: GridModel, columns: list) -> None:
        super().__init__(parent, style=wx.LC_REPORT | wx.LC_VIRTUAL | wx.LC_HRULES)
        self._model = model
        self._columns = columns

    def OnGetItemText(self, item: int, column: int) -> str:  # noqa: N802 (wx API)
        return self._model.cell_text(item, self._columns[column].name)


class AccessibleGrid:
    """An accessible, native data grid backed by a :class:`GridModel`.

    Parameters
    ----------
    parent:
        Parent wx window.
    model:
        Your :class:`GridModel` subclass.
    label:
        Accessible name for the grid (set as the control's name).
    announce:
        Optional ``callable(str)`` the grid calls to voice a cell as you move
        Left/Right across columns. Wire it to your app's speech path. If omitted,
        Left/Right still move the cell cursor but nothing is spoken.
    """

    def __init__(
        self,
        parent: wx.Window,
        model: GridModel,
        label: str = "Grid",
        announce: Callable[[str], None] | None = None,
    ) -> None:
        self._model = model
        self._columns = list(model.columns())
        self._announce = announce
        self._current_col = 0
        self._list = _GridListCtrl(parent, model, self._columns)
        self._list.SetName(label)
        for i, col in enumerate(self._columns):
            self._list.InsertColumn(i, col.label, width=_WIDTH.get(col.width_hint, 130))
        self._list.SetItemCount(model.row_count())
        self._list.Bind(wx.EVT_KEY_DOWN, self._on_key_down)

    # -- access --------------------------------------------------------
    @property
    def control(self) -> wx.ListCtrl:
        """The underlying ``wx.ListCtrl``; add this to a sizer."""
        return self._list

    @property
    def model(self) -> GridModel:
        return self._model

    # -- cell cursor (Left/Right) --------------------------------------
    def current_column(self) -> int:
        """The 0-based index of the column the cell cursor is on."""
        return self._current_col

    def current_cell(self) -> tuple[int, int] | None:
        """``(row, column_index)`` for the cell cursor, or ``None`` if no row is
        focused. Handy for wiring a host edit action to the focused cell."""
        row = self.focused_row()
        return None if row is None else (row, self._current_col)

    def _on_key_down(self, event: wx.KeyEvent) -> None:
        key = event.GetKeyCode()
        if key in (wx.WXK_LEFT, wx.WXK_RIGHT) and not event.HasAnyModifiers():
            delta = -1 if key == wx.WXK_LEFT else 1
            moved = clamp_column(self._current_col, delta, len(self._columns))
            self._current_col = moved
            self._speak_current_cell()
            return  # consume: a report list does nothing with Left/Right anyway
        event.Skip()

    def _speak_current_cell(self) -> None:
        if self._announce is None:
            return
        row = self.focused_row()
        if row is None or not self._columns:
            return
        col = self._columns[self._current_col]
        value = self._model.cell_text(row, col.name)
        text = value if value else "blank"
        self._announce(f"{text}, {col.label}")

    # -- structure -----------------------------------------------------
    def set_columns(self) -> None:
        """Rebuild the columns from the model and reset the row count.

        Use when the dataset's column *shape* changes (e.g. a different radio
        with a different feature set). ``refresh()`` is for row changes only; this
        clears and re-inserts the columns, so it also resets the cell cursor to
        the first column.
        """
        self._columns = list(self._model.columns())
        self._list._columns = self._columns
        self._current_col = 0
        self._list.ClearAll()  # drops both columns and items
        for i, col in enumerate(self._columns):
            self._list.InsertColumn(i, col.label, width=_WIDTH.get(col.width_hint, 130))
        self._list.SetItemCount(self._model.row_count())
        self._list.Refresh()

    # -- refresh -------------------------------------------------------
    def refresh(self) -> None:
        """Re-read the row count from the model and repaint the whole list.

        Use after rows are added, removed, or reordered. Keeps the columns (and
        the screen reader's focus) rather than rebuilding them.
        """
        self._list.SetItemCount(self._model.row_count())
        self._list.Refresh()

    def refresh_rows(self, rows: list[int]) -> None:
        """Repaint just ``rows`` (their item indexes) after an in-place edit."""
        count = self._list.GetItemCount()
        for r in rows:
            if 0 <= r < count:
                self._list.RefreshItem(r)

    # -- selection / focus ---------------------------------------------
    def selected_rows(self) -> list[int]:
        """Selected row indexes; falls back to the focused row when none are
        selected, so a single-row action still has a target."""
        rows, item = [], self._list.GetFirstSelected()
        while item != -1:
            rows.append(item)
            item = self._list.GetNextSelected(item)
        if not rows:
            focused = self._list.GetFocusedItem()
            if focused != -1:
                rows = [focused]
        return sorted(rows)

    def focused_row(self) -> int | None:
        item = self._list.GetFocusedItem()
        return None if item == -1 else item

    def select_rows(self, rows: list[int]) -> None:
        """Replace the selection with exactly ``rows``."""
        item = self._list.GetFirstSelected()
        while item != -1:
            nxt = self._list.GetNextSelected(item)
            self._list.Select(item, on=False)
            item = nxt
        count = self._list.GetItemCount()
        for r in rows:
            if 0 <= r < count:
                self._list.Select(r, on=True)

    def focus_row(self, row: int) -> None:
        """Move focus to ``row``, make it visible, and ensure it is read.

        A native list item is only spoken by NVDA/VoiceOver when its control has
        system focus, so this takes keyboard focus to the grid if it does not
        already have it. Pair with :meth:`select_rows` when a row should be both
        selected and read (a Go-to-channel, a Find, a post-edit return).
        """
        if not (0 <= row < self._list.GetItemCount()):
            return
        if wx.Window.FindFocus() is not self._list:
            self._list.SetFocus()
        self._list.Focus(row)
        self._list.EnsureVisible(row)
