"""``AccessibleGrid`` — an editable, screen-reader-first data grid widget.

It owns an :class:`~wx_accessible_webview.AccessibleWebView`, renders a
:class:`~wx_accessible_grid.model.GridModel` into it as an ARIA grid, installs
the runtime behaviour, and brokers every edit/select/delete/page request between
the page and your model. Add :attr:`control` to a sizer like any wx window.

By default the whole grid renders at once (no pagination) for Excel-style
navigation; ``aria-rowcount`` still tells the screen reader "row N of many".
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable

from wx_accessible_webview import DEFAULT_STYLES, AccessibleWebView

from wx_accessible_grid.assets import GRID_CSS, runtime_js
from wx_accessible_grid.model import GridModel
from wx_accessible_grid.render import render_grid, render_rows


@dataclass
class ContextMenuItem:
    """One entry in a grid context menu: a label and a zero-argument callback."""

    label: str
    callback: Callable[[], None]


class AccessibleGrid:
    """An accessible, editable grid backed by a :class:`GridModel`.

    Parameters
    ----------
    parent:
        Parent wx window.
    model:
        The :class:`GridModel` providing data, validation, and persistence.
    label:
        Accessible name for the grid (its caption and ``aria-label``).
    page_size:
        Rows rendered per page; ``0`` (the default) renders the whole grid on one
        page with no pagination — Excel-style navigation expects the full dataset
        in the DOM. A positive value still renders in chunks, but arrow/Tab
        navigation no longer crosses chunk boundaries, so leave it at 0.
    handler_name:
        WebView bridge handler name (only change it if you host two grids that
        must not collide).
    on_context:
        Optional ``on_context(row: int, column: str)`` callback fired when the
        user presses the context-menu key (Shift+F10 / Applications) on a cell —
        build items and call :meth:`show_context_menu` here, or open a dialog.
    on_navigate:
        Optional ``on_navigate(row: int, column: str)`` fired (throttled) whenever
        the active cell changes.
    on_activate:
        Optional ``on_activate(row: int, column: str)`` fired when Enter is pressed
        on a non-editable cell (a row "open" hook).
    on_selection_changed:
        Optional ``on_selection_changed(rows: list[int])`` fired when row selection
        changes.
    on_edit_committed:
        Optional ``on_edit_committed(row: int, column: str, display: str)`` fired
        after the model accepts an edit (the authoritative display value).
    description:
        Optional sentence appended to the caption (usage hint).
    """

    def __init__(
        self,
        parent,
        model: GridModel,
        *,
        label: str = "Data grid",
        page_size: int = 0,
        handler_name: str = "wag",
        on_context=None,
        on_navigate=None,
        on_activate=None,
        on_selection_changed=None,
        on_edit_committed=None,
        description: str = "",
        row_select: bool = False,
    ) -> None:
        self.model = model
        self._label = label
        self._page_size = max(0, int(page_size))
        self._handler = handler_name
        self._on_context = on_context
        self._on_navigate = on_navigate
        self._on_activate = on_activate
        self._on_selection_changed = on_selection_changed
        self._on_edit_committed = on_edit_committed
        self._description = description
        self._row_select = bool(row_select)
        self._page = 0
        self._selected: set[int] = set()  # absolute row indexes
        self._active: tuple[int, int] = (0, 0)  # (row, col index) of the active cell
        self._installed = False

        self._awv = AccessibleWebView(
            parent,
            title=label,
            lang="en",
            live_region=False,  # we announce via the assertive status region
            handler_name=handler_name,
            on_message=self._on_message,
            styles=DEFAULT_STYLES + GRID_CSS,
            initial_html=self._render_page(),
        )

        if self._awv.using_webview:
            import wx
            import wx.html2 as webview

            self._wx = wx
            # Install the runtime + column metadata once the page is ready. The
            # library's own loaded handler runs too; CallAfter sequences ours
            # after it so the page is fully live.
            self._awv.view.Bind(webview.EVT_WEBVIEW_LOADED, self._on_loaded)

    # -- public API --------------------------------------------------------

    @property
    def control(self):
        """The underlying wx control — add this to a sizer."""
        return self._awv.control

    @property
    def using_webview(self) -> bool:
        return self._awv.using_webview

    def focus(self) -> None:
        """Put keyboard focus INTO the grid: focus the table and place the cursor
        on the last active cell (the first cell to start), so arrows and Tab work
        immediately. Focuses the table itself, not the webview wrapper, or the
        keydown handler's focus gate would bail and the grid would feel dead."""
        self._awv.focus()
        if self._awv.using_webview:
            r, c = self._active
            self._awv.run_js(f"window.__wag&&window.__wag.enterGrid({r},{c});")

    def selected_rows(self) -> list[int]:
        """Absolute indexes of the currently selected rows, ascending.

        This is what bulk operations act on — move, reorder, delete a region,
        edit a range. The host reads it (e.g. from an ``on_context`` handler or a
        toolbar button), performs the operation via the model, then calls
        :meth:`refresh`."""
        return sorted(self._selected)

    def refresh(self) -> None:
        """Re-render the current page from the model (after external changes)."""
        self._render_and_show(focus_row=self._first(), focus_col=0)

    def announce(self, text: str) -> None:
        self._awv.status(text)

    def get_active_cell(self) -> tuple[int, int]:
        """The (row, column-index) of the cell the user is currently on."""
        return self._active

    def focus_cell(self, row: int, col: int = 0) -> None:
        """Move the active cell to an absolute (row, column index)."""
        self._active = (row, col)
        if self._awv.using_webview:
            self._awv.run_js(f"window.__wag&&window.__wag.focusCell({row},{col});")

    def edit_cell(self, row: int, col: int = 0) -> None:
        """Open the in-cell editor on an absolute (row, column index)."""
        if self._awv.using_webview:
            self._awv.run_js(f"window.__wag&&window.__wag.editCell({row},{col});")

    def show_context_menu(self, items: list[ContextMenuItem]) -> None:
        """Pop up a native ``wx.Menu`` of :class:`ContextMenuItem` on the grid and
        return focus to the cell afterwards. Call this from your ``on_context``
        handler. Native menus read correctly in NVDA/JAWS and arrow-navigate for
        free, which is why we use one instead of an in-page menu."""
        if not self._awv.using_webview:
            return
        import wx

        menu = wx.Menu()
        handlers: dict[int, Callable[[], None]] = {}
        for item in items:
            mi = menu.Append(wx.ID_ANY, item.label)
            handlers[mi.GetId()] = item.callback
        self.control.Bind(wx.EVT_MENU, lambda e: (handlers.get(e.GetId()) or (lambda: None))())
        self.control.PopupMenu(menu)
        menu.Destroy()
        wx.CallAfter(self.focus)

    def default_context_items(self, row: int, col: int) -> list[ContextMenuItem]:
        """A ready-made Edit + Delete menu for hosts that just want the basics."""
        return [
            ContextMenuItem("Edit (F2)", lambda: self.edit_cell(row, col)),
            ContextMenuItem("Delete (Del)", lambda: self._delete_rows([row])),
        ]

    # -- paging math -------------------------------------------------------

    def _total(self) -> int:
        return self.model.row_count()

    def _size(self) -> int:
        return self._page_size or max(1, self._total())

    def _pages(self) -> int:
        return max(1, math.ceil(self._total() / self._size())) if self._total() else 1

    def _first(self) -> int:
        return self._page * self._size()

    def _last(self) -> int:
        return min(self._total() - 1, self._first() + self._size() - 1)

    # -- rendering ---------------------------------------------------------

    def _render_page(self) -> str:
        total = self._total()
        if total == 0:
            return f"<h1>{self._label}</h1><p>No rows.</p>"
        self._page = min(self._page, self._pages() - 1)
        desc = self._description
        if self._page_size and self._pages() > 1:
            desc = (
                f"Showing rows {self._first() + 1} to {self._last() + 1} of {total}, "
                f"page {self._page + 1} of {self._pages()}. {desc}"
            ).strip()
        return render_grid(
            self.model,
            label=self._label,
            first=self._first(),
            last=self._last(),
            selected=self._selected,
            description=desc,
            row_select=self._row_select,
        )

    def _render_and_show(self, *, focus_row: int, focus_col: int) -> None:
        """Full re-render (rebuilds the whole table). Used by refresh()."""
        self._awv.set_content(self._render_page())
        if self._awv.using_webview:
            self._push_columns()
            self._awv.run_js(f"window.__wag&&window.__wag.focusCell({focus_row},{focus_col});")

    def _swap_rows(self, *, focus_row: int, focus_col: int) -> None:
        """Replace only the tbody (paging / delete) so the table — and thus
        keyboard focus and the screen reader's focus mode — survives."""
        if not self._awv.using_webview:
            self._render_and_show(focus_row=focus_row, focus_col=focus_col)
            return
        import json

        html = render_rows(
            self.model, self._first(), self._last(), self._selected, row_select=self._row_select
        )
        rowcount = self._total() + 1
        self._awv.run_js(
            f"window.__wag&&window.__wag.setRows("
            f"{json.dumps(html)},{focus_row},{focus_col},{rowcount});"
        )

    def _push_columns(self) -> None:
        import json

        meta = [
            {
                "editor": c.editor,
                "choices": c.choices,
                "min": c.min,
                "max": c.max,
                "step": c.step,
                "label": c.label,
                "editable": c.editable,
            }
            for c in self.model.columns()
        ]
        self._awv.run_js(f"window.__wag&&window.__wag.setColumns({json.dumps(meta)});")

    def _on_loaded(self, _event) -> None:
        if self._installed:
            return
        self._installed = True

        def install():
            self._awv.run_js(runtime_js(self._handler))
            self._push_columns()
            # The grid is the live surface: drop the user straight into it on the
            # first cell so arrows and Tab work immediately, no tabbing onto the
            # table. (Mirrors the spike's auto-enter; safe because the grid is the
            # content the host just added.)
            if self.model.row_count():
                self._awv.focus()
                self._awv.run_js(f"window.__wag&&window.__wag.enterGrid({self._first()},0);")

        self._wx.CallAfter(install)

    # -- bridge ------------------------------------------------------------

    def _col_name(self, col_index: int) -> str:
        return self.model.columns()[col_index].name

    def _on_message(self, data: dict) -> None:
        if data.get("type") != "wag":
            return
        action = data.get("action")
        if action == "edit":
            self._handle_edit(data)
        elif action == "select":
            self._handle_select(data)
        elif action == "delete":
            self._delete_rows([int(r) for r in data.get("rows", [])])
        elif action == "navigate":
            self._handle_navigate(data)
        elif action == "activate":
            self._handle_activate(data)
        elif action == "page":
            self._handle_page(data)
        elif action == "context":
            self._handle_context(data)

    def _handle_edit(self, data: dict) -> None:
        row = int(data["row"])
        col = int(data["col"])
        name = self._col_name(col)
        result = self.model.set_cell(row, name, str(data.get("value", "")))
        if result.ok:
            display = result.display or self.model.display(row, name)
            self._js_setcell(row, col, display, result.message)
            if self._on_edit_committed is not None:
                self._on_edit_committed(row, name, display)
        else:
            self._js_editfailed(row, col, result.message or "Invalid value")

    def _handle_select(self, data: dict) -> None:
        row = int(data["row"])
        if data.get("selected"):
            self._selected.add(row)
        else:
            self._selected.discard(row)
        if self._on_selection_changed is not None:
            self._on_selection_changed(self.selected_rows())

    def _handle_navigate(self, data: dict) -> None:
        row, col = int(data["row"]), int(data.get("col", 0))
        self._active = (row, col)
        if self._on_navigate is not None:
            self._on_navigate(row, self._col_name(col))

    def _handle_activate(self, data: dict) -> None:
        if self._on_activate is not None:
            self._on_activate(int(data["row"]), self._col_name(int(data.get("col", 0))))

    def _delete_rows(self, rows: list[int]) -> None:
        rows = sorted({int(r) for r in rows})
        if not rows:
            return
        result = self.model.delete_rows(rows)
        if not result.ok:
            self.announce(result.message or "Delete failed")
            return
        self._selected.clear()
        focus = min(rows[0], max(0, self._total() - 1))
        self._page = (focus // self._size()) if self._size() else 0
        self._swap_rows(focus_row=focus, focus_col=0)
        if self._on_selection_changed is not None:
            self._on_selection_changed([])
        self.announce(result.message or f"Deleted {len(rows)} row(s)")

    def _handle_page(self, data: dict) -> None:
        if not self._page_size:
            return
        direction = data.get("dir")
        col = int(data.get("col", 0))
        if direction in ("next", "prev"):
            target_page = self._page + (1 if direction == "next" else -1)
        elif direction == "first":
            target_page = 0
        elif direction == "last":
            target_page = self._pages() - 1
        else:
            return
        if target_page < 0:
            self.announce("First page")
            return
        if target_page > self._pages() - 1:
            self.announce("Last page")
            return
        self._page = target_page
        # Continue in the natural direction: top of the new page going down,
        # bottom going up.
        focus_row = self._first() if direction != "prev" else self._last()
        self._swap_rows(focus_row=focus_row, focus_col=col)
        self.announce(
            f"Rows {self._first() + 1} to {self._last() + 1} of {self._total()}, "
            f"page {self._page + 1} of {self._pages()}"
        )

    def _handle_context(self, data: dict) -> None:
        if self._on_context is None:
            return
        row = int(data["row"])
        self._on_context(row, self._col_name(int(data.get("col", 0))))

    # -- js calls ----------------------------------------------------------

    def _js_setcell(self, row: int, col: int, display: str, message: str = "") -> None:
        import json

        self._awv.run_js(
            f"window.__wag&&window.__wag.setCell("
            f"{row},{col},{json.dumps(display)},{json.dumps(message)});"
        )

    def _js_editfailed(self, row: int, col: int, message: str) -> None:
        import json

        self._awv.run_js(
            f"window.__wag&&window.__wag.editFailed({row},{col},{json.dumps(message)});"
        )
