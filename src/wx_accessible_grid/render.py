"""Render a :class:`~wx_accessible_grid.model.GridModel` to ARIA grid HTML.

Why a real ``<table role="grid">`` and not a stack of ``<div>``s: a true table
gives the screen reader free, correct announcements — move down a column and it
speaks the row header; move across a row and it speaks the column header; it
knows "row 105 of 10,000" from ``aria-rowcount`` even though only one page is in
the DOM. ``role="grid"`` then layers *application* navigation on top.

Focus model (model B — roving tabindex with REAL DOM focus): every cell carries
``tabindex="-1"`` and a stable id; the runtime promotes the active cell to
``tabindex="0"`` and calls ``cell.focus()`` on it, so both VoiceOver and NVDA
follow the real cursor and read each cell on every arrow. There is no
``aria-activedescendant`` (its support is weak in VoiceOver, which left the
reader not following plain arrows). Focus always lands on the gridcell itself,
never a child element (NVDA #8395 — focusing a child flips NVDA to browse mode and
kills the arrows); only the editor input takes focus, while editing.

Only one page of rows is ever in the DOM. ``aria-rowindex`` on each row is the
*absolute* 1-based position (header row is 1, the first data row is 2), so paging
is invisible to the user's sense of place.

Accessible name (the header fix): a real table is *supposed* to make the screen
reader speak the row/column header as you move, but VoiceOver does NOT do that on
focus move inside ``role="grid"`` — and because VoiceOver intercepts VO+arrows,
the runtime's live-region announcement never fires either, so on macOS the header
goes unspoken. The fix lives here, in the static DOM: each data cell carries an
``aria-labelledby`` that composes its name from the row-header cell, the column
header ``<th>``, the value (wrapped in its own span), and the control-type span —
"5, Frequency, 146.520, edit box". VoiceOver recomputes and speaks that on every
focus landing with no JS, and NVDA reads the same name in focus mode (so the
runtime stops echoing plain moves into the live region to avoid double-speak).
"""

from __future__ import annotations

from html import escape

from wx_accessible_grid.model import CHECKBOX, COMBO, SLIDER, STEPPER, TEXT, GridModel

# id helpers — kept in one place so the renderer and the runtime agree.
GRID_ID = "wag-grid"

# Spoken control type per editor. We surface it INSIDE the cell as a
# visually-hidden suffix span so it becomes part of the cell's accessible NAME and
# VoiceOver speaks it on every VO+arrow move (e.g. "Frequency, 146.520, edit box").
# aria-roledescription on a gridcell is read inconsistently by VoiceOver, and the
# accessible name is the one channel both VoiceOver and NVDA reliably read, so the
# suffix span is the source of truth; the JS runtime mirrors the same word into its
# live-region announcement for redundancy. Read-only data cells say "read only".
_EDITOR_SUFFIX = {
    TEXT: "edit box",
    COMBO: "combo box",
    CHECKBOX: "checkbox",
    SLIDER: "slider",
    STEPPER: "stepper",
}
# Non-editable data cells (not the row-header) announce that they are read only.
_READONLY_SUFFIX = "read only"


def _editor_suffix(model: GridModel, row: int, col) -> str:
    """The spoken control-type word for a cell, or "" when it should be silent.

    The row-header (channel number / id) is left without a suffix: it is an
    identifier, not a control, and gets spoken as the row label on vertical moves.
    """
    if col.is_row_header:
        return ""
    if not model.is_editable(row, col.name):
        return _READONLY_SUFFIX
    return _EDITOR_SUFFIX.get(col.editor, "")


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
    toggled with Space/Enter on the cell; the cell itself takes the roving focus,
    so the inner input is tabindex=-1 and not a separate tab stop. Bulk row
    selection rides on the checkbox + the row's ``wag-rowsel`` class, NOT
    ``aria-selected`` (kept exclusively for cell-range selection)."""
    checked = " checked" if sel else ""
    return (
        f'<td role="gridcell" id="wag-r{row}-csel" data-select="1" tabindex="-1" '
        f'aria-colindex="{colindex}">'
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
            # tabindex=-1 on every cell; the runtime promotes the active cell to 0
            # (roving tabindex, model B real DOM focus).
            common = (
                f'id="{cid}" aria-colindex="{ci + 1 + offset}" tabindex="-1" '
                f"{_cell_attrs(model, row, col, ci)}"
            )
            # Compose the cell's accessible NAME from referenced child spans so a
            # screen reader speaks the full context — channel, column header, value,
            # control type — on every focus move. This is the ONE channel VoiceOver
            # reads when VO+arrows never reach the page: the JS live-region
            # announcement can't fire under VoiceOver, but the computed name
            # (aria-labelledby) is spoken on focus. The value lives in its own span
            # so aria-labelledby can target it WITHOUT self-referencing the cell (a
            # self-idref re-walks the subtree and on WebKit can drop or double the
            # value). The control-type span keeps the spoken word, gets a stable id,
            # and drops the leading comma (labelledby tokens are spoken as separate
            # phrases). The editor swaps the cell's children while editing, so the JS
            # drops aria-labelledby for the duration and rebuilds these spans on
            # commit; cancel restores them from cell.__orig.
            vid = f"{cid}-v"
            sid = f"{cid}-s"
            val = f'<span id="{vid}">{text}</span>'
            suffix = _editor_suffix(model, row, col)
            tail = f'<span id="{sid}" class="wag-sr-only">{escape(suffix)}</span>' if suffix else ""
            if col.is_row_header:
                # The row header (channel number) is an identifier the data cells
                # reference by id; it just speaks its own value.
                cells.append(f'<th role="rowheader" scope="row" {common}>{val}{tail}</th>')
            else:
                # Static name order: channel (row header), column header, value,
                # control type -> "5, Frequency, 146.520, edit box". Reference the
                # existing column-header <th> and the row-header cell by id, so no
                # text is duplicated and the ids stay stable across paging.
                # NOTE: selection state is deliberately NOT part of the per-move
                # name — announcing "selected" on every move is the chatter bug we
                # already fixed. Selection is announced only when you actually
                # select (toggleSelect / the range + Edit-menu commands).
                lbl = f"{cell_id(row, 0)} {header_id(ci)} {vid}"
                if suffix:
                    lbl += f" {sid}"
                cells.append(
                    f'<td role="gridcell" {common} aria-labelledby="{lbl}">{val}{tail}</td>'
                )
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
        f'<table id="{GRID_ID}" class="wag-grid" role="grid" '
        f'aria-label="{escape(label)}" aria-rowcount="{total + 1}" '
        f'aria-colcount="{len(cols) + offset}" aria-multiselectable="true">'
        f"<caption>{caption}</caption>"
        f'<thead><tr role="row" aria-rowindex="1">{headers}</tr></thead>'
        f"<tbody>{render_rows(model, first, last, selected, row_select=row_select)}</tbody>"
        f"</table>"
    )
