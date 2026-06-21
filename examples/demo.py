"""Standalone demo of AccessibleGrid — run it with a screen reader.

    pip install -e .
    python examples/demo.py

It builds a 2,500-row Excel-style grid (the whole thing in the DOM, no paging)
with one of every editor: text, combo, checkbox, slider, stepper. Events print
to stdout so you can watch the grid fire them. Try, with NVDA running:

* Arrow around — it speaks the cell value, and leads with the row label going
  down a column. Plain arrows say nothing about selection. Home/End and
  Ctrl+Home/Ctrl+End jump; Ctrl+arrow jumps to a region edge; PageUp/Down move 20.
* Tab and Shift+Tab move cell to cell and wrap at the row ends.
* F2 or just start typing to edit a cell; Enter commits and drops down a row,
  Escape cancels then (pressed again) leaves the grid. F6 also leaves.
* Shift+arrow extends a cell range ("Selected B2 to B5, 4 cells"); Ctrl+Space
  selects the column, Shift+Space the row, Ctrl+A all; a plain arrow collapses it.
* Space selects the row for bulk ops (the checkbox column); Delete deletes the
  selection. The Applications key (or Shift+F10) opens a native Edit/Delete menu.
"""

from __future__ import annotations

import wx

from wx_accessible_grid import (
    CHECKBOX,
    COMBO,
    NONE,
    SLIDER,
    STEPPER,
    TEXT,
    AccessibleGrid,
    Column,
    ContextMenuItem,
    GridModel,
    SetResult,
)

MODES = ["FM", "NFM", "AM", "USB", "LSB", "CW", "DV"]


class DemoModel(GridModel):
    """An in-memory grid: a list of dict rows, all validation inline."""

    def __init__(self, n: int = 2500) -> None:
        self._cols = [
            Column("num", "#", editor=NONE, is_row_header=True),
            Column("name", "Name", editor=TEXT),
            Column("mode", "Mode", editor=COMBO, choices=MODES),
            Column("active", "Active", editor=CHECKBOX),
            Column("volume", "Volume", editor=SLIDER, min=0, max=100, step=1),
            Column("priority", "Priority", editor=STEPPER, min=0, max=10, step=1),
            Column("comment", "Comment", editor=TEXT),
        ]
        self._rows = [
            {
                "name": f"Channel {i + 1}",
                "mode": MODES[i % len(MODES)],
                "active": i % 3 == 0,
                "volume": (i * 7) % 101,
                "priority": i % 11,
                "comment": "",
            }
            for i in range(n)
        ]

    def columns(self) -> list[Column]:
        return self._cols

    def row_count(self) -> int:
        return len(self._rows)

    def display(self, row: int, column: str) -> str:
        if column == "num":
            return str(row + 1)
        val = self._rows[row][column]
        if column == "active":
            return "Yes" if val else "No"
        return str(val)

    def edit_value(self, row: int, column: str) -> str:
        if column == "active":
            return "true" if self._rows[row]["active"] else "false"
        if column == "num":
            return str(row + 1)
        return str(self._rows[row][column])

    def set_cell(self, row: int, column: str, value: str) -> SetResult:
        if column in ("volume", "priority"):
            try:
                num = int(float(value))
            except ValueError:
                return SetResult(False, message=f"{column} must be a number")
            lo, hi = (0, 100) if column == "volume" else (0, 10)
            if not lo <= num <= hi:
                return SetResult(False, message=f"{column} must be {lo} to {hi}")
            self._rows[row][column] = num
            return SetResult(True, str(num), f"{column} set to {num}")
        if column == "active":
            on = value in ("true", "1", "yes")
            self._rows[row]["active"] = on
            return SetResult(True, "Yes" if on else "No", "Active on" if on else "Active off")
        if column == "mode":
            if value not in MODES:
                return SetResult(False, message=f"{value} is not a valid mode")
            self._rows[row]["mode"] = value
            return SetResult(True, value, f"Mode {value}")
        self._rows[row][column] = value
        return SetResult(True, value, f"{column} updated")

    def delete_rows(self, rows: list[int]) -> SetResult:
        for r in sorted(rows, reverse=True):
            if 0 <= r < len(self._rows):
                del self._rows[r]
        return SetResult(True, message=f"Deleted {len(rows)} row(s)")


class DemoFrame(wx.Frame):
    def __init__(self) -> None:
        super().__init__(None, title="wx-accessible-grid demo", size=(900, 600))
        panel = wx.Panel(self)
        self.model = DemoModel()
        self.grid = AccessibleGrid(
            panel,
            self.model,
            label="Demo channels",
            row_select=True,  # page_size defaults to 0 — whole grid, no pagination
            on_context=self._on_context,
            on_navigate=lambda r, c: print(f"navigate -> row {r}, {c}"),
            on_activate=lambda r, c: print(f"activate -> row {r}, {c}"),
            on_selection_changed=lambda rows: print(f"selection -> {rows}"),
            on_edit_committed=lambda r, c, v: print(f"edit committed -> row {r}, {c} = {v!r}"),
            description="Arrow/Tab to move, F2 or type to edit, Space to select.",
        )
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.grid.control, 1, wx.EXPAND)
        panel.SetSizer(sizer)
        self.Show()
        # The grid auto-enters on load (lands the cursor on the first cell), so no
        # explicit focus() call is needed here.

    def _on_context(self, row: int, column: str) -> None:
        # Find the column index for edit_cell; fall back to the first column.
        names = [c.name for c in self.model.columns()]
        col = names.index(column) if column in names else 0
        self.grid.show_context_menu([
            ContextMenuItem(f"Edit {column} (F2)", lambda: self.grid.edit_cell(row, col)),
            ContextMenuItem(f"Delete row {row + 1} (Del)",
                            lambda: self.grid._delete_rows([row])),
        ])


if __name__ == "__main__":
    app = wx.App()
    DemoFrame()
    app.MainLoop()
