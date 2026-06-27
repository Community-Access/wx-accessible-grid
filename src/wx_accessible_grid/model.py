"""The data model an :class:`~wx_accessible_grid.grid.AccessibleGrid` reads.

The grid is a native virtual ``wx.ListCtrl``: it never stores your rows, it asks
this model for each visible cell's text as it paints. So all the data lives
behind a :class:`GridModel` you provide, and the same grid drives an in-memory
list, a database, or (the reason this library exists) a radio's memory channels.

Editing is host-driven. A native list does not edit in place, so the host opens
a real native control (an edit dialog, say), writes the result back into the
model, and calls :meth:`~wx_accessible_grid.grid.AccessibleGrid.refresh_rows`.
That keeps every editor a genuine native control the screen reader reads
correctly, instead of an emulated in-cell widget.

The model is pure Python with no wx in it, so columns, row counts, and cell
formatting are all unit-testable headless, without a display.
"""

from __future__ import annotations

from dataclasses import dataclass

# Column width hints, mapped to pixel widths by the grid.
NARROW = "narrow"
WIDE = "wide"
AUTO = "auto"

WIDTH_HINTS = frozenset({NARROW, WIDE, AUTO})


@dataclass
class Column:
    """One grid column.

    ``is_row_header=True`` marks the column that identifies the row (a channel
    number, an id). It is read first by :meth:`GridModel.row_label` when
    announcing a row, so a grid should have at most one and it should come first.
    ``width_hint`` is one of ``"narrow"``, ``"wide"``, or ``"auto"``.
    """

    name: str
    label: str
    is_row_header: bool = False
    width_hint: str = AUTO

    def __post_init__(self) -> None:
        if self.width_hint not in WIDTH_HINTS:
            raise ValueError(
                f"Column {self.name!r}: unknown width_hint {self.width_hint!r}; "
                f"expected one of {sorted(WIDTH_HINTS)}"
            )


class GridModel:
    """Subclass this and implement the data access for your grid.

    Row indexes are absolute and 0-based across the whole dataset; column access
    is by ``name``. Only :meth:`columns`, :meth:`row_count`, and :meth:`cell_text`
    are required.
    """

    def columns(self) -> list[Column]:
        raise NotImplementedError

    def row_count(self) -> int:
        """Total number of rows."""
        raise NotImplementedError

    def cell_text(self, row: int, column: str) -> str:
        """Text the list paints and the screen reader reads for this cell."""
        raise NotImplementedError

    def row_label(self, row: int) -> str:
        """Accessible name for a whole row, used when announcing selection or in
        a context menu. Defaults to the row-header cell's text, else the 1-based
        row number."""
        for col in self.columns():
            if col.is_row_header:
                return self.cell_text(row, col.name)
        return str(row + 1)

    def column_names(self) -> list[str]:
        """The column names in order (handy for mapping a column index to a name
        when wiring host actions)."""
        return [col.name for col in self.columns()]
