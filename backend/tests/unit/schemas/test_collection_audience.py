"""Gooclaim: a collection says who its documents may answer.

Members (the default, the Portal's library) or staff (Orion only). Fixed at
creation.
"""

import pytest
from pydantic import ValidationError

from airweave import schemas
from airweave.models.collection import Collection


def test_a_new_collection_is_the_members_library_unless_it_says_staff():
    assert schemas.CollectionCreate(name="Policy wordings").audience == "members"
    assert schemas.CollectionCreate(name="Staff SOPs", audience="staff").audience == "staff"
    with pytest.raises(ValidationError):
        schemas.CollectionCreate(name="Anything goes", audience="everyone")


def test_the_audience_is_set_when_made_and_never_updated():
    assert "audience" not in schemas.CollectionUpdate.model_fields


def test_the_model_defaults_and_the_database_refuses_other_words():
    assert Collection(name="x", readable_id="x").audience in (None, "members")
    column = Collection.__table__.c.audience
    assert column.server_default.arg == "members"
    checks = [c for c in Collection.__table__.constraints if c.name == "ck_collection_audience"]
    assert checks and "'members', 'staff'" in str(checks[0].sqltext)


def test_every_collection_read_says_its_audience():
    """gooclaim-datasources-mcp decides who may search a collection from this."""
    assert schemas.Collection.model_fields["audience"].default == "members"
    assert schemas.Collection.model_fields["audience"].annotation.__args__ == ("members", "staff")
