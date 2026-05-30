"""Tests for work package activities and reactions in OpenProject MCP Server."""
import pytest
import json
from unittest.mock import AsyncMock, patch
from src.mcp_server import (
    openproject_client, 
    get_work_package_activities, 
    create_work_package_comment,
    toggle_reaction
)

class TestWorkPackageActivities:
    """Test activities and reactions tools."""

    @pytest.mark.asyncio
    async def test_get_work_package_activities_success(self):
        """Test successful retrieval of activities."""
        mock_activities = [
            {
                "id": 101,
                "version": 1,
                "comment": {"raw": "First comment"},
                "createdAt": "2024-01-01T10:00:00Z",
                "updatedAt": "2024-01-01T10:00:00Z",
                "_links": {"author": {"title": "User A"}},
                "_embedded": {"emojiReactions": [{"emoji": "thumbs_up", "count": 1, "_links": {"reactingUsers": [{"title": "User B"}]}}]}
            }
        ]
        
        with patch.object(openproject_client, 'get_work_package_activities', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_activities
            
            result = await get_work_package_activities(1, offset=1, page_size=10)
            result_data = json.loads(result)
            
            assert result_data["success"] is True
            assert len(result_data["activities"]) == 1
            assert result_data["activities"][0]["comment"] == "First comment"
            assert result_data["activities"][0]["author"] == "User A"
            assert result_data["activities"][0]["reactions"][0]["emoji"] == "thumbs_up"

    @pytest.mark.asyncio
    async def test_create_work_package_comment_success(self):
        """Test successful comment creation."""
        mock_result = {
            "id": 102,
            "comment": {"raw": "New comment"},
            "createdAt": "2024-01-01T11:00:00Z"
        }
        
        with patch.object(openproject_client, 'create_work_package_comment', new_callable=AsyncMock) as mock_create:
            mock_create.return_value = mock_result
            
            result = await create_work_package_comment(1, "New comment")
            result_data = json.loads(result)
            
            assert result_data["success"] is True
            assert result_data["activity"]["comment"] == "New comment"

    @pytest.mark.asyncio
    async def test_toggle_reaction_success(self):
        """Test successful reaction toggling."""
        mock_result = {
            "_embedded": {
                "elements": [{"emoji": "heart", "count": 1}]
            }
        }
        
        with patch.object(openproject_client, 'toggle_reaction', new_callable=AsyncMock) as mock_toggle:
            mock_toggle.return_value = mock_result
            
            result = await toggle_reaction(101, "heart")
            result_data = json.loads(result)
            
            assert result_data["success"] is True
            assert result_data["reactions"][0]["emoji"] == "heart"
