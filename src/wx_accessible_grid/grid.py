"""``AccessibleGrid`` — a native, screen-reader-first data grid widget.

It wraps a ``wx.dataview.DataViewListCtrl``, which is a real native control on
every platform: ``NSTableView`` on macOS (so VoiceOver reads the table, its rows,
and each cell value out of the box, e.g. "Frequency, 146.520"), and the native
list view on Windows/GTK for NVDA and Orca. The screen reader does cell
navigation itself, so there is nothing to announce manually and no WebView.

(The earlier ``wx.ListCtrl`` report-mode version of this library was silent under
VoiceOver on macOS: `wx.ListCtrl` falls back to wx's generic custom-drawn
implementation there, which exposes nothing to NSAccessibility. DataViewListCtrl
wraps NSTableView instead, which carries Apple's accessibility for free.)

Add :attr:`control` to a sizer like any wx window. Editing and row actions are
host-driven: read the selection with :meth:`selected_rows`, act through your own
model, then call :meth:`refresh_rows` (or :meth:`refresh`) to repaint.
"""

from __future__ import annotations

import wx
import wx.dataview as dv

from wx_accessible_grid.model import GridModel

# Width hints -> pixel widths.
_WIDTH = {"narrow": 90, "wide": 200, "auto": 130}


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
    """

    def __init__(self, parent: wx.Window, model: GridModel, label: str = "Grid") -> None:
        self._model = model
        self._columns = list(model.columns())
        self._list = dv.DataViewListCtrl(parent, style=dv.DV_MULTIPLE | dv.DV_ROW_LINES)
        self._list.SetName(label)
        self._populate()

    def _populate(self) -> None:
        """Rebuild columns and rows from the model. DataViewListCtrl is not a
        virtual control, so it stores the rows; for very large data, switch to a
        DataViewCtrl + custom model (out of scope here)."""
        self._list.ClearColumns()
        self._list.DeleteAllItems()
        for col in self._columns:
            self._list.AppendTextColumn(col.label, width=_WIDTH.get(col.width_hint, 130))
        for r in range(self._model.row_count()):
            self._list.AppendItem([self._model.cell_text(r, c.name) for c in self._columns])

    # -- access --------------------------------------------------------
    @property
    def control(self) -> dv.DataViewListCtrl:
        """The underlying ``wx.dataview.DataViewListCtrl``; add this to a sizer."""
        return self._list

    @property
    def model(self) -> GridModel:
        return self._model

    # -- structure -----------------------------------------------------
    def set_columns(self) -> None:
        """Rebuild the columns and rows from the model. Use when the dataset's
        column *shape* changes (e.g. a different radio with a different feature
        set)."""
        self._columns = list(self._model.columns())
        self._populate()

    # -- refresh -------------------------------------------------------
    def refresh(self) -> None:
        """Update every cell in place from the model, keeping the control and the
        screen reader's focus. Falls back to a full rebuild if the row count
        changed."""
        n = self._model.row_count()
        if n != self._list.GetItemCount():
            self._populate()
            return
        for r in range(n):
            for ci, col in enumerate(self._columns):
                self._list.SetTextValue(self._model.cell_text(r, col.name), r, ci)

    def refresh_rows(self, rows: list[int]) -> None:
        """Update just ``rows`` (their item indexes) in place after an edit."""
        n = self._list.GetItemCount()
        for r in rows:
            if 0 <= r < n:
                for ci, col in enumerate(self._columns):
                    self._list.SetTextValue(self._model.cell_text(r, col.name), r, ci)

    # -- selection / focus ---------------------------------------------
    def _current_row(self) -> int | None:
        item = self._list.GetCurrentItem()
        if not item.IsOk():
            return None
        row = self._list.ItemToRow(item)
        return row if row != wx.NOT_FOUND else None

    def selected_rows(self) -> list[int]:
        """Selected row indexes; falls back to the focused row when none are
        selected, so a single-row action still has a target."""
        rows = []
        for item in self._list.GetSelections():
            row = self._list.ItemToRow(item)
            if row != wx.NOT_FOUND:
                rows.append(row)
        if not rows:
            cur = self._current_row()
            if cur is not None:
                rows = [cur]
        return sorted(rows)

    def focused_row(self) -> int | None:
        return self._current_row()

    def select_rows(self, rows: list[int]) -> None:
        """Replace the selection with exactly ``rows``."""
        self._list.UnselectAll()
        n = self._list.GetItemCount()
        for r in rows:
            if 0 <= r < n:
                self._list.SelectRow(r)

    def focus_row(self, row: int) -> None:
        """Move the focused (current) row to ``row``, make it visible, and ensure
        it is read.

        Sets the current item *before* taking focus: if focus arrived first the
        screen reader would announce the stale current row, then announce again
        after the move, a double/wrong announcement on go-to / find / post-edit.
        """
        if not (0 <= row < self._list.GetItemCount()):
            return
        item = self._list.RowToItem(row)
        self._list.SetCurrentItem(item)
        self._list.EnsureVisible(item)
        if wx.Window.FindFocus() is not self._list:
            self._list.SetFocus()
