"""Gooclaim: a search hit says which page(s) its passage came from."""

from airweave.domains.search.adapters.vector_db.tests.test_vespa_client_name_substring import (
    _make_client,
)


def _fields(**extra):
    return {
        "data_sources_system_metadata_source_name": "gooclaim_upload",
        "data_sources_system_metadata_entity_type": "GooclaimUploadFileEntity",
        "data_sources_system_metadata_chunk_index": 3,
        **extra,
    }


def test_a_hit_carries_its_pages():
    client, _ = _make_client()
    meta = client._extract_system_metadata(
        _fields(
            data_sources_system_metadata_page_start=4,
            data_sources_system_metadata_page_end=5,
        ),
        "doc__chunk_3",
    )
    assert (meta.page_start, meta.page_end) == (4, 5)


def test_a_hit_from_before_pages_says_unknown_never_page_one():
    client, _ = _make_client()
    meta = client._extract_system_metadata(_fields(), "doc__chunk_3")
    assert (meta.page_start, meta.page_end) == (None, None)
