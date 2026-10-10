"""Gooclaim: where each page of a converted document begins.

A passage cited to staff names its page ("Policy wording · page 4"). OCR reads
a document page by page; the converter used to join the pages into one text
and the page was lost. Pages are now joined by ``PAGE_BREAK`` (a form feed —
the separator text extractors such as pdftotext use), every page kept, an
empty one too, so the count never drifts. The chunker's offsets then say which
page(s) a chunk spans, and the form feeds are taken out of the chunk text.
"""

from typing import Optional, Tuple

PAGE_BREAK = "\f"
#: Pages joined with blank lines around the break, so markdown blocks never merge.
PAGE_JOIN = f"\n\n{PAGE_BREAK}\n\n"
_BLANK = frozenset(" \t\r\n" + PAGE_BREAK)


def pages_of(
    text: str, start: Optional[int], end: Optional[int]
) -> Tuple[Optional[int], Optional[int]]:
    """1-based first and last page of ``text[start:end]``.

    ``(None, None)`` when the text has no page breaks or the chunk has no
    offsets — an unknown page, never a guessed one.
    """
    if PAGE_BREAK not in text or start is None or end is None:
        return None, None
    # Blank space and breaks at the edges are not on a page: a chunk that ends
    # on the blank lines after a page's last word is on that page alone.
    while start < end and text[start] in _BLANK:
        start += 1
    while end > start and text[end - 1] in _BLANK:
        end -= 1
    if start == end:  # nothing but blank space: on no page
        return None, None
    first = 1 + text.count(PAGE_BREAK, 0, start)
    last = 1 + text.count(PAGE_BREAK, 0, end - 1)
    return first, last


def without_breaks(text: str) -> str:
    """The text a reader sees — no page-break characters."""
    return text.replace(PAGE_BREAK, "")
