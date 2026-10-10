"""Gooclaim: a passage knows its page — from OCR, through the chunker, to search.

Mistral OCR reads page by page; the pages are joined by a page break that the
chunker's offsets are counted against, and that never reaches the passage text.
"""

from types import SimpleNamespace

from airweave.domains.ocr.mistral.converter import MistralOCR
from airweave.domains.ocr.mistral.ocr_client import MistralOcrClient
from airweave.domains.ocr.pages import PAGE_BREAK, PAGE_JOIN, pages_of, without_breaks
from airweave.platform.chunkers.semantic import SemanticChunker


def test_a_span_is_on_the_pages_its_offsets_fall_on():
    text = PAGE_JOIN.join(["one", "two", "three"])
    two = text.index("two")
    three = text.index("three")
    assert pages_of(text, 0, 3) == (1, 1)
    assert pages_of(text, two, two + 3) == (2, 2)
    assert pages_of(text, two, three + 5) == (2, 3)
    # blank lines and the break at a span's edges are on no page
    assert pages_of(text, 0, text.index(PAGE_BREAK) + 3) == (1, 1)
    assert pages_of(text, text.index(PAGE_BREAK), two + 3) == (2, 2)
    assert pages_of(text, 3, two) == (None, None)  # only blank space: on no page


def test_no_breaks_or_no_offsets_is_an_unknown_page_never_page_one():
    assert pages_of("a document with no pages", 0, 5) == (None, None)
    assert pages_of(PAGE_JOIN.join(["a", "b"]), None, 4) == (None, None)


def test_a_reader_never_sees_the_break():
    assert without_breaks(PAGE_JOIN.join(["Clause 4", "waiting period"])) == (
        "Clause 4\n\n\n\nwaiting period"
    )


def test_ocr_keeps_every_page_in_place_an_empty_one_too():
    resp = {"pages": [{"markdown": "Cover"}, {"markdown": ""}, {"markdown": "Clause 4"}]}
    text = MistralOcrClient._extract_markdown(resp, "policy.pdf")
    assert text is not None
    assert text.split(PAGE_JOIN) == ["Cover", "", "Clause 4"]
    at = text.index("Clause 4")
    assert pages_of(text, at, at + 8) == (3, 3)  # not 2: the blank page still counts


def test_sdk_page_objects_read_the_same_and_an_all_empty_document_is_empty():
    pages = [SimpleNamespace(markdown="A"), SimpleNamespace(markdown="B")]
    assert (
        MistralOcrClient._extract_markdown(SimpleNamespace(pages=pages), "x")
        == "A" + PAGE_JOIN + "B"
    )
    assert MistralOcrClient._extract_markdown({"pages": [{"markdown": " "}]}, "x") == ""
    assert MistralOcrClient._extract_markdown({"pages": []}, "x") is None


def test_the_parts_of_a_split_pdf_meet_at_a_page_boundary():
    chunks = [SimpleNamespace(batch_index=0, chunk_index=i) for i in range(2)]
    group = SimpleNamespace(original_path="/tmp/policy.pdf", chunks=chunks)
    ocr = {
        (0, 0): SimpleNamespace(markdown="p1" + PAGE_JOIN + "p2", error=None),
        (0, 1): SimpleNamespace(markdown="p3", error=None),
    }
    text = MistralOCR._assemble_group(group, ocr)
    assert text is not None and text.split(PAGE_JOIN) == ["p1", "p2", "p3"]


def test_a_split_sub_chunks_offsets_count_from_the_document():
    """The safety net re-cuts an oversized chunk.

    Its pieces' offsets were within that chunk, so every page after the first
    was wrong.
    """
    piece = SimpleNamespace(text="waiting period", start_index=10, end_index=24, token_count=3)
    out = SemanticChunker._convert_chunk(
        SemanticChunker.__new__(SemanticChunker), piece, offset=1000
    )
    assert (out["start_index"], out["end_index"]) == (1010, 1024)
    whole = SemanticChunker._convert_chunk(SemanticChunker.__new__(SemanticChunker), piece)
    assert (whole["start_index"], whole["end_index"]) == (10, 24)


def test_the_safety_net_shifts_each_piece_by_where_its_chunk_began():
    chunker = object.__new__(SemanticChunker)
    big = SimpleNamespace(
        text="x" * 50,
        start_index=500,
        end_index=550,
        token_count=SemanticChunker.MAX_TOKENS_PER_CHUNK + 1,
    )
    small = SimpleNamespace(text="y", start_index=0, end_index=1, token_count=1)
    pieces = [
        SimpleNamespace(text="x" * 25, start_index=0, end_index=25, token_count=1),
        SimpleNamespace(text="x" * 25, start_index=25, end_index=50, token_count=1),
    ]
    chunker._token_chunker = SimpleNamespace(chunk_batch=lambda texts: [pieces])
    [out] = chunker._apply_safety_net_batched([[small, big]])
    assert [(c["start_index"], c["end_index"]) for c in out] == [(0, 1), (500, 525), (525, 550)]
