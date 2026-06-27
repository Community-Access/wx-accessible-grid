"""Tests for the data model (no wx needed)."""

from __future__ import annotations

import pytest

from wx_accessible_grid.model import Column, GridModel, clamp_column


def test_unknown_width_hint_rejected():
    with pytest.raises(ValueError):
        Column("x", "X", width_hint="huge")


def test_column_defaults():
    col = Column("name", "Name")
    assert col.is_row_header is False
    assert col.width_hint == "auto"


class _Model(GridModel):
    def __init__(self):
        self._cols = [
            Column("num", "#", is_row_header=True, width_hint="narrow"),
            Column("name", "Name"),
        ]
        self._data = [{"name": "Alpha"}, {"name": "Bravo"}]

    def columns(self):
        return self._cols

    def row_count(self):
        return len(self._data)

    def cell_text(self, row, column):
        return str(row + 1) if column == "num" else self._data[row][column]


def test_row_count_and_cell_text():
    m = _Model()
    assert m.row_count() == 2
    assert m.cell_text(0, "num") == "1"
    assert m.cell_text(1, "name") == "Bravo"


def test_row_label_uses_row_header_cell():
    assert _Model().row_label(1) == "2"  # the "num" cell text, not the index


def test_row_label_falls_back_to_one_based_number():
    class NoHeader(_Model):
        def columns(self):
            return [Column("name", "Name")]

    assert NoHeader().row_label(0) == "1"


def test_column_names_in_order():
    assert _Model().column_names() == ["num", "name"]


def test_clamp_column_moves_and_stops_at_edges():
    assert clamp_column(0, 1, 3) == 1  # right
    assert clamp_column(2, 1, 3) == 2  # right off the end stays put
    assert clamp_column(0, -1, 3) == 0  # left off the start stays put
    assert clamp_column(2, -1, 3) == 1  # left
    assert clamp_column(0, 1, 0) == 0  # no columns
