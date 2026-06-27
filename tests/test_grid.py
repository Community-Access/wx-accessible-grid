"""Smoke tests for the native grid widget.

These need wx and a display. They skip cleanly where neither is available (a
headless CI box), so the model tests still run everywhere.
"""

from __future__ import annotations

import pytest

wx = pytest.importorskip("wx")

from wx_accessible_grid import AccessibleGrid, Column, GridModel  # noqa: E402


class _Model(GridModel):
    def __init__(self, n=5):
        self._n = n
        self._cols = [Column("num", "#", is_row_header=True), Column("name", "Name")]

    def columns(self):
        return self._cols

    def row_count(self):
        return self._n

    def cell_text(self, row, column):
        return str(row + 1) if column == "num" else f"Row {row + 1}"


@pytest.fixture
def app():
    try:
        application = wx.App()
    except Exception as exc:  # no display
        pytest.skip(f"no wx display: {exc}")
    yield application
    application.Destroy()


def test_grid_builds_columns_and_rows(app):
    frame = wx.Frame(None)
    grid = AccessibleGrid(frame, _Model(5), label="Channels")
    assert grid.control.GetColumnCount() == 2
    assert grid.control.GetItemCount() == 5
    assert grid.control.GetName() == "Channels"
    # virtual-list callback resolves text through the model
    assert grid.control.OnGetItemText(2, 0) == "3"
    assert grid.control.OnGetItemText(2, 1) == "Row 3"
    frame.Destroy()


def test_selection_helpers(app):
    frame = wx.Frame(None)
    grid = AccessibleGrid(frame, _Model(5), label="Channels")
    grid.select_rows([1, 3])
    assert grid.selected_rows() == [1, 3]
    # out-of-range rows are ignored, not errors
    grid.select_rows([99])
    assert grid.selected_rows() == [] or grid.selected_rows() == [grid.focused_row()]
    frame.Destroy()


def test_refresh_after_row_count_change(app):
    frame = wx.Frame(None)
    model = _Model(5)
    grid = AccessibleGrid(frame, model, label="Channels")
    model._n = 8
    grid.refresh()
    assert grid.control.GetItemCount() == 8
    frame.Destroy()


def test_set_columns_rebuilds_for_a_new_shape(app):
    frame = wx.Frame(None)
    model = _Model(5)
    grid = AccessibleGrid(frame, model, label="Channels")
    assert grid.control.GetColumnCount() == 2

    # swap to a different column set, then rebuild
    model._cols = [Column("num", "#", is_row_header=True)]
    model._n = 3
    grid.set_columns()
    assert grid.control.GetColumnCount() == 1
    assert grid.control.GetItemCount() == 3
    assert grid.current_column() == 0
    frame.Destroy()


def _key(code):
    evt = wx.KeyEvent(wx.wxEVT_KEY_DOWN)
    evt.SetKeyCode(code)
    return evt


def test_left_right_moves_cell_cursor_and_announces(app):
    frame = wx.Frame(None)
    spoken = []
    grid = AccessibleGrid(frame, _Model(5), label="Channels", announce=spoken.append)
    grid.focus_row(2)  # row index 2 -> "3" / "Row 3"

    assert grid.current_column() == 0
    grid._on_key_down(_key(wx.WXK_RIGHT))
    assert grid.current_column() == 1
    assert spoken[-1] == "Row 3, Name"  # value, then column label

    grid._on_key_down(_key(wx.WXK_RIGHT))  # off the right edge, stays on last col
    assert grid.current_column() == 1
    assert spoken[-1] == "Row 3, Name"

    grid._on_key_down(_key(wx.WXK_LEFT))
    assert grid.current_column() == 0
    assert spoken[-1] == "3, #"
    assert grid.current_cell() == (2, 0)
    frame.Destroy()
