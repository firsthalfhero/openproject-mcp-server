"""Tests for get_project tool in OpenProject MCP Server."""
import pytest
import json
from unittest.mock import AsyncMock, patch
from src.mcp_server import openproject_client, get_project

class TestGetProject:
    """Test get_project tool."""

    @pytest.mark.asyncio
    async def test_get_project_success(self):
        """Test successful project retrieval with enriched attributes."""
        mock_project = {
            "id": 1,
            "name": "Test Project",
            "identifier": "test-project",
            "description": {"raw": "This is a test project"},
            "status": "active",
            "active": True,
            "public": False,
            "createdAt": "2024-01-01T00:00:00Z",
            "updatedAt": "2024-01-01T00:00:00Z",
            "customField1": "Custom Value",
            "_links": {"self": {"href": "/api/v3/projects/1"}}
        }
        
        mock_schema = {
            "customField1": {
                "type": "String",
                "name": "WorkDirectory",
                "required": False,
                "writable": True
            }
        }
        
        with patch.object(openproject_client, 'get_project', new_callable=AsyncMock) as mock_get_project, \
             patch.object(openproject_client, 'get_project_schema', new_callable=AsyncMock) as mock_get_schema:
            
            mock_get_project.return_value = mock_project
            mock_get_schema.return_value = mock_schema
            
            # Test with ID
            result = await get_project(1)
            result_data = json.loads(result)
            
            assert result_data["success"] is True
            assert result_data["project"]["id"] == 1
            assert len(result_data["project"]["attributes"]) == 1
            
            attr = result_data["project"]["attributes"][0]
            assert attr["key"] == "customField1"
            assert attr["name"] == "WorkDirectory"
            assert attr["value"] == "Custom Value"
            assert attr["type"] == "String"
            assert "url" in result_data["project"]
            
            # Test with identifier
            result = await get_project("test-project")
            result_data = json.loads(result)
            assert result_data["success"] is True
            assert result_data["project"]["identifier"] == "test-project"

    @pytest.mark.asyncio
    async def test_get_project_not_found(self):
        """Test project not found error."""
        from src.openproject_client import OpenProjectAPIError
        
        with patch.object(openproject_client, 'get_project', new_callable=AsyncMock) as mock_get_project:
            mock_get_project.side_effect = OpenProjectAPIError("Project not found", status_code=404)
            
            result = await get_project(999)
            result_data = json.loads(result)
            
            assert result_data["success"] is False
            assert "Project not found" in result_data["error"]
