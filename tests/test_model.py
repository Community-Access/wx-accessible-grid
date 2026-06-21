"""Tests for the data model (no wx needed)."""

from __future__ import annotations

import pytest

from wx_accessible_grid.model import (
    CHECKBOX,
    NONE,
    Column,
    GridModel,
    SetResult,
)


def test_unknown_editor_rejected():
    with pytest.raises(ValueError):
        Column("x", "X", editor="dropdown")


def test_row_header_and_none_are_read_only():
    assert Column("n", "#", is_row_header=True).editable is False
    assert Column("c", "C", editor=NONE).editable is False
    # An explicit editable=True is overridden for a row header.
    assert Column("n", "#", is_row_header=True, editable=True).editable is False


def test_checkbox_column_keeps_editable():
    assert Column("on", "On", editor=CHECKBOX).editable is True


class _Model(GridModel):
    def __init__(self):
        self._cols = [
            Column("num", "#", editor=NONE, is_row_header=True),
            Column("name", "Name"),
        ]
        self._data = [{"name": "a"}, {"name": "b"}]

    def columns(self):
        return self._cols

    def row_count(self):
        return len(self._data)

    def display(self, row, column):
        return str(row + 1) if column == "num" else self._data[row][column]

    def set_cell(self, row, column, value):
        self._data[row][column] = value
        return SetResult(True, value, "ok")


def test_defaults_and_helpers():
    m = _Model()
    assert m.row_count() == 2
    assert m.edit_value(0, "name") == "a"  # defaults to display
    assert m.is_editable(0, "name") is True
    assert m.is_editable(0, "num") is False
    assert m.row_label(0) == "1"  # row-header cell text
    assert m.choices(0, "name") == []


def test_delete_unsupported_by_default():
    m = _Model()
    res = m.delete_rows([0])
    assert res.ok is False and "not supported" in res.message.lower()


def test_set_cell_round_trip():
    m = _Model()
    res = m.set_cell(0, "name", "z")
    assert res.ok and res.display == "z"
    assert m.display(0, "name") == "z"
