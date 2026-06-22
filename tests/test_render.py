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
    # model B: the table is NOT a tab stop; cells carry the roving tabindex
    assert 'role="grid" aria-label' in html  # no tabindex on the table element
    assert 'tabindex="-1"' in html
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
    # cells carry stable ids and the roving tabindex (=-1; runtime promotes one to 0)
    assert f'id="{cell_id(0, 1)}"' in rows
    assert 'tabindex="-1"' in rows
    # non-editable row-header cell is marked read-only
    assert 'aria-readonly="true"' in rows


def test_editable_and_raw_markers():
    rows = render_rows(_Model(10), 1, 1, selected=set())
    assert 'data-editable="1"' in rows
    # checkbox/slider carry their raw edit value; combo/text do not
    assert 'data-raw="true"' in rows   # active, odd row
    assert 'data-raw="1"' in rows      # volume row 1 -> 1


def test_row_select_column():
    h = render_grid(_Model(10), label="C", first=0, last=2, selected={1}, row_select=True)
    # leading Select header + a checkbox cell per row
    assert 'id="wag-h-sel"' in h and ">Select<" in h
    assert 'data-select="1"' in h
    assert 'type="checkbox" tabindex="-1" aria-label="Select row 2" checked' in h
    # colcount is shifted by the extra column, and the row header moves to col 2
    assert 'aria-colcount="6"' in h
    assert 'role="rowheader" scope="row" id="wag-r0-c0" aria-colindex="2"' in h
    # without row_select there is no select column
    h2 = render_grid(_Model(10), label="C", first=0, last=2)
    assert "data-select" not in h2 and 'aria-colcount="5"' in h2


def test_full_grid_renders_all_rows():
    # Excel-style: the whole dataset is in one render (no pagination).
    n = 300
    html = render_grid(_Model(n), label="C", first=0, last=n - 1)
    assert 'data-row="0"' in html
    assert f'data-row="{n - 1}"' in html
    assert html.count('role="row"') == n + 1  # data rows + header row


def test_colindex_sequence_for_announcements():
    # The runtime composes "column N" from aria-colindex, so it must be a correct
    # 1-based sequence; with row_select everything shifts right by one.
    rows = render_rows(_Model(5), 0, 0, selected=set())
    assert 'aria-colindex="1"' in rows  # row header (#)
    assert 'aria-colindex="5"' in rows  # last of 5 columns
    rs = render_rows(_Model(5), 0, 0, selected=set(), row_select=True)
    assert 'data-select="1"' in rs and 'aria-colindex="1"' in rs  # select col is 1
    assert 'aria-colindex="6"' in rs  # columns pushed right by the select column


def test_bulk_selected_row_uses_class_not_aria_selected():
    rows = render_rows(_Model(10), 0, 2, selected={1})
    # the bulk-selected row carries the wag-rowsel class
    assert 'data-row="1" class="wag-rowsel"' in rows
    # exactly one row is class-selected
    assert rows.count('class="wag-rowsel"') == 1
    # unselected rows have no class
    assert 'data-row="0" class' not in rows


def test_editor_type_suffix_in_cell_name():
    # Each editable data cell carries a visually-hidden control-type suffix span
    # (now with a stable id and no leading comma) so a screen reader speaks the
    # control type as part of the cell's accessible name.
    rows = render_rows(_Model(10), 0, 0, selected=set())
    assert 'class="wag-sr-only">edit box</span>' in rows   # name (text)
    assert 'class="wag-sr-only">combo box</span>' in rows  # mode (combo)
    assert 'class="wag-sr-only">checkbox</span>' in rows   # active (checkbox)
    assert 'class="wag-sr-only">slider</span>' in rows     # vol (slider)
    # the leading ", " is gone — aria-labelledby tokens are spoken as separate
    # phrases, so the comma would be doubled up
    assert 'wag-sr-only">, ' not in rows
    # the non-editable row-header (#) gets NO suffix (it is an identifier)
    assert '<th role="rowheader" scope="row" id="wag-r0-c0"' in rows
    head_cell = rows.split('id="wag-r0-c0"', 1)[1].split("</th>", 1)[0]
    assert "wag-sr-only" not in head_cell


def test_cell_name_is_composed_with_aria_labelledby():
    # The header fix: each data cell's accessible NAME is composed via aria-labelledby
    # from the row header (channel), the column header, the value span, and the
    # control-type span — so VoiceOver speaks "channel, header, value, type" on every
    # focus move with no JS (it never receives the VO+arrow). The value lives in its
    # own span so the cell is never self-referenced.
    rows = render_rows(_Model(10), 0, 0, selected=set())
    # the "name" column is data-col 1: rowheader c0, column header c1, value, suffix.
    # Selection state is intentionally NOT in the per-move name (announcing it on
    # every move is the chatter bug we already fixed).
    assert 'aria-labelledby="wag-r0-c0 wag-h-c1 wag-r0-c1-v wag-r0-c1-s"' in rows
    assert '<span id="wag-r0-c1-v">name0</span>' in rows
    # the row header's channel value is wrapped so data cells can reference it
    assert '<span id="wag-r0-c0-v">1</span>' in rows
    # the row header is itself NOT labelledby-composed (it is the identifier)
    head_tag = rows.split('<th role="rowheader" scope="row" id="wag-r0-c0"', 1)[1].split(">", 1)[0]
    assert "aria-labelledby" not in head_tag
    # no per-row selection-status span exists (selection is announced on action,
    # not baked into every cell's name)
    assert "-sel" not in rows


def test_readonly_cell_announces_read_only():
    # A non-editable data column (editor "none", not a row header) says "read only".
    class RO(_Model):
        def __init__(self):
            super().__init__(5)
            self._cols = [
                Column("num", "#", editor=NONE, is_row_header=True),
                Column("calc", "Computed", editor=NONE),  # read-only data cell
                Column("name", "Name"),
            ]

    rows = render_rows(RO(), 0, 0, selected=set())
    assert 'class="wag-sr-only">read only</span>' in rows


def test_render_never_emits_aria_selected():
    # The whole point of the new selection model: aria-selected is added only at
    # runtime on range cells, never rendered, and never set to "false".
    for kw in ({}, {"row_select": True}):
        h = render_grid(_Model(10), label="C", first=0, last=4, selected={1, 3}, **kw)
        assert "aria-selected" not in h
        assert 'aria-selected="false"' not in h
    rows = render_rows(_Model(10), 0, 4, selected={2}, row_select=True)
    assert "aria-selected" not in rows
