"""Integration tests for OpenProject MCP Server."""
import pytest
import json
import asyncio
from unittest.mock import AsyncMock, patch
from src.mcp_server import (
    openproject_client, 
    get_users, 
    assign_work_package_by_email,
    get_project_members,
    get_work_package_types,
    get_work_package_statuses,
    get_priorities,
    create_work_package_dependency
)


class TestOpenProjectIntegration:
    """Test complete integration workflows."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup mock client for all tests."""
        self.original_client = openproject_client
        
    def teardown(self):
        """Restore original client."""
        pass

    @pytest.mark.asyncio
    async def test_user_workflow(self):
        """Test complete user management workflow."""
        # Mock user data
        mock_users = [
            {
                "id": 1,
                "name": "John Doe",
                "firstName": "John",
                "lastName": "Doe",
                "email": "john@example.com",
                "login": "john.doe",
                "status": "active",
                "admin": False
            },
            {
                "id": 2,
                "name": "Jane Smith",
                "firstName": "Jane",
                "lastName": "Smith",
                "email": "jane@example.com",
                "login": "jane.smith",
                "status": "active",
                "admin": True
            }
        ]
        
        with patch.object(openproject_client, 'get_users', new_callable=AsyncMock) as mock_get_users:
            mock_get_users.return_value = mock_users
            
            # Test get_users without filter
            result = await get_users()
            result_data = json.loads(result)
            
            assert result_data["success"] is True
            assert len(result_data["users"]) == 2
            assert result_data["users"][0]["name"] == "John Doe"
            assert result_data["users"][1]["admin"] is True
            
            # Test get_users with email filter
            mock_get_users.return_value = [mock_users[0]]  # Only John
            result = await get_users("john@example.com")
            result_data = json.loads(result)
            
            assert result_data["success"] is True
            assert len(result_data["users"]) == 1
            assert result_data["users"][0]["email"] == "john@example.com"

    @pytest.mark.asyncio
    async def test_assign_work_package_by_email_workflow(self):
        """Test work package assignment by email workflow."""
        # Mock user and work package data
        mock_user = {
            "id": 1,
            "name": "John Doe",
            "email": "john@example.com"
        }
        
        mock_updated_wp = {
            "id": 123,
            "subject": "Test Work Package",
            "_links": {
                "assignee": {
                    "href": "/api/v3/users/1",
                    "title": "John Doe"
                }
            }
        }
        
        with patch.object(openproject_client, 'get_user_by_email', new_callable=AsyncMock) as mock_get_user, \
             patch.object(openproject_client, 'update_work_package', new_callable=AsyncMock) as mock_update_wp:
            
            mock_get_user.return_value = mock_user
            mock_update_wp.return_value = mock_updated_wp
            
            # Test successful assignment
            result = await assign_work_package_by_email(123, "john@example.com")
            result_data = json.loads(result)
            
            assert result_data["success"] is True
            assert result_data["work_package"]["assignee"]["email"] == "john@example.com"
            
            # Verify the API calls
            mock_get_user.assert_called_once_with("john@example.com")
            mock_update_wp.assert_called_once_with(123, {
                "_links": {
                    "assignee": {
                        "href": "/api/v3/users/1"
                    }
                }
            })

    @pytest.mark.asyncio
    async def test_assign_work_package_user_not_found(self):
        """Test work package assignment when user is not found."""
        with patch.object(openproject_client, 'get_user_by_email', new_callable=AsyncMock) as mock_get_user:
            mock_get_user.return_value = None  # User not found
            
            result = await assign_work_package_by_email(123, "nonexistent@example.com")
            result_data = json.loads(result)
            
            assert result_data["success"] is False
            assert "not found" in result_data["error"]

    @pytest.mark.asyncio
    async def test_project_members_workflow(self):
        """Test project members retrieval workflow."""
        mock_memberships = [
            {
                "id": 1,
                "_links": {
                    "principal": {
                        "href": "/api/v3/users/1",
                        "title": "John Doe"
                    },
                    "roles": [
                        {"title": "Manager"},
                        {"title": "Developer"}
                    ]
                },
                "createdAt": "2024-01-01T00:00:00Z"
            },
            {
                "id": 2,
                "_links": {
                    "principal": {
                        "href": "/api/v3/users/2",
                        "title": "Jane Smith"
                    },
                    "roles": [
                        {"title": "Tester"}
                    ]
                },
                "createdAt": "2024-01-02T00:00:00Z"
            }
        ]
        
        with patch.object(openproject_client, 'get_project_memberships', new_callable=AsyncMock) as mock_get_members:
            mock_get_members.return_value = mock_memberships
            
            result = await get_project_members(1)
            result_data = json.loads(result)
            
            assert result_data["success"] is True
            assert len(result_data["members"]) == 2
            assert result_data["members"][0]["user"]["title"] == "John Doe"
            assert len(result_data["members"][0]["roles"]) == 2
            assert "Manager" in result_data["members"][0]["roles"]

    @pytest.mark.asyncio
    async def test_configuration_loading_workflow(self):
        """Test dynamic configuration loading workflow."""
        mock_types = [
            {"id": 1, "name": "Task", "isDefault": True},
            {"id": 2, "name": "Bug", "isDefault": False},
            {"id": 3, "name": "Feature", "isMilestone": False}
        ]
        
        mock_statuses = [
            {"id": 1, "name": "New", "isDefault": True, "isClosed": False},
            {"id": 2, "name": "In Progress", "isDefault": False, "isClosed": False},
            {"id": 3, "name": "Closed", "isDefault": False, "isClosed": True}
        ]
        
        mock_priorities = [
            {"id": 1, "name": "Low", "isDefault": False},
            {"id": 2, "name": "Normal", "isDefault": True},
            {"id": 3, "name": "High", "isDefault": False}
        ]
        
        with patch.object(openproject_client, 'get_work_package_types', new_callable=AsyncMock) as mock_get_types, \
             patch.object(openproject_client, 'get_work_package_statuses', new_callable=AsyncMock) as mock_get_statuses, \
             patch.object(openproject_client, 'get_priorities', new_callable=AsyncMock) as mock_get_priorities:
            
            mock_get_types.return_value = mock_types
            mock_get_statuses.return_value = mock_statuses
            mock_get_priorities.return_value = mock_priorities
            
            # Test work package types
            result = await get_work_package_types()
            result_data = json.loads(result)
            assert result_data["success"] is True
            assert len(result_data["types"]) == 3
            assert any(t["is_default"] for t in result_data["types"])
            
            # Test work package statuses
            result = await get_work_package_statuses()
            result_data = json.loads(result)
            assert result_data["success"] is True
            assert len(result_data["statuses"]) == 3
            assert any(s["is_closed"] for s in result_data["statuses"])
            
            # Test priorities
            result = await get_priorities()
            result_data = json.loads(result)
            assert result_data["success"] is True
            assert len(result_data["priorities"]) == 3
            assert any(p["is_default"] for p in result_data["priorities"])

    @pytest.mark.asyncio
    async def test_work_package_dependency_creation_workflow(self):
        """Test complete work package dependency creation workflow."""
        mock_relation_result = {
            "id": 456,
            "type": "follows",
            "reverseType": "precedes",
            "description": "Task B follows Task A",
            "lag": 2,
            "_links": {
                "from": {
                    "href": "/api/v3/work_packages/1",
                    "title": "Task A"
                },
                "to": {
                    "href": "/api/v3/work_packages/2",
                    "title": "Task B"
                }
            }
        }
        
        with patch.object(openproject_client, 'create_work_package_relation', new_callable=AsyncMock) as mock_create_relation:
            mock_create_relation.return_value = mock_relation_result
            
            # Test successful relation creation
            result = await create_work_package_dependency(
                from_work_package_id=1,
                to_work_package_id=2,
                relation_type="follows",
                description="Task B follows Task A",
                lag=2
            )
            
            result_data = json.loads(result)
            assert result_data["success"] is True
            assert result_data["relation"]["id"] == 456
            assert result_data["relation"]["relation_type"] == "follows"
            assert result_data["relation"]["lag"] == 2
            
            # Verify API call
            mock_create_relation.assert_called_once_with(1, 2, "follows", "Task B follows Task A", 2)

    @pytest.mark.asyncio
    async def test_validation_error_handling(self):
        """Test validation error handling in integration workflow."""
        # Test invalid work package dependency (self-relation)
        result = await create_work_package_dependency(
            from_work_package_id=1,
            to_work_package_id=1  # Same as from
        )
        
        result_data = json.loads(result)
        assert result_data["success"] is False
        assert result_data["error"] == "Validation error"
        assert any("Work package cannot have a relation with itself" in detail["message"] 
                  for detail in result_data["details"])

    @pytest.mark.asyncio
    async def test_api_error_handling(self):
        """Test OpenProject API error handling in integration workflow."""
        from src.mcp_server import OpenProjectAPIError
        
        with patch.object(openproject_client, 'get_users', new_callable=AsyncMock) as mock_get_users:
            # Mock API error
            mock_get_users.side_effect = OpenProjectAPIError(
                "Unauthorized access",
                status_code=401,
                response_data={"error": "Invalid API key"}
            )
            
            result = await get_users()
            result_data = json.loads(result)
            
            assert result_data["success"] is False
            assert "OpenProject API error" in result_data["error"]
            assert "Unauthorized access" in result_data["error"]

    @pytest.mark.asyncio
    async def test_input_validation_edge_cases(self):
        """Test edge cases for input validation."""
        # Test empty email
        result = await assign_work_package_by_email(123, "")
        result_data = json.loads(result)
        assert result_data["success"] is False
        assert "Valid email address is required" in result_data["error"]
        
        # Test invalid email format
        result = await assign_work_package_by_email(123, "invalid-email")
        result_data = json.loads(result)
        assert result_data["success"] is False
        assert "Valid email address is required" in result_data["error"]
        
        # Test zero work package ID
        result = await get_project_members(0)
        result_data = json.loads(result)
        assert result_data["success"] is False
        assert "Project ID must be a positive integer" in result_data["error"]
