"""The bounded Markdown view of the most valuable memories."""

from __future__ import annotations

from pathlib import Path

from .longterm import Category, MemoryEntry
from .store import LongTermStore

PRECIS_MAX_ENTRIES = 30
PRECIS_MAX_BYTES = 5120
TRUNCATION_MARKER = "\n…(truncated)"


def truncate_utf8(text: str, max_bytes: int) -> str:
    """Cut *text* to at most *max_bytes* UTF-8 bytes.

    Cuts on a character boundary, so the result always decodes, and
    appends a marker when anything was dropped.

    :param text: Text to bound.
    :param max_bytes: Greatest size of the result in UTF-8 bytes.
    :returns: *text* unchanged if it already fits, otherwise a shortened
        copy ending in the truncation marker.
    """
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text
    budget = max_bytes - len(TRUNCATION_MARKER.encode("utf-8"))
    if budget <= 0:
        return ""
    # errors="ignore" drops the partial character a byte-wise cut leaves
    # at the end, which is exactly the boundary this needs to respect.
    return encoded[:budget].decode("utf-8", errors="ignore") + TRUNCATION_MARKER


def render(entries: list[MemoryEntry], max_bytes: int = PRECIS_MAX_BYTES) -> str:
    """Render *entries* as Markdown bounded to *max_bytes*.

    :param entries: Entries to render, in the order they should appear.
    :param max_bytes: Greatest size of the result in UTF-8 bytes.
    :returns: Markdown, or ``""`` when there is nothing to render.
    """
    if not entries:
        return ""
    parts = []
    for entry in entries:
        category = (
            entry.category.value
            if isinstance(entry.category, Category)
            else str(entry.category)
        )
        heading = f"## {entry.title}"
        if category:
            heading += f" `{category}`"
        parts.append(f"{heading}\n{entry.content}")
    return truncate_utf8("\n\n".join(parts), max_bytes)


class Precis:
    """A Markdown file holding the top entries, refreshed on demand.

    :param store: Store to draw entries from.
    :param path: File the rendered view is written to.
    :param max_bytes: Greatest size of the file in UTF-8 bytes.
    :param max_entries: Greatest number of entries to draw.
    """

    def __init__(
        self,
        store: LongTermStore,
        path: str | Path,
        max_bytes: int = PRECIS_MAX_BYTES,
        max_entries: int = PRECIS_MAX_ENTRIES,
    ) -> None:
        self._store = store
        self.path = Path(path)
        self.max_bytes = max_bytes if max_bytes > 0 else PRECIS_MAX_BYTES
        self.max_entries = max_entries

    async def regenerate(self) -> str:
        """Rebuild the file from the store's top entries.

        :returns: The Markdown that was written.
        """
        entries = list(await self._store.list(self.max_entries))
        content = render(entries, self.max_bytes)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(content, encoding="utf-8")
        return content

    def read(self) -> str:
        """The file's contents, or ``""`` when it does not exist yet.

        :returns: The Markdown last written by :meth:`regenerate`.
        """
        if not self.path.exists():
            return ""
        return self.path.read_text(encoding="utf-8")
