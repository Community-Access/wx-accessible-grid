"""Render a :class:`~wx_accessible_grid.model.GridModel` to ARIA grid HTML.

Why a real ``<table role="grid">`` and not a stack of ``<div>``s: a true table
gives the screen reader free, correct announcements — move down a column and it
speaks the row header; move across a row and it speaks the column header; it
knows "row 105 of 10,000" from ``aria-rowcount`` even though only one page is in
the DOM. ``role="grid"`` then layers *application* navigation on top.

Focus model: the **table** is the single focusable element (``tabindex="0"``)
and owns ``aria-activedescendant`` pointing at the active cell's id. This is the
pattern NVDA reliably enters and stays in focus mode for — a focused
``role="gridcell"`` with a roving ``tabindex`` does **not** dependably trigger
focus mode in WebView2, which would leave arrow keys dead. So cells carry stable
ids but no ``tabindex``; the runtime moves ``aria-activedescendant`` instead of
calling ``cell.focus()``, which also means edits and deletes never bounce focus
through ``document.body`` (and out of focus mode).

Only one page of rows is ever in the DOM. ``aria-rowindex`` on each row is the
*absolute* 1-based position (header row is 1, the first data row is 2), so paging
is invisible to the user's sense of place.
"""

from __future__ import annotations

from html import escape

from wx_accessible_grid.model import CHECKBOX, SLIDER, STEPPER, GridModel

# id helpers — kept in one place so the renderer and the runtime agree.
GRID_ID = "wag-grid"


def cell_id(row: int, col_index: int) -> str:
    return f"wag-r{row}-c{col_index}"


def header_id(col_index: int) -> str:
    return f"wag-h-c{col_index}"


def _cell_attrs(model: GridModel, row: int, col, col_index: int) -> str:
    """data-* / aria-* the runtime needs to build the right editor for a cell."""
    editable = model.is_editable(row, col.name)
    attrs = [f'data-col="{col_index}"']
    if editable:
        attrs.append('data-editable="1"')
        # The editor's starting value, when it differs from the shown text.
        if col.editor in (CHECKBOX, SLIDER, STEPPER):
            attrs.append(f'data-raw="{escape(model.edit_value(row, col.name), quote=True)}"')
    else:
        attrs.append('aria-readonly="true"')
    return " ".join(attrs)


def _select_cell(row: int, label: str, sel: bool, colindex: int) -> str:
    """The leading row-selection checkbox cell (a real checkbox, so it both looks
    like one for sighted users and announces its state to a screen reader). It is
    toggled with Space/Enter on the cell; the table keeps focus, so the input is
    tabindex=-1 and not a separate tab stop. Bulk row selection rides on the
    checkbox + the row's ``wag-rowsel`` class, NOT ``aria-selected`` (kept
    exclusively for cell-range selection so plain arrows stay quiet)."""
    checked = " checked" if sel else ""
    return (
        f'<td role="gridcell" id="wag-r{row}-csel" data-select="1" aria-colindex="{colindex}">'
        f'<input type="checkbox" tabindex="-1" aria-label="Select row {escape(label)}"{checked}>'
        f"</td>"
    )


def render_rows(
    model: GridModel,
    first: int,
    last: int,
    selected: set[int],
    *,
    row_select: bool = False,
) -> str:
    """Render ``<tr>`` rows for absolute indexes ``first..last`` inclusive.

    Used for the full page render and for the tbody-only refresh on paging,
    deletes, and edits, so refreshed rows always match the originals exactly.
    When ``row_select`` is set, each row begins with a selection checkbox.

    ``aria-selected`` is never emitted here — it is added at runtime only on cells
    inside an active range, and is never set to ``"false"``. Bulk-selected rows
    carry the ``wag-rowsel`` class instead.
    """
    cols = model.columns()
    offset = 1 if row_select else 0
    out: list[str] = []
    for row in range(first, last + 1):
        rowsel = row in selected
        cells: list[str] = []
        if row_select:
            cells.append(_select_cell(row, model.row_label(row), rowsel, 1))
        for ci, col in enumerate(cols):
            text = escape(model.display(row, col.name))
            cid = cell_id(row, ci)
            common = (
                f'id="{cid}" aria-colindex="{ci + 1 + offset}" '
                f"{_cell_attrs(model, row, col, ci)}"
            )
            if col.is_row_header:
                cells.append(f'<th role="rowheader" scope="row" {common}>{text}</th>')
            else:
                cells.append(f'<td role="gridcell" {common}>{text}</td>')
        cls = ' class="wag-rowsel"' if rowsel else ""
        out.append(
            f'<tr role="row" aria-rowindex="{row + 2}" data-row="{row}"{cls}>'
            f'{"".join(cells)}</tr>'
        )
    return "".join(out)


def render_grid(
    model: GridModel,
    *,
    label: str,
    first: int,
    last: int,
    selected: set[int] | None = None,
    description: str = "",
    row_select: bool = False,
) -> str:
    """Render the whole grid (live regions, caption, header row, and rows).

    ``aria-rowcount`` is total rows + 1 (the header row counts); each row's
    ``aria-rowindex`` is offset to match. Two visually-hidden live regions are
    rendered as *siblings* of the table so announcements have a registered target
    at parse time and don't depend on the host webview. When ``row_select`` is
    set, a leading selection-checkbox column is added.
    """
    selected = selected or set()
    cols = model.columns()
    total = model.row_count()
    offset = 1 if row_select else 0

    headers = ""
    if row_select:
        headers += '<th role="columnheader" scope="col" id="wag-h-sel" aria-colindex="1">Select</th>'
    headers += "".join(
        f'<th role="columnheader" scope="col" id="{header_id(ci)}" data-col="{ci}" '
        f'aria-colindex="{ci + 1 + offset}">{escape(c.label)}</th>'
        for ci, c in enumerate(cols)
    )
    caption = escape(label)
    if description:
        caption += f' <span class="wag-desc">{escape(description)}</span>'

    live = (
        '<div id="wag-live" class="wag-sr-only" aria-live="polite" aria-atomic="true"></div>'
        '<div id="wag-live-assertive" class="wag-sr-only" aria-live="assertive" '
        'aria-atomic="true"></div>'
    )
    return (
        f"{live}"
        f'<table id="{GRID_ID}" class="wag-grid" role="grid" tabindex="0" '
        f'aria-label="{escape(label)}" aria-rowcount="{total + 1}" '
        f'aria-colcount="{len(cols) + offset}" aria-multiselectable="true">'
        f"<caption>{caption}</caption>"
        f'<thead><tr role="row" aria-rowindex="1">{headers}</tr></thead>'
        f"<tbody>{render_rows(model, first, last, selected, row_select=row_select)}</tbody>"
        f"</table>"
    )
