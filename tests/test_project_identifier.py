"""Tests for project identifier generation, status validation, and project _links payloads."""
import pytest
from unittest.mock import AsyncMock

from src.utils.validation import (
    generate_identifier,
    validate_project_status,
    VALID_PROJECT_STATUSES,
)
from src.openproject_client import OpenProjectClient
from src.models import ProjectCreateRequest, ProjectUpdateRequest


class TestGenerateIdentifier:
    """generate_identifier must produce URL-safe, OpenProject-valid identifiers."""

    @pytest.mark.parametrize("name,expected", [
        ("B&R", "b-r"),
        ("FH ", "fh"),                      # trailing space must be trimmed
        ("Jenoptik_WeMatch", "jenoptik_wematch"),  # underscore preserved
        ("COLOP KG", "colop-kg"),
    ])
    def test_required_edge_cases(self, name, expected):
        assert generate_identifier(name) == expected

    def test_umlaut_transliteration(self):
        assert generate_identifier("Müller & Söhne") == "mueller-soehne"
        assert generate_identifier("Weiß") == "weiss"

    def test_collapses_and_trims_dashes(self):
        assert generate_identifier("  --A  B-- ") == "a-b"

    def test_empty_falls_back(self):
        assert generate_identifier("") == "project"
        assert generate_identifier("&&&") == "project"

    def test_result_is_url_safe(self):
        ident = generate_identifier("Projekt #42: Über/Allès!")
        assert all(c.isalnum() or c in "-_" for c in ident)
        assert ident == ident.lower()


class TestValidateProjectStatus:
    def test_all_valid_statuses_pass(self):
        for status in VALID_PROJECT_STATUSES:
            validate_project_status(status)  # should not raise

    def test_invalid_status_raises(self):
        with pytest.raises(ValueError) as exc:
            validate_project_status("active")
        assert "Invalid status" in str(exc.value)


class TestProjectLinksPayload:
    """create_project / update_project must set parent and status via HAL _links."""

    @pytest.fixture
    def client(self):
        c = OpenProjectClient()
        c._make_request = AsyncMock(return_value={"id": 1, "identifier": "x"})
        return c

    @pytest.mark.asyncio
    async def test_create_builds_links(self, client):
        req = ProjectCreateRequest(
            name="Test Sub", description="d", parent_id=10,
            status="finished", identifier="test-sub",
        )
        await client.create_project(req)
        method, url = client._make_request.call_args.args
        payload = client._make_request.call_args.kwargs["json"]
        assert (method, url) == ("POST", "/projects")
        assert payload["identifier"] == "test-sub"
        assert payload["_links"]["parent"]["href"] == "/api/v3/projects/10"
        assert payload["_links"]["status"]["href"] == "/api/v3/project_statuses/finished"

    @pytest.mark.asyncio
    async def test_create_without_optionals_has_no_links(self, client):
        await client.create_project(ProjectCreateRequest(name="Plain", description=""))
        payload = client._make_request.call_args.kwargs["json"]
        assert "_links" not in payload
        assert "identifier" not in payload

    @pytest.mark.asyncio
    async def test_update_patches_only_provided_fields(self, client):
        await client.update_project(5, ProjectUpdateRequest(status="on_track"))
        method, url = client._make_request.call_args.args
        payload = client._make_request.call_args.kwargs["json"]
        assert (method, url) == ("PATCH", "/projects/5")
        assert payload == {"_links": {"status": {"href": "/api/v3/project_statuses/on_track"}}}
