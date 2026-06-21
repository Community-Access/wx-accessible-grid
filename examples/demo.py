"""Standalone demo of AccessibleGrid — run it with a screen reader.

    pip install -e .
    python examples/demo.py

It builds a 2,500-row grid (to exercise paging and large-dataset performance,
the exact condition that broke earlier in-grid attempts) with one of every
editor: text, combo, checkbox, slider, stepper. Try, with NVDA running:

* Arrow around — moving across a row speaks the column; moving down speaks the
  row number. Arrow past the bottom/top to roll onto the next/previous page.
* F2 or Enter on a cell to edit; Enter commits, Escape cancels.
* Space (or Ctrl+Space) to select a row; Delete to delete selected rows.
* The Applications key (or Shift+F10) on a cell opens a native row menu.
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
            page_size=100,
            row_select=True,
            on_context=self._on_context,
            description="Arrow to move, F2 or Enter to edit, Space to select.",
        )
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.grid.control, 1, wx.EXPAND)
        panel.SetSizer(sizer)
        self.Show()
        wx.CallAfter(self.grid.focus)

    def _on_context(self, row: int, column: str) -> None:
        menu = wx.Menu()
        edit = menu.Append(wx.ID_ANY, f"Edit row {row + 1} (full)\tEnter")
        delete = menu.Append(wx.ID_ANY, f"Delete row {row + 1}\tDel")
        self.Bind(
            wx.EVT_MENU,
            lambda _e: self.grid.announce(f"Would open full editor for row {row + 1}"),
            edit,
        )
        self.Bind(
            wx.EVT_MENU,
            lambda _e: (self.model.delete_rows([row]), self.grid.refresh()),
            delete,
        )
        self.grid.control.PopupMenu(menu)
        menu.Destroy()


if __name__ == "__main__":
    app = wx.App()
    DemoFrame()
    app.MainLoop()
