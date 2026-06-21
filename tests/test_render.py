"""Tests for the ARIA grid HTML renderer (no wx needed)."""

from __future__ import annotations

from wx_accessible_grid.model import CHECKBOX, COMBO, NONE, SLIDER, Column, GridModel, SetResult
from wx_accessible_grid.render import cell_id, render_grid, render_rows


class _Model(GridModel):
    def __init__(self, n=250):
        self._cols = [
            Column("num", "#", editor=NONE, is_row_header=True),
            Column("name", "Name"),
            Column("mode", "Mode", editor=COMBO, choices=["FM", "AM"]),
            Column("active", "Active", editor=CHECKBOX),
            Column("vol", "Volume", editor=SLIDER, min=0, max=10),
        ]
        self._n = n

    def columns(self):
        return self._cols

    def row_count(self):
        return self._n

    def display(self, row, column):
        if column == "num":
            return str(row + 1)
        if column == "active":
            return "Yes" if row % 2 else "No"
        return f"{column}{row}"

    def edit_value(self, row, column):
        if column == "active":
            return "true" if row % 2 else "false"
        if column == "vol":
            return str(row % 11)
        return self.display(row, column)

    def set_cell(self, row, column, value):
        return SetResult(True, value, "ok")


def test_grid_skeleton_and_counts():
    html = render_grid(_Model(250), label="Channels", first=0, last=99)
    assert 'id="wag-grid"' in html
    assert 'role="grid"' in html
    assert 'tabindex="0"' in html  # the table is the single focusable element
    assert 'aria-label="Channels"' in html
    assert 'aria-rowcount="251"' in html  # 250 rows + header
    assert 'aria-colcount="5"' in html
    assert 'aria-multiselectable="true"' in html
    # live regions are siblings of the table, present at parse time
    assert 'id="wag-live"' in html and 'aria-live="polite"' in html
    assert 'id="wag-live-assertive"' in html and 'aria-live="assertive"' in html
    assert '<th role="columnheader" scope="col" id="wag-h-c0" data-col="0"' in html


def test_only_requested_rows_rendered():
    html = render_grid(_Model(250), label="C", first=100, last=119)
    assert 'data-row="100"' in html
    assert 'data-row="119"' in html
    assert 'data-row="120"' not in html
    assert 'data-row="99"' not in html


def test_row_and_cell_semantics():
    rows = render_rows(_Model(10), 0, 0, selected=set())
    assert 'role="row"' in rows
    # absolute row 0 -> aria-rowindex 2 (header is 1)
    assert 'aria-rowindex="2"' in rows
    assert '<th role="rowheader" scope="row"' in rows
    assert 'role="gridcell"' in rows
    # cells carry stable ids and NO tabindex (focus lives on the table)
    assert f'id="{cell_id(0, 1)}"' in rows
    assert "tabindex" not in rows
    # non-editable row-header cell is marked read-only
    assert 'aria-readonly="true"' in rows


def test_editable_and_raw_markers():
    rows = render_rows(_Model(10), 1, 1, selected=set())
    assert 'data-editable="1"' in rows
    # checkbox/slider carry their raw edit value; combo/text do not
    assert 'data-raw="true"' in rows   # active, odd row
    assert 'data-raw="1"' in rows      # volume row 1 -> 1


def test_selection_marked():
    rows = render_rows(_Model(10), 0, 2, selected={1})
    # the selected row's <tr> is marked
    assert 'aria-selected="true" data-row="1"' in rows
    # exactly one row is selected at the <tr> level
    assert rows.count('aria-selected="true" data-row=') == 1
    # unselected rows are explicitly false
    assert 'aria-selected="false" data-row="0"' in rows
