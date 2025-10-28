"""Interactive browse command built on Textual."""

from __future__ import annotations

import subprocess
from configparser import SectionProxy
from datetime import date
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple

from ..models import Entry
from ..utils import iter_diary_entries

TEXTUAL_AVAILABLE = False

try:  # pragma: no cover - import guard is exercised via CLI test instead
    from textual.app import App, ComposeResult
    from textual.containers import Horizontal, Vertical, VerticalScroll
    from textual.screen import ModalScreen
    from textual.widgets import (
        Button,
        Footer,
        Header,
        ListItem,
        ListView,
        Static,
    )
    from rich.text import Text

    TEXTUAL_AVAILABLE = True
except ImportError:  # pragma: no cover - import guard is exercised via CLI test
    # Textual is optional; browse_command will surface a friendly error instead.
    App = object  # type: ignore[assignment]
    ComposeResult = object  # type: ignore[assignment]
    Horizontal = Vertical = VerticalScroll = Footer = Header = Button = ListItem = ListView = Static = object  # type: ignore
    ModalScreen = object  # type: ignore[assignment]
    Text = object  # type: ignore[assignment]

DEPENDENCY_MESSAGE = (
    "The browse interface requires the optional 'textual' dependency.\n"
    "Install it with: pip install kaydet[browse]"
)


class BrowseDependencyError(RuntimeError):
    """Raised when the browse command cannot load its optional dependency."""

    def __init__(self) -> None:
        super().__init__(DEPENDENCY_MESSAGE)


def _entry_sort_key(entry: Entry) -> tuple[date, str, str]:
    day = entry.day or date.min
    identifier = entry.entry_id or ""
    return (day, entry.timestamp, identifier)


def _group_entries(entries: Sequence[Entry]) -> List[Tuple[str, List[Entry]]]:
    groups: List[Tuple[str, List[Entry]]] = []
    current_label: Optional[str] = None
    current_bucket: List[Entry] = []

    for entry in entries:
        if entry.day:
            label = entry.day.strftime("%Y-%m-%d (%A)")
        else:
            label = entry.source.stem
        if label != current_label:
            if current_bucket:
                groups.append((current_label or "", current_bucket))
            current_label = label
            current_bucket = [entry]
        else:
            current_bucket.append(entry)

    if current_bucket:
        groups.append((current_label or "", current_bucket))

    return groups


def _collect_entries(log_dir: Path, config: SectionProxy) -> List[Entry]:
    entries = list(iter_diary_entries(log_dir, config))
    entries.sort(key=_entry_sort_key, reverse=True)
    return entries


def _format_entry_summary(entry: Entry) -> str:
    headline = ""
    for line in entry.lines:
        stripped = line.strip()
        if stripped:
            headline = stripped
            break
    if not headline:
        headline = "(no text)"
    if len(headline) > 60:
        headline = f"{headline[:57]}..."
    return f"{entry.timestamp} {headline}".rstrip()


def _make_entry_text(entry: Entry, width: int | None = None) -> "Text":
    summary = _format_entry_summary(entry)
    if width is not None and width > 0:
        max_length = max(width - 2, 0)
        if len(summary) > max_length:
            if max_length <= 1:
                lead = summary[:1] if summary else ""
                summary = f"{lead}…" if lead else "…"
            else:
                summary = summary[: max_length - 1] + "…"
    return Text(summary, no_wrap=True)


def _format_entry_detail(entry: Entry) -> str:
    lines: List[str] = []
    if entry.day:
        lines.append(f"{entry.day.isoformat()} ({entry.day.strftime('%A')})")
    else:
        lines.append(entry.source.name)

    identifier = entry.entry_id or "—"
    lines.append(f"Time: {entry.timestamp}  ID: {identifier}")
    lines.append("")

    if entry.lines:
        lines.extend(entry.lines)
    else:
        lines.append("(no text)")

    if entry.metadata:
        lines.append("")
        lines.append("Metadata:")
        for key in sorted(entry.metadata):
            lines.append(f"  {key}: {entry.metadata[key]}")

    if entry.tags:
        lines.append("")
        lines.append("Tags: " + ", ".join(sorted(entry.tags)))

    return "\n".join(lines)


if TEXTUAL_AVAILABLE:

    class HeadingListItem(ListItem):
        """Non-selectable heading item for grouping entries."""

        def __init__(self, label: str) -> None:
            super().__init__(
                Static(label, classes="sidebar-heading"),
                disabled=True,
            )

    class EntryListItem(ListItem):
        """List item that carries the associated entry."""

        def __init__(self, entry: Entry, *, width: int | None = None) -> None:
            label = Static(
                _make_entry_text(entry, width),
                shrink=True,
                classes="entry-label",
            )
            label.styles.overflow = "hidden"
            label.styles.text_overflow = "ellipsis"
            label.styles.white_space = "nowrap"
            super().__init__(label)
            self.entry = entry
            self.add_class("entry-item")

    class BrowseApp(App[str]):
        """Simple Textual application for browsing diary entries."""

        CSS = """
        Screen {
            layout: vertical;
        }
        #body {
            layout: horizontal;
        }
        #sidebar-container {
            width: 38;
            min-width: 30;
            border: solid $accent;
        }
        #sidebar {
            padding: 0;
        }
        #detail {
            border: solid $accent;
        }
        .sidebar-heading {
            text-style: bold;
            padding: 0 1;
            background: $accent 20%;
            color: $text;
        }
        .entry-item>.entry-label {
            padding-left: 1;
        }
        """

        BINDINGS = [
            ("q", "app.quit", "Close"),
            ("e", "edit_entry", "Edit entry"),
            ("enter", "edit_entry", "Edit entry"),
            ("j", "cursor_down", "Down"),
            ("k", "cursor_up", "Up"),
            ("d", "delete_entry", "Delete entry"),
        ]

        def __init__(
            self,
            entries: Sequence[Entry],
            *,
            log_dir: Optional[Path] = None,
            config: Optional[SectionProxy] = None,
        ) -> None:
            super().__init__()
            self.entries = list(entries)
            self._initial_entries = list(entries)
            self.log_dir = log_dir
            self.config = config
            self.current_entry: Optional[Entry] = None
            self.detail_text: str = ""
            self.sidebar: Optional[ListView] = None
            self.sidebar_width: int | None = None

        def compose(self) -> ComposeResult:
            yield Header()
            with Horizontal(id="body"):
                with VerticalScroll(id="sidebar-container"):
                    yield Static("Entries", id="sidebar-title")
                    self.sidebar = ListView(id="sidebar")
                    yield self.sidebar
                yield Static(
                    "Select an entry to view the contents.",
                    id="detail",
                    expand=True,
                )
            yield Footer()

        def on_mount(self) -> None:
            self._reload_entries()
            self.call_after_refresh(self._update_sidebar_width, True)
            if not self.entries:
                detail = self.query_one("#detail", Static)
                detail.update("No diary entries found.")
                return

            sidebar = self.sidebar or self.query_one("#sidebar", ListView)
            self.set_focus(sidebar)
            self._select_first_entry(sidebar)

        def on_resize(self, event) -> None:  # type: ignore[override]
            self.call_after_refresh(self._update_sidebar_width, True)

        def on_list_view_highlighted(
            self, event: ListView.Highlighted
        ) -> None:
            if isinstance(event.item, EntryListItem):
                self._update_detail(event.item.entry)
            # Headings are non-focusable; cursor movement skips them.

        def action_cursor_down(self) -> None:
            self._move_cursor(1)

        def action_cursor_up(self) -> None:
            self._move_cursor(-1)

        def action_edit_entry(self) -> None:
            entry = self.current_entry
            if entry is None:
                self.console.print("Select an entry first.")
                return
            if not entry.entry_id:
                self.console.print(
                    "This entry does not have a numeric identifier."
                )
                return
            try:
                subprocess.run(
                    ["kaydet", "--edit", str(entry.entry_id)],
                    check=True,
                )
            except FileNotFoundError:
                self.console.print("Could not find the 'kaydet' executable.")
                return
            except subprocess.CalledProcessError as error:
                self.console.print(f"Editing entry failed: {error}")
                return
            self._reload_entries(focus_entry_id=entry.entry_id)

        def action_delete_entry(self) -> None:
            entry = self.current_entry
            if entry is None:
                self.console.print("Select an entry first.")
                return
            if not entry.entry_id:
                self.console.print(
                    "This entry does not have a numeric identifier."
                )
                return
            neighbor = self._neighbor_entry_id(entry.entry_id)
            self.push_screen(
                ConfirmDeleteScreen(entry.entry_id),
                lambda confirmed: self._confirm_delete_result(
                    confirmed, entry.entry_id, neighbor
                ),
            )

        def _confirm_delete_result(
            self,
            confirmed: bool,
            entry_id: str,
            focus_entry_id: Optional[str],
        ) -> None:
            if not confirmed:
                return
            try:
                subprocess.run(
                    ["kaydet", "--delete", entry_id, "--yes"],
                    check=True,
                )
            except FileNotFoundError:
                self.console.print("Could not find the 'kaydet' executable.")
                return
            except subprocess.CalledProcessError as error:
                self.console.print(f"Deletion failed: {error}")
                return
            self._reload_entries(focus_entry_id=focus_entry_id)

        def _update_detail(self, entry: Entry) -> None:
            self.current_entry = entry
            detail_text = _format_entry_detail(entry)
            detail_widget = self.query_one("#detail", Static)
            detail_widget.update(detail_text)
            self.detail_text = detail_text

        def _select_first_entry(self, sidebar: ListView) -> None:
            for index, child in enumerate(sidebar.children):
                if isinstance(child, EntryListItem):
                    sidebar.index = index
                    self._update_detail(child.entry)
                    return
            detail = self.query_one("#detail", Static)
            detail.update("No diary entries found.")
            self.current_entry = None

        def _move_cursor(self, step: int) -> None:
            sidebar = self.sidebar or self.query_one("#sidebar", ListView)
            children = list(sidebar.children)
            if not children:
                return
            current_index = sidebar.index
            if current_index is None:
                current_index = -1 if step > 0 else len(children)
            index = current_index
            while True:
                index += step
                if index < 0 or index >= len(children):
                    break
                child = children[index]
                if isinstance(child, EntryListItem):
                    sidebar.index = index
                    self._update_detail(child.entry)
                    return

        def _reload_entries(
            self, *, focus_entry_id: Optional[str] = None
        ) -> None:
            self.entries = self._load_entries()
            sidebar = self.sidebar or self.query_one("#sidebar", ListView)
            sidebar.clear()
            items = list(
                self._yield_sidebar_items(
                    self.entries, width=self.sidebar_width
                )
            )
            if items:
                for item in items:
                    sidebar.append(item)
            detail = self.query_one("#detail", Static)
            if not self.entries:
                detail.update("No diary entries found.")
                self.current_entry = None
                return
            if focus_entry_id and self._focus_entry_by_id(
                sidebar, focus_entry_id
            ):
                return
            self._select_first_entry(sidebar)

        def _update_sidebar_width(self, refresh: bool = False) -> None:
            sidebar = self.sidebar or self.query_one("#sidebar", ListView)
            if sidebar is None:
                return
            width = 0
            region = getattr(sidebar, "content_region", None)
            if region is not None:
                width = int(region.width)
            if not width:
                size = getattr(sidebar, "size", None)
                if size is not None:
                    width = int(size.width)
            if width <= 0:
                return
            if width != self.sidebar_width:
                self.sidebar_width = width
                if refresh:
                    focus_id = (
                        self.current_entry.entry_id
                        if self.current_entry and self.current_entry.entry_id
                        else None
                    )
                    self._reload_entries(focus_entry_id=focus_id)

        def _focus_entry_by_id(
            self, sidebar: ListView, entry_id: str
        ) -> bool:
            for index, child in enumerate(sidebar.children):
                if (
                    isinstance(child, EntryListItem)
                    and child.entry.entry_id == entry_id
                ):
                    sidebar.index = index
                    self._update_detail(child.entry)
                    return True
            return False

        def _yield_sidebar_items(
            self, entries: Iterable[Entry], *, width: int | None
        ) -> Iterable[ListItem]:
            for label, bucket in _group_entries(entries):
                yield HeadingListItem(label)
                for entry in bucket:
                    yield EntryListItem(entry, width=width)

        def _load_entries(self) -> List[Entry]:
            if self.log_dir and self.config:
                return _collect_entries(self.log_dir, self.config)
            if self.entries:
                return list(self.entries)
            return list(self._initial_entries)

        def _neighbor_entry_id(self, entry_id: str) -> Optional[str]:
            ids = [entry.entry_id for entry in self.entries if entry.entry_id]
            try:
                index = ids.index(entry_id)
            except ValueError:
                return None
            if index + 1 < len(ids):
                return ids[index + 1]
            if index > 0:
                return ids[index - 1]
            return None

    class ConfirmDeleteScreen(ModalScreen[bool]):
        """Modal confirmation prompt for deletions."""

        def __init__(self, entry_id: str) -> None:
            super().__init__()
            self.entry_id = entry_id

        def compose(self) -> ComposeResult:
            yield Vertical(
                Static(
                    f"Delete entry {self.entry_id}? This cannot be undone.",
                    id="confirm-message",
                ),
                Horizontal(
                    Button("Delete", id="confirm-delete", variant="error"),
                    Button("Cancel", id="cancel-delete"),
                    id="confirm-buttons",
                ),
                id="confirm-modal",
            )

        def on_button_pressed(self, event: Button.Pressed) -> None:
            self.dismiss(event.button.id == "confirm-delete")


def browse_command(
    db,  # Ignored but kept for API symmetry with other commands
    log_dir: Path,
    config: SectionProxy,
) -> None:
    """Launch the interactive browser or report missing dependencies."""
    if not TEXTUAL_AVAILABLE:
        raise BrowseDependencyError()

    entries = _collect_entries(log_dir, config)
    if not entries:
        print("No diary entries to browse yet.")
        return

    BrowseApp(entries, log_dir=log_dir, config=config).run()


__all__ = ["browse_command", "BrowseDependencyError", "TEXTUAL_AVAILABLE"]
if TEXTUAL_AVAILABLE:  # pragma: no cover - definition varies
    __all__.append("BrowseApp")
