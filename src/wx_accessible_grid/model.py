"""The data model an :class:`~wx_accessible_grid.grid.AccessibleGrid` renders.

The grid is *just a view*. All data, validation, and persistence live behind a
:class:`GridModel` you provide, so the same grid drives an in-memory list, a
database, or (the reason this library exists) a radio's memory channels. The
grid never mutates your data directly — it asks the model to, and shows whatever
the model says is now true. That round trip is what lets a model reject or
normalize an edit (e.g. snap a frequency, refuse an immutable cell) and have the
screen reader announce the *authoritative* result, not the raw keystrokes.

Columns declare which **editor** a cell uses. The five editors mirror the
controls real data-entry software uses (and exactly the three a blind ham's paid
radio software was found to use — text, combo, checkbox — plus slider and
stepper for completeness):

* ``text``     — a single-line edit box.
* ``combo``    — a drop-down of fixed choices (also stands in for radio groups).
* ``checkbox`` — a boolean toggle.
* ``slider``   — a range control adjusted with the arrow keys.
* ``stepper``  — a number spinner (type a value or step it).
* ``none``     — never editable (e.g. a computed or identifier column).
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Editor kinds. Plain strings so a model can be built without importing enums.
TEXT = "text"
COMBO = "combo"
CHECKBOX = "checkbox"
SLIDER = "slider"
STEPPER = "stepper"
NONE = "none"

EDITORS = frozenset({TEXT, COMBO, CHECKBOX, SLIDER, STEPPER, NONE})


@dataclass
class Column:
    """One grid column.

    ``editor`` picks the in-cell control; ``editable=False`` (or ``editor`` of
    ``"none"``) makes the column read-only. ``is_row_header=True`` marks the
    column that identifies the row (rendered as ``<th role="rowheader">`` so the
    screen reader speaks it when you move *between* rows); a grid should have at
    most one, and it is read-only by convention (the channel number, an id).
    """

    name: str
    label: str
    editor: str = TEXT
    choices: list[str] = field(default_factory=list)
    editable: bool = True
    # Numeric bounds for slider / stepper (ignored by the other editors).
    min: float | None = None
    max: float | None = None
    step: float | None = None
    is_row_header: bool = False

    def __post_init__(self) -> None:
        if self.editor not in EDITORS:
            raise ValueError(
                f"Column {self.name!r}: unknown editor {self.editor!r}; "
                f"expected one of {sorted(EDITORS)}"
            )
        if self.is_row_header or self.editor == NONE:
            self.editable = False


@dataclass
class SetResult:
    """What a model returns from :meth:`GridModel.set_cell`.

    ``ok`` says whether the edit was accepted. ``display`` is the authoritative
    text to show in the cell afterwards (the model may have normalized it).
    ``message`` is announced to the screen reader either way — a confirmation on
    success, the reason on failure (so the user always hears *why* nothing
    changed, never silence).
    """

    ok: bool
    display: str = ""
    message: str = ""


class GridModel:
    """Subclass this and implement the data access for your grid.

    Row indexes are absolute and 0-based across the whole dataset (not the
    current page), so a model backed by 10,000 channels works unchanged whether
    the grid pages or not. Column access is by ``name``.
    """

    # -- shape -------------------------------------------------------------

    def columns(self) -> list[Column]:
        raise NotImplementedError

    def row_count(self) -> int:
        """Total number of rows across the whole dataset."""
        raise NotImplementedError

    # -- reading -----------------------------------------------------------

    def display(self, row: int, column: str) -> str:
        """Text shown in the cell (and read by the screen reader)."""
        raise NotImplementedError

    def edit_value(self, row: int, column: str) -> str:
        """Initial value for the in-cell editor.

        Defaults to :meth:`display`. Override when the editor needs a different
        form than the displayed text — a checkbox wants ``"true"``/``"false"``,
        a slider/stepper wants a bare number, even if the cell shows ``"Yes"`` or
        ``"146.520 MHz"``.
        """
        return self.display(row, column)

    def is_editable(self, row: int, column: str) -> bool:
        """Whether this specific cell can be edited (default: the column's flag).

        Override to make editability depend on the row (e.g. an immutable
        channel, or a field that only applies when another field is set).
        """
        col = self._column(column)
        return col.editable

    def choices(self, row: int, column: str) -> list[str]:
        """Combo choices for this cell (default: the column's static list).

        Override for choices that depend on the row (e.g. tone values that only
        make sense for the current tone mode).
        """
        return list(self._column(column).choices)

    def row_label(self, row: int) -> str:
        """Accessible name for the whole row, used when announcing selection
        and in context menus. Defaults to the row-header cell's text, else the
        1-based row number."""
        for col in self.columns():
            if col.is_row_header:
                return self.display(row, col.name)
        return str(row + 1)

    # -- writing -----------------------------------------------------------

    def set_cell(self, row: int, column: str, value: str) -> SetResult:
        """Apply an edit. Return a :class:`SetResult` (validate/normalize here)."""
        raise NotImplementedError

    def delete_rows(self, rows: list[int]) -> SetResult:
        """Delete the given rows. Default: not supported."""
        return SetResult(False, message="Delete is not supported here.")

    # -- helpers -----------------------------------------------------------

    def _column(self, name: str) -> Column:
        for col in self.columns():
            if col.name == name:
                return col
        raise KeyError(name)
