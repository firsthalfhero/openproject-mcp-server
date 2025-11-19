"""FastMCP server for OpenProject integration."""
import asyncio
import json
from typing import Dict, Any, Optional
from fastmcp import FastMCP
from openproject_client import OpenProjectClient, OpenProjectAPIError
from models import ProjectCreateRequest, WorkPackageCreateRequest, WorkPackageRelationCreateRequest
from pydantic import ValidationError
from config import settings
from handlers.resources import ResourceHandler
from utils.logging import get_logger, log_tool_execution, log_error

logger = get_logger(__name__)


# Initialize FastMCP server with minimal output
import os
os.environ['FASTMCP_QUIET'] = '1'  # Try to suppress FastMCP banner
app = FastMCP("OpenProject MCP Server")

# Initialize OpenProject client and resource handler
openproject_client = OpenProjectClient()
resource_handler = ResourceHandler(openproject_client)


# Add health check tool for MCP
@app.tool()
async def health_check() -> str:
    """Health check tool to verify OpenProject MCP Server is running and connected.
    
    Returns:
        JSON string with server and OpenProject connection status
    """
    try:
        # Test OpenProject connection
        connection_result = await openproject_client.test_connection()
        
        if connection_result.get('success'):
            result = {
                "status": "healthy",
                "message": "OpenProject MCP Server is currently running",
                "openproject_connection": "connected",
                "openproject_version": connection_result.get('openproject_version', 'unknown'),
                "openproject_url": settings.openproject_url
            }
        else:
            result = {
                "status": "degraded", 
                "message": "OpenProject MCP Server is running but OpenProject connection failed",
                "openproject_connection": "failed",
                "error": connection_result.get('message', 'Unknown connection error'),
                "openproject_url": settings.openproject_url
            }
        
        log_tool_execution(logger, "health_check", {}, result)
        return json.dumps(result, indent=2)
        
    except Exception as e:
        error_result = {
            "status": "unhealthy",
            "message": "OpenProject MCP Server encountered an error",
            "error": str(e)
        }
        log_error(logger, e, {"tool": "health_check"})
        return json.dumps(error_result, indent=2)


@app.tool()
async def create_project(name: str, description: str = "") -> str:
    """Create a new project in OpenProject.
    
    Args:
        name: Project name (required)
        description: Project description (optional)
    
    Returns:
        JSON string with project creation result
    """
    try:
        # Validate input
        if not name or not name.strip():
            return json.dumps({
                "success": False,
                "error": "Project name is required and cannot be empty"
            })
        
        # Create project request
        project_request = ProjectCreateRequest(
            name=name.strip(),
            description=description.strip() if description else ""
        )
        
        # Call OpenProject API
        result = await openproject_client.create_project(project_request)
        
        return json.dumps({
            "success": True,
            "message": f"Project '{name}' created successfully",
            "project": {
                "id": result.get("id"),
                "name": result.get("name"),
                "description": result.get("description", {}).get("raw", ""),
                "status": result.get("status"),
                "url": f"{settings.openproject_url}/projects/{result.get('identifier', result.get('id'))}"
            }
        }, indent=2)
        
    except OpenProjectAPIError as e:
        return json.dumps({
            "success": False,
            "error": f"OpenProject API error: {e.message}",
            "details": e.response_data
        }, indent=2)
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": f"Unexpected error: {str(e)}"
        }, indent=2)


@app.tool()
async def create_work_package(
    project_id: int,
    subject: str,
    description: str = "",
    start_date: Optional[str] = None,
    due_date: Optional[str] = None,
    parent_id: Optional[int] = None,
    assignee_id: Optional[int] = None,
    estimated_hours: Optional[float] = None
) -> str:
    """Create a work package in a project with dates for Gantt chart.
    
    Args:
        project_id: ID of the project to create work package in
        subject: Work package title/subject
        description: Detailed description (optional)
        start_date: Start date in YYYY-MM-DD format (optional)
        due_date: Due date in YYYY-MM-DD format (optional)
        parent_id: Parent work package ID for hierarchy (optional)
        assignee_id: User ID to assign work package to (optional)
        estimated_hours: Estimated hours for completion (optional)
    
    Returns:
        JSON string with work package creation result
    """
    try:
        # Validate input
        if not subject or not subject.strip():
            return json.dumps({
                "success": False,
                "error": "Work package subject is required and cannot be empty"
            })
        
        if project_id <= 0:
            return json.dumps({
                "success": False,
                "error": "Project ID must be a positive integer"
            })
        
        # Validate date format if provided
        if start_date and not _is_valid_date_format(start_date):
            return json.dumps({
                "success": False,
                "error": "Start date must be in YYYY-MM-DD format"
            })
        
        if due_date and not _is_valid_date_format(due_date):
            return json.dumps({
                "success": False,
                "error": "Due date must be in YYYY-MM-DD format"
            })
        
        # Create work package request
        wp_request = WorkPackageCreateRequest(
            project_id=project_id,
            subject=subject.strip(),
            description=description.strip() if description else "",
            start_date=start_date,
            due_date=due_date,
            parent_id=parent_id,
            assignee_id=assignee_id,
            estimated_hours=estimated_hours
        )
        
        # Call OpenProject API
        result = await openproject_client.create_work_package(wp_request)
        
        return json.dumps({
            "success": True,
            "message": f"Work package '{subject}' created successfully",
            "work_package": {
                "id": result.get("id"),
                "subject": result.get("subject"),
                "description": result.get("description", {}).get("raw", ""),
                "project_id": project_id,
                "start_date": result.get("startDate"),
                "due_date": result.get("dueDate"),
                "status": result.get("_links", {}).get("status", {}).get("title", "Unknown"),
                "url": f"{settings.openproject_url}/work_packages/{result.get('id')}"
            }
        }, indent=2)
        
    except ValidationError as e:
        return json.dumps({
            "success": False,
            "error": "Validation error",
            "details": [{"field": err["loc"][-1], "message": err["msg"]} for err in e.errors()]
        }, indent=2)
    except OpenProjectAPIError as e:
        return json.dumps({
            "success": False,
            "error": f"OpenProject API error: {e.message}",
            "details": e.response_data
        }, indent=2)
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": f"Unexpected error: {str(e)}"
        }, indent=2)


@app.tool()
async def create_work_package_dependency(
    from_work_package_id: int,
    to_work_package_id: int,
    relation_type: str = "follows",
    description: str = "",
    lag: int = 0
) -> str:
    """Create a dependency between two work packages for Gantt chart visualization.
    
    Args:
        from_work_package_id: ID of the work package that comes first
        to_work_package_id: ID of the work package that depends on the first
        relation_type: Type of relation (follows, precedes, blocks, blocked, relates, duplicates, duplicated)
        description: Optional description of the relation
        lag: Working days between finish of predecessor and start of successor (default: 0)
    
    Returns:
        JSON string with relation creation result
    """
    try:
        # Create and validate relation request using Pydantic model
        relation_request = WorkPackageRelationCreateRequest(
            from_work_package_id=from_work_package_id,
            to_work_package_id=to_work_package_id,
            relation_type=relation_type,
            description=description,
            lag=lag
        )
        
        # Call OpenProject API
        result = await openproject_client.create_work_package_relation(
            relation_request.from_work_package_id, 
            relation_request.to_work_package_id, 
            relation_request.relation_type, 
            relation_request.description, 
            relation_request.lag
        )
        
        # Extract relation info from result
        relation_data = {
            "id": result.get("id"),
            "from_work_package_id": from_work_package_id,
            "to_work_package_id": to_work_package_id,
            "relation_type": result.get("type", relation_type),
            "reverse_type": result.get("reverseType"),
            "description": result.get("description", description),
            "lag": result.get("lag", lag),
            "url": f"{settings.openproject_url}/relations/{result.get('id')}" if result.get('id') else None
        }
        
        return json.dumps({
            "success": True,
            "message": f"Relation created: Work package {from_work_package_id} {relation_type} work package {to_work_package_id}",
            "relation": relation_data
        }, indent=2)
        
    except ValidationError as e:
        return json.dumps({
            "success": False,
            "error": "Validation error",
            "details": [{"field": err["loc"][-1], "message": err["msg"]} for err in e.errors()]
        }, indent=2)
    except OpenProjectAPIError as e:
        return json.dumps({
            "success": False,
            "error": f"OpenProject API error: {e.message}",
            "details": e.response_data
        }, indent=2)
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": f"Unexpected error: {str(e)}"
        }, indent=2)


@app.tool()
async def get_work_package_relations(work_package_id: int) -> str:
    """Get all relations for a specific work package.
    
    Args:
        work_package_id: ID of the work package to get relations for
    
    Returns:
        JSON string with list of relations
    """
    try:
        if work_package_id <= 0:
            return json.dumps({
                "success": False,
                "error": "Work package ID must be a positive integer"
            })
        
        relations = await openproject_client.get_work_package_relations(work_package_id)
        
        relation_list = []
        for relation in relations:
            # Extract linked work packages info
            from_wp = relation.get("_links", {}).get("from", {})
            to_wp = relation.get("_links", {}).get("to", {})
            
            relation_data = {
                "id": relation.get("id"),
                "type": relation.get("type"),
                "reverse_type": relation.get("reverseType"),
                "description": relation.get("description", ""),
                "lag": relation.get("lag", 0),
                "from_work_package": {
                    "id": from_wp.get("href", "").split("/")[-1] if from_wp.get("href") else None,
                    "title": from_wp.get("title", "Unknown")
                },
                "to_work_package": {
                    "id": to_wp.get("href", "").split("/")[-1] if to_wp.get("href") else None,
                    "title": to_wp.get("title", "Unknown")
                }
            }
            relation_list.append(relation_data)
        
        return json.dumps({
            "success": True,
            "message": f"Found {len(relation_list)} relations for work package {work_package_id}",
            "work_package_id": work_package_id,
            "relations": relation_list
        }, indent=2)
        
    except OpenProjectAPIError as e:
        return json.dumps({
            "success": False,
            "error": f"OpenProject API error: {e.message}",
            "details": e.response_data
        }, indent=2)
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": f"Unexpected error: {str(e)}"
        }, indent=2)


@app.tool()
async def delete_work_package_relation(relation_id: int) -> str:
    """Delete a work package relation.
    
    Args:
        relation_id: ID of the relation to delete
    
    Returns:
        JSON string with deletion result
    """
    try:
        if relation_id <= 0:
            return json.dumps({
                "success": False,
                "error": "Relation ID must be a positive integer"
            })
        
        await openproject_client.delete_work_package_relation(relation_id)
        
        return json.dumps({
            "success": True,
            "message": f"Relation {relation_id} deleted successfully"
        }, indent=2)
        
    except OpenProjectAPIError as e:
        return json.dumps({
            "success": False,
            "error": f"OpenProject API error: {e.message}",
            "details": e.response_data
        }, indent=2)
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": f"Unexpected error: {str(e)}"
        }, indent=2)


@app.tool()
async def get_projects() -> str:
    """Get list of all projects from OpenProject.
    
    Returns:
        JSON string with list of projects
    """
    try:
        projects = await openproject_client.get_projects()
        
        project_list = []
        for project in projects:
            project_list.append({
                "id": project.get("id"),
                "name": project.get("name"),
                "description": project.get("description", {}).get("raw", ""),
                "status": project.get("status"),
                "identifier": project.get("identifier"),
                "url": f"{settings.openproject_url}/projects/{project.get('identifier', project.get('id'))}"
            })
        
        return json.dumps({
            "success": True,
            "message": f"Found {len(project_list)} projects",
            "projects": project_list
        }, indent=2)
        
    except OpenProjectAPIError as e:
        return json.dumps({
            "success": False,
            "error": f"OpenProject API error: {e.message}",
            "details": e.response_data
        }, indent=2)
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": f"Unexpected error: {str(e)}"
        }, indent=2)


@app.tool()
async def get_work_packages(project_id: int) -> str:
    """Get work packages for a specific project.
    
    Args:
        project_id: ID of the project to get work packages from
    
    Returns:
        JSON string with list of work packages
    """
    try:
        if project_id <= 0:
            return json.dumps({
                "success": False,
                "error": "Project ID must be a positive integer"
            })
        
        work_packages = await openproject_client.get_work_packages(project_id)
        
        wp_list = []
        for wp in work_packages:
            wp_list.append({
                "id": wp.get("id"),
                "subject": wp.get("subject"),
                "description": wp.get("description", {}).get("raw", ""),
                "project_id": project_id,
                "start_date": wp.get("startDate"),
                "due_date": wp.get("dueDate"),
                "status": wp.get("_links", {}).get("status", {}).get("title", "Unknown"),
                "assignee": wp.get("_links", {}).get("assignee", {}).get("title", "Unassigned"),
                "url": f"{settings.openproject_url}/work_packages/{wp.get('id')}"
            })
        
        return json.dumps({
            "success": True,
            "message": f"Found {len(wp_list)} work packages in project {project_id}",
            "work_packages": wp_list
        }, indent=2)
        
    except OpenProjectAPIError as e:
        return json.dumps({
            "success": False,
            "error": f"OpenProject API error: {e.message}",
            "details": e.response_data
        }, indent=2)
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": f"Unexpected error: {str(e)}"
        }, indent=2)


@app.tool()
async def update_work_package(
    work_package_id: int,
    subject: Optional[str] = None,
    description: Optional[str] = None,
    start_date: Optional[str] = None,
    due_date: Optional[str] = None,
    assignee_id: Optional[int] = None,
    estimated_hours: Optional[float] = None
) -> str:
    """Update an existing work package.
    
    Args:
        work_package_id: ID of the work package to update
        subject: New subject/title (optional)
        description: New description (optional)
        start_date: New start date in YYYY-MM-DD format (optional)
        due_date: New due date in YYYY-MM-DD format (optional)
        assignee_id: User ID to assign work package to (optional)
        estimated_hours: New estimated hours (optional)
    
    Returns:
        JSON string with update result
    """
    try:
        if work_package_id <= 0:
            return json.dumps({
                "success": False,
                "error": "Work package ID must be a positive integer"
            })
        
        # First, fetch the current work package to get the lockVersion
        # This is required by OpenProject's optimistic locking mechanism
        current_wp = await openproject_client.get_work_package_by_id(work_package_id)
        lock_version = current_wp.get("lockVersion")
        
        if lock_version is None:
            return json.dumps({
                "success": False,
                "error": "Unable to retrieve lock version for work package. It may not exist."
            })
        
        # Build update payload with only provided fields
        updates = {
            "lockVersion": lock_version  # Required for optimistic locking
        }
        
        if subject:
            updates["subject"] = subject.strip()
        
        if description is not None:
            updates["description"] = {"raw": description.strip()}
        
        if start_date:
            if not _is_valid_date_format(start_date):
                return json.dumps({
                    "success": False,
                    "error": "Start date must be in YYYY-MM-DD format"
                })
            updates["startDate"] = start_date
        
        if due_date:
            if not _is_valid_date_format(due_date):
                return json.dumps({
                    "success": False,
                    "error": "Due date must be in YYYY-MM-DD format"
                })
            updates["dueDate"] = due_date
        
        if assignee_id:
            updates["_links"] = updates.get("_links", {})
            updates["_links"]["assignee"] = {"href": f"/api/v3/users/{assignee_id}"}
        
        if estimated_hours:
            updates["estimatedTime"] = f"PT{estimated_hours}H"
        
        # Check if any actual updates were provided (besides lockVersion)
        if len(updates) == 1:
            return json.dumps({
                "success": False,
                "error": "No updates provided. Specify at least one field to update."
            })
        
        result = await openproject_client.update_work_package(work_package_id, updates)
        
        return json.dumps({
            "success": True,
            "message": f"Work package {work_package_id} updated successfully",
            "work_package": {
                "id": result.get("id"),
                "subject": result.get("subject"),
                "description": result.get("description", {}).get("raw", ""),
                "start_date": result.get("startDate"),
                "due_date": result.get("dueDate"),
                "status": result.get("_links", {}).get("status", {}).get("title", "Unknown"),
                "url": f"{settings.openproject_url}/work_packages/{result.get('id')}"
            }
        }, indent=2)
        
    except OpenProjectAPIError as e:
        return json.dumps({
            "success": False,
            "error": f"OpenProject API error: {e.message}",
            "details": e.response_data
        }, indent=2)
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": f"Unexpected error: {str(e)}"
        }, indent=2)


@app.tool()
async def get_users(email_filter: Optional[str] = None) -> str:
    """Get list of users, optionally filtered by email.
    
    Args:
        email_filter: Optional email address to search for specific user
    
    Returns:
        JSON string with list of users
    """
    try:
        filters = None
        if email_filter:
            # OpenProject API filter format for email search
            filters = {"filters": f'[{{"email": {{"operator": "=", "values": ["{email_filter}"]}}}}]'}
        
        users = await openproject_client.get_users(filters)
        
        user_list = []
        for user in users:
            user_list.append({
                "id": user.get("id"),
                "name": user.get("name"),
                "firstName": user.get("firstName", ""),
                "lastName": user.get("lastName", ""),
                "email": user.get("email", ""),
                "login": user.get("login", ""),
                "status": user.get("status", ""),
                "language": user.get("language", ""),
                "admin": user.get("admin", False),
                "created_at": user.get("createdAt", ""),
                "updated_at": user.get("updatedAt", "")
            })
        
        return json.dumps({
            "success": True,
            "message": f"Found {len(user_list)} users" + (f" matching email '{email_filter}'" if email_filter else ""),
            "users": user_list
        }, indent=2)
        
    except OpenProjectAPIError as e:
        return json.dumps({
            "success": False,
            "error": f"OpenProject API error: {e.message}",
            "details": e.response_data
        }, indent=2)
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": f"Unexpected error: {str(e)}"
        }, indent=2)


@app.tool()
async def assign_work_package_by_email(work_package_id: int, assignee_email: str) -> str:
    """Assign work package to user by email address.
    
    Args:
        work_package_id: ID of the work package to assign
        assignee_email: Email address of the user to assign to
    
    Returns:
        JSON string with assignment result
    """
    try:
        if work_package_id <= 0:
            return json.dumps({
                "success": False,
                "error": "Work package ID must be a positive integer"
            })
        
        if not assignee_email or "@" not in assignee_email:
            return json.dumps({
                "success": False,
                "error": "Valid email address is required"
            })
        
        # Find user by email
        user = await openproject_client.get_user_by_email(assignee_email)
        if not user:
            return json.dumps({
                "success": False,
                "error": f"User with email '{assignee_email}' not found"
            })
        
        # First, fetch the current work package to get the lockVersion
        current_wp = await openproject_client.get_work_package_by_id(work_package_id)
        lock_version = current_wp.get("lockVersion")
        
        if lock_version is None:
            return json.dumps({
                "success": False,
                "error": "Unable to retrieve lock version for work package"
            })
        
        # Update work package with assignee and lockVersion
        updates = {
            "lockVersion": lock_version,
            "_links": {
                "assignee": {
                    "href": f"/api/v3/users/{user.get('id')}"
                }
            }
        }
        
        result = await openproject_client.update_work_package(work_package_id, updates)
        
        return json.dumps({
            "success": True,
            "message": f"Work package {work_package_id} assigned to {user.get('name', assignee_email)}",
            "work_package": {
                "id": result.get("id"),
                "subject": result.get("subject"),
                "assignee": {
                    "id": user.get("id"),
                    "name": user.get("name"),
                    "email": user.get("email")
                },
                "url": f"{settings.openproject_url}/work_packages/{result.get('id')}"
            }
        }, indent=2)
        
    except OpenProjectAPIError as e:
        return json.dumps({
            "success": False,
            "error": f"OpenProject API error: {e.message}",
            "details": e.response_data
        }, indent=2)
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": f"Unexpected error: {str(e)}"
        }, indent=2)


@app.tool()
async def get_project_members(project_id: int) -> str:
    """Get list of project members with roles.
    
    Args:
        project_id: ID of the project to get members from
    
    Returns:
        JSON string with list of project members
    """
    try:
        if project_id <= 0:
            return json.dumps({
                "success": False,
                "error": "Project ID must be a positive integer"
            })
        
        memberships = await openproject_client.get_project_memberships(project_id)
        
        member_list = []
        for membership in memberships:
            # Extract user and role information from HAL+JSON structure
            user_link = membership.get("_links", {}).get("principal", {})
            roles = membership.get("_links", {}).get("roles", [])
            
            # Get user details if available
            user_info = {
                "id": user_link.get("href", "").split("/")[-1] if user_link.get("href") else None,
                "title": user_link.get("title", "Unknown User")
            }
            
            # Extract role names
            role_names = []
            if isinstance(roles, list):
                role_names = [role.get("title", "Unknown Role") for role in roles]
            elif isinstance(roles, dict):
                role_names = [roles.get("title", "Unknown Role")]
            
            member_data = {
                "id": membership.get("id"),
                "user": user_info,
                "roles": role_names,
                "created_at": membership.get("createdAt", ""),
                "updated_at": membership.get("updatedAt", "")
            }
            member_list.append(member_data)
        
        return json.dumps({
            "success": True,
            "message": f"Found {len(member_list)} members in project {project_id}",
            "project_id": project_id,
            "members": member_list
        }, indent=2)
        
    except OpenProjectAPIError as e:
        return json.dumps({
            "success": False,
            "error": f"OpenProject API error: {e.message}",
            "details": e.response_data
        }, indent=2)
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": f"Unexpected error: {str(e)}"
        }, indent=2)


@app.tool()
async def get_work_package_types() -> str:
    """Get available work package types from OpenProject.
    
    Returns:
        JSON string with list of work package types
    """
    try:
        types = await openproject_client.get_work_package_types()
        
        type_list = []
        for wp_type in types:
            type_list.append({
                "id": wp_type.get("id"),
                "name": wp_type.get("name"),
                "description": wp_type.get("description", ""),
                "position": wp_type.get("position", 0),
                "is_default": wp_type.get("isDefault", False),
                "is_milestone": wp_type.get("isMilestone", False)
            })
        
        return json.dumps({
            "success": True,
            "message": f"Found {len(type_list)} work package types",
            "types": type_list
        }, indent=2)
        
    except OpenProjectAPIError as e:
        return json.dumps({
            "success": False,
            "error": f"OpenProject API error: {e.message}",
            "details": e.response_data
        }, indent=2)
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": f"Unexpected error: {str(e)}"
        }, indent=2)


@app.tool()
async def get_work_package_statuses() -> str:
    """Get available work package statuses from OpenProject.
    
    Returns:
        JSON string with list of work package statuses
    """
    try:
        statuses = await openproject_client.get_work_package_statuses()
        
        status_list = []
        for status in statuses:
            status_list.append({
                "id": status.get("id"),
                "name": status.get("name"),
                "description": status.get("description", ""),
                "position": status.get("position", 0),
                "is_default": status.get("isDefault", False),
                "is_closed": status.get("isClosed", False),
                "is_readonly": status.get("isReadonly", False)
            })
        
        return json.dumps({
            "success": True,
            "message": f"Found {len(status_list)} work package statuses",
            "statuses": status_list
        }, indent=2)
        
    except OpenProjectAPIError as e:
        return json.dumps({
            "success": False,
            "error": f"OpenProject API error: {e.message}",
            "details": e.response_data
        }, indent=2)
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": f"Unexpected error: {str(e)}"
        }, indent=2)


@app.tool()
async def get_priorities() -> str:
    """Get available work package priorities from OpenProject.
    
    Returns:
        JSON string with list of priorities
    """
    try:
        priorities = await openproject_client.get_priorities()
        
        priority_list = []
        for priority in priorities:
            priority_list.append({
                "id": priority.get("id"),
                "name": priority.get("name"),
                "description": priority.get("description", ""),
                "position": priority.get("position", 0),
                "is_default": priority.get("isDefault", False),
                "is_active": priority.get("isActive", True)
            })
        
        return json.dumps({
            "success": True,
            "message": f"Found {len(priority_list)} priorities",
            "priorities": priority_list
        }, indent=2)
        
    except OpenProjectAPIError as e:
        return json.dumps({
            "success": False,
            "error": f"OpenProject API error: {e.message}",
            "details": e.response_data
        }, indent=2)
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": f"Unexpected error: {str(e)}"
        }, indent=2)


@app.tool()
async def get_project_summary(project_id: int) -> str:
    """Get a comprehensive summary of a project including work packages and status.
    
    Args:
        project_id: ID of the project to summarize
    
    Returns:
        JSON string with project summary
    """
    try:
        if project_id <= 0:
            return json.dumps({
                "success": False,
                "error": "Project ID must be a positive integer"
            })
        
        # Get project details and work packages in parallel
        projects = await openproject_client.get_projects()
        project = next((p for p in projects if p.get("id") == project_id), None)
        
        if not project:
            return json.dumps({
                "success": False,
                "error": f"Project with ID {project_id} not found"
            })
        
        work_packages = await openproject_client.get_work_packages(project_id)
        
        # Analyze work packages
        total_wp = len(work_packages)
        with_dates = sum(1 for wp in work_packages if wp.get("startDate") or wp.get("dueDate"))
        assigned = sum(1 for wp in work_packages if wp.get("_links", {}).get("assignee"))
        
        status_counts = {}
        for wp in work_packages:
            status = wp.get("_links", {}).get("status", {}).get("title", "Unknown")
            status_counts[status] = status_counts.get(status, 0) + 1
        
        return json.dumps({
            "success": True,
            "project": {
                "id": project.get("id"),
                "name": project.get("name"),
                "description": project.get("description", {}).get("raw", ""),
                "status": project.get("status"),
                "url": f"{settings.openproject_url}/projects/{project.get('identifier', project.get('id'))}"
            },
            "summary": {
                "total_work_packages": total_wp,
                "work_packages_with_dates": with_dates,
                "assigned_work_packages": assigned,
                "unassigned_work_packages": total_wp - assigned,
                "status_breakdown": status_counts,
                "gantt_ready": with_dates > 0
            }
        }, indent=2)
        
    except OpenProjectAPIError as e:
        return json.dumps({
            "success": False,
            "error": f"OpenProject API error: {e.message}",
            "details": e.response_data
        }, indent=2)
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": f"Unexpected error: {str(e)}"
        }, indent=2)


def _is_valid_date_format(date_string: str) -> bool:
    """Validate date string is in YYYY-MM-DD format."""
    try:
        from datetime import datetime
        datetime.strptime(date_string, "%Y-%m-%d")
        return True
    except ValueError:
        return False


# Add resource handlers
@app.resource("openproject://projects")
async def projects_resource() -> str:
    """List all projects in OpenProject."""
    try:
        projects = await openproject_client.get_projects()
        
        formatted_projects = []
        for project in projects:
            formatted_projects.append({
                "id": project.get("id"),
                "name": project.get("name"),
                "description": project.get("description", {}).get("raw", ""),
                "status": project.get("status"),
                "identifier": project.get("identifier"),
                "url": f"{settings.openproject_url}/projects/{project.get('identifier', project.get('id'))}"
            })
        
        return json.dumps({
            "projects": formatted_projects,
            "total": len(formatted_projects),
            "retrieved_at": "now"
        }, indent=2)
        
    except OpenProjectAPIError as e:
        return json.dumps({
            "error": f"OpenProject API error: {e.message}",
            "details": e.response_data
        }, indent=2)


@app.resource("openproject://project/{project_id}")
async def project_resource(project_id: int) -> str:
    """Get details for a specific project."""
    try:
        projects = await openproject_client.get_projects()
        project = next((p for p in projects if p.get("id") == project_id), None)
        
        if not project:
            return json.dumps({
                "error": f"Project with ID {project_id} not found"
            }, indent=2)
        
        # Get work packages for this project
        work_packages = await openproject_client.get_work_packages(project_id)
        
        return json.dumps({
            "project": {
                "id": project.get("id"),
                "name": project.get("name"),
                "description": project.get("description", {}).get("raw", ""),
                "status": project.get("status"),
                "identifier": project.get("identifier"),
                "url": f"{settings.openproject_url}/projects/{project.get('identifier', project.get('id'))}"
            },
            "work_packages_count": len(work_packages),
            "retrieved_at": "now"
        }, indent=2)
        
    except OpenProjectAPIError as e:
        return json.dumps({
            "error": f"OpenProject API error: {e.message}",
            "details": e.response_data
        }, indent=2)


@app.resource("openproject://work-packages/{project_id}")
async def work_packages_resource(project_id: int) -> str:
    """Get work packages for a specific project."""
    try:
        work_packages = await openproject_client.get_work_packages(project_id)
        
        formatted_wps = []
        for wp in work_packages:
            formatted_wps.append({
                "id": wp.get("id"),
                "subject": wp.get("subject"),
                "description": wp.get("description", {}).get("raw", ""),
                "project_id": project_id,
                "start_date": wp.get("startDate"),
                "due_date": wp.get("dueDate"),
                "status": wp.get("_links", {}).get("status", {}).get("title", "Unknown"),
                "type": wp.get("_links", {}).get("type", {}).get("title", "Unknown"),
                "priority": wp.get("_links", {}).get("priority", {}).get("title", "Unknown"),
                "assignee": wp.get("_links", {}).get("assignee", {}).get("title", "Unassigned"),
                "url": f"{settings.openproject_url}/work_packages/{wp.get('id')}"
            })
        
        return json.dumps({
            "work_packages": formatted_wps,
            "project_id": project_id,
            "total": len(formatted_wps),
            "retrieved_at": "now"
        }, indent=2)
        
    except OpenProjectAPIError as e:
        return json.dumps({
            "error": f"OpenProject API error: {e.message}",
            "details": e.response_data
        }, indent=2)


@app.resource("openproject://work-package/{work_package_id}")
async def work_package_resource(work_package_id: int) -> str:
    """Get details for a specific work package."""
    try:
        work_package = await openproject_client.get_work_package_by_id(work_package_id)
        
        return json.dumps({
            "work_package": {
                "id": work_package.get("id"),
                "subject": work_package.get("subject"),
                "description": work_package.get("description", {}).get("raw", ""),
                "project": work_package.get("_links", {}).get("project", {}).get("title", "Unknown"),
                "start_date": work_package.get("startDate"),
                "due_date": work_package.get("dueDate"),
                "status": work_package.get("_links", {}).get("status", {}).get("title", "Unknown"),
                "type": work_package.get("_links", {}).get("type", {}).get("title", "Unknown"),
                "priority": work_package.get("_links", {}).get("priority", {}).get("title", "Unknown"),
                "assignee": work_package.get("_links", {}).get("assignee", {}).get("title", "Unassigned"),
                "estimated_time": work_package.get("estimatedTime"),
                "done_ratio": work_package.get("doneRatio", 0),
                "url": f"{settings.openproject_url}/work_packages/{work_package.get('id')}"
            },
            "retrieved_at": "now"
        }, indent=2)
        
    except OpenProjectAPIError as e:
        return json.dumps({
            "error": f"OpenProject API error: {e.message}",
            "details": e.response_data
        }, indent=2)


@app.resource("openproject://work-package-relations/{work_package_id}")
async def work_package_relations_resource(work_package_id: int) -> str:
    """Get relations for a specific work package."""
    try:
        relations = await openproject_client.get_work_package_relations(work_package_id)
        
        formatted_relations = []
        for relation in relations:
            # Extract linked work packages info
            from_wp = relation.get("_links", {}).get("from", {})
            to_wp = relation.get("_links", {}).get("to", {})
            
            relation_data = {
                "id": relation.get("id"),
                "type": relation.get("type"),
                "reverse_type": relation.get("reverseType"),
                "description": relation.get("description", ""),
                "lag": relation.get("lag", 0),
                "from_work_package": {
                    "id": from_wp.get("href", "").split("/")[-1] if from_wp.get("href") else None,
                    "title": from_wp.get("title", "Unknown")
                },
                "to_work_package": {
                    "id": to_wp.get("href", "").split("/")[-1] if to_wp.get("href") else None,
                    "title": to_wp.get("title", "Unknown")
                }
            }
            formatted_relations.append(relation_data)
        
        return json.dumps({
            "work_package_id": work_package_id,
            "relations": formatted_relations,
            "total": len(formatted_relations),
            "retrieved_at": "now"
        }, indent=2)
        
    except OpenProjectAPIError as e:
        return json.dumps({
            "error": f"OpenProject API error: {e.message}",
            "details": e.response_data
        }, indent=2)


# Add prompt handlers
@app.prompt()
async def project_status_report(project_id: int) -> list:
    """Generate a comprehensive project status report.
    
    Args:
        project_id: ID of the project to report on
        
    Returns:
        List of message objects for LLM consumption
    """
    try:
        # Get project details and work packages
        projects = await openproject_client.get_projects()
        project = next((p for p in projects if p.get("id") == project_id), None)
        
        if not project:
            return [
                {
                    "role": "user",
                    "content": f"Error: Project with ID {project_id} not found. Please check the project ID and try again."
                }
            ]
        
        work_packages = await openproject_client.get_work_packages(project_id)
        
        # Analyze project status
        total_wp = len(work_packages)
        with_dates = sum(1 for wp in work_packages if wp.get("startDate") or wp.get("dueDate"))
        assigned = sum(1 for wp in work_packages if wp.get("_links", {}).get("assignee"))
        
        status_counts = {}
        for wp in work_packages:
            status = wp.get("_links", {}).get("status", {}).get("title", "Unknown")
            status_counts[status] = status_counts.get(status, 0) + 1
        
        project_data = {
            "project": {
                "name": project.get("name"),
                "description": project.get("description", {}).get("raw", ""),
                "status": project.get("status"),
                "url": f"{settings.openproject_url}/projects/{project.get('identifier', project.get('id'))}"
            },
            "summary": {
                "total_work_packages": total_wp,
                "work_packages_with_dates": with_dates,
                "assigned_work_packages": assigned,
                "unassigned_work_packages": total_wp - assigned,
                "status_breakdown": status_counts,
                "gantt_ready": with_dates > 0
            },
            "work_packages": [
                {
                    "subject": wp.get("subject"),
                    "status": wp.get("_links", {}).get("status", {}).get("title", "Unknown"),
                    "assignee": wp.get("_links", {}).get("assignee", {}).get("title", "Unassigned"),
                    "start_date": wp.get("startDate"),
                    "due_date": wp.get("dueDate")
                }
                for wp in work_packages[:10]  # Limit to first 10 for readability
            ]
        }
        
        return [
            {
                "role": "user",
                "content": f"""Please analyze this project status data and provide a comprehensive report:

{json.dumps(project_data, indent=2)}

Focus on:
1. Overall project health and progress
2. Work package completion status
3. Resource allocation (assigned vs unassigned work)
4. Timeline readiness (work packages with dates)
5. Any potential issues or recommendations
6. Next steps for project management"""
            }
        ]
        
    except Exception as e:
        return [
            {
                "role": "user",
                "content": f"Error generating project status report: {str(e)}"
            }
        ]


@app.prompt()
async def work_package_summary(project_id: int, status_filter: str = "all") -> list:
    """Summarize work packages in a project.
    
    Args:
        project_id: ID of the project
        status_filter: Filter by status (all, new, in_progress, closed, etc.)
        
    Returns:
        List of message objects for LLM consumption
    """
    try:
        work_packages = await openproject_client.get_work_packages(project_id)
        
        # Filter by status if specified
        if status_filter != "all":
            work_packages = [
                wp for wp in work_packages 
                if wp.get("_links", {}).get("status", {}).get("title", "").lower() == status_filter.lower()
            ]
        
        wp_data = []
        for wp in work_packages:
            wp_data.append({
                "id": wp.get("id"),
                "subject": wp.get("subject"),
                "description": wp.get("description", {}).get("raw", "")[:200] + "..." if len(wp.get("description", {}).get("raw", "")) > 200 else wp.get("description", {}).get("raw", ""),
                "status": wp.get("_links", {}).get("status", {}).get("title", "Unknown"),
                "type": wp.get("_links", {}).get("type", {}).get("title", "Unknown"),
                "priority": wp.get("_links", {}).get("priority", {}).get("title", "Unknown"),
                "assignee": wp.get("_links", {}).get("assignee", {}).get("title", "Unassigned"),
                "start_date": wp.get("startDate"),
                "due_date": wp.get("dueDate"),
                "done_ratio": wp.get("doneRatio", 0)
            })
        
        return [
            {
                "role": "user",
                "content": f"""Please provide a summary of these work packages (filtered by status: {status_filter}):

{json.dumps(wp_data, indent=2)}

Please organize your summary by:
1. High-priority items requiring attention
2. Items by status category
3. Timeline overview (upcoming deadlines)
4. Resource allocation analysis
5. Recommendations for project management"""
            }
        ]
        
    except Exception as e:
        return [
            {
                "role": "user",
                "content": f"Error generating work package summary: {str(e)}"
            }
        ]


@app.prompt()
async def project_planning_assistant(project_name: str, work_package_count: int = 5) -> list:
    """Help with planning a new project structure.
    
    Args:
        project_name: Name of the project to plan
        work_package_count: Suggested number of work packages to create
        
    Returns:
        List of message objects for LLM consumption
    """
    return [
        {
            "role": "user",
            "content": f"""I need help planning a new project called "{project_name}". 

Please help me create a project structure with approximately {work_package_count} work packages. Consider:

1. **Project Planning Best Practices:**
   - Break down the project into logical phases
   - Create work packages with clear deliverables
   - Establish realistic timelines
   - Define dependencies between work packages

2. **For Each Work Package, suggest:**
   - Clear, actionable title
   - Brief description of what needs to be done
   - Estimated duration
   - Dependencies on other work packages
   - Priority level

3. **Timeline Considerations:**
   - Logical sequence of work packages
   - Dependencies that affect scheduling
   - Buffer time for unexpected issues
   - Milestone checkpoints

4. **Resource Planning:**
   - Skills required for each work package
   - Potential team member assignments
   - External dependencies or resources needed

Please provide a structured breakdown that I can use to create the project in OpenProject with proper dates and dependencies for a functional Gantt chart."""
        }
    ]


@app.prompt()
async def team_workload_analysis(project_ids: list[int] = None) -> list:
    """Analyze team workload across projects.
    
    Args:
        project_ids: List of project IDs to analyze (optional, analyzes all if not provided)
        
    Returns:
        List of message objects for LLM consumption
    """
    try:
        # Get all projects if none specified
        if project_ids is None:
            projects = await openproject_client.get_projects()
            project_ids = [p.get("id") for p in projects[:5]]  # Limit to first 5 for performance
        
        workload_data = {}
        total_work_packages = 0
        
        for project_id in project_ids:
            try:
                work_packages = await openproject_client.get_work_packages(project_id)
                total_work_packages += len(work_packages)
                
                for wp in work_packages:
                    assignee = wp.get("_links", {}).get("assignee", {}).get("title", "Unassigned")
                    if assignee not in workload_data:
                        workload_data[assignee] = {
                            "total_tasks": 0,
                            "in_progress": 0,
                            "completed": 0,
                            "overdue": 0,
                            "projects": set()
                        }
                    
                    workload_data[assignee]["total_tasks"] += 1
                    workload_data[assignee]["projects"].add(project_id)
                    
                    status = wp.get("_links", {}).get("status", {}).get("title", "").lower()
                    if "progress" in status or "active" in status:
                        workload_data[assignee]["in_progress"] += 1
                    elif "closed" in status or "done" in status:
                        workload_data[assignee]["completed"] += 1
                    
                    # Check for overdue items (simplified check)
                    due_date = wp.get("dueDate")
                    if due_date and due_date < "2024-12-20":  # Simplified date check
                        workload_data[assignee]["overdue"] += 1
                        
            except Exception:
                continue  # Skip projects that can't be accessed
        
        # Convert sets to lists for JSON serialization
        for assignee_data in workload_data.values():
            assignee_data["projects"] = list(assignee_data["projects"])
        
        return [
            {
                "role": "user",
                "content": f"""Please analyze this team workload data across {len(project_ids)} projects:

Total work packages analyzed: {total_work_packages}

Team workload breakdown:
{json.dumps(workload_data, indent=2)}

Please provide analysis on:
1. **Workload Distribution:**
   - Who has the heaviest workload?
   - Are there team members with capacity for additional work?
   - Is work evenly distributed?

2. **Progress Analysis:**
   - Which team members are making good progress?
   - Are there bottlenecks or blockers?
   - Completion rates by team member

3. **Risk Assessment:**
   - Overdue items and their impact
   - Team members who might be overloaded
   - Projects that might need additional resources

4. **Recommendations:**
   - Workload rebalancing suggestions
   - Priority adjustments
   - Resource allocation improvements
   - Process improvements to increase efficiency"""
            }
        ]
        
    except Exception as e:
        return [
            {
                "role": "user",
                "content": f"Error generating team workload analysis: {str(e)}"
            }
        ]


# Server is run directly via app.run() from the run_server.py script
