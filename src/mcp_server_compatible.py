#!/usr/bin/env python3
"""OpenProject MCP Server - Python 3.9 Compatible Version."""

import asyncio
import json
import sys
from typing import Dict, Any, Optional, List
from openproject_client import OpenProjectClient, OpenProjectAPIError
from models import ProjectCreateRequest, ProjectUpdateRequest, WorkPackageCreateRequest
from config import settings
from handlers.resources import ResourceHandler
from utils.logging import get_logger, log_tool_execution, log_error
from utils.validation import generate_identifier, validate_project_status


def _format_api_error(e: OpenProjectAPIError) -> dict:
    """Build a consistent error payload, with a clear hint on 403 permissions."""
    error_message = f"OpenProject API error: {e.message}"
    if e.status_code == 403:
        error_message = (
            f"Permission denied (403): {e.message}. Creating a subproject requires "
            f"the 'add_subprojects' permission on the parent project, or global "
            f"project-creation rights. Setting a status requires edit rights on the project."
        )
    return {
        "success": False,
        "error": error_message,
        "status_code": e.status_code,
        "details": e.response_data,
    }


def _is_identifier_taken_error(e: OpenProjectAPIError) -> bool:
    """Detect an OpenProject error caused by a duplicate/taken identifier."""
    if e.status_code not in (409, 422):
        return False
    haystack = (e.message or "").lower()
    validation_errors = getattr(e, "validation_errors", None)
    if isinstance(validation_errors, dict):
        haystack += " " + " ".join(str(k) for k in validation_errors.keys()).lower()
    return "identifier" in haystack

logger = get_logger(__name__)

# Initialize OpenProject client and resource handler
openproject_client = OpenProjectClient()
resource_handler = ResourceHandler(openproject_client)


class MCPServer:
    """Simple MCP Server implementation compatible with Python 3.9."""
    
    def __init__(self):
        self.tools = {}
        self.resources = {}
        self.prompts = {}
        self._register_tools()
        self._register_resources()
        self._register_prompts()
    
    def tool(self, func):
        """Register a tool function."""
        self.tools[func.__name__] = {
            'function': func,
            'description': func.__doc__ or "",
            'name': func.__name__
        }
        return func
    
    def resource(self, uri_template):
        """Register a resource handler."""
        def decorator(func):
            self.resources[uri_template] = {
                'function': func,
                'description': func.__doc__ or "",
                'uri_template': uri_template
            }
            return func
        return decorator
    
    def prompt(self, func):
        """Register a prompt handler."""
        self.prompts[func.__name__] = {
            'function': func,
            'description': func.__doc__ or "",
            'name': func.__name__
        }
        return func
    
    def _register_tools(self):
        """Register all MCP tools."""
        
        @self.tool
        async def health_check() -> str:
            """Health check tool to verify OpenProject MCP Server is running and connected."""
            try:
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
        
        @self.tool
        async def create_project(
            name: str,
            description: str = "",
            parent_id: Optional[int] = None,
            status: Optional[str] = None,
            identifier: Optional[str] = None,
        ) -> str:
            """Create a new project in OpenProject.

            Optional parent_id nests it under another project; optional status is
            one of on_track | off_track | at_risk | not_started | finished |
            discontinued; identifier auto-generates from name when omitted.
            """
            try:
                if not name or not name.strip():
                    return json.dumps({
                        "success": False,
                        "error": "Project name is required and cannot be empty"
                    })

                if status is not None:
                    try:
                        validate_project_status(status)
                    except ValueError as ve:
                        return json.dumps({"success": False, "error": str(ve)}, indent=2)

                clean_name = name.strip()
                user_supplied_identifier = bool(identifier and identifier.strip())
                base_identifier = identifier.strip() if user_supplied_identifier else generate_identifier(clean_name)

                max_attempts = 1 if user_supplied_identifier else 10
                last_error = None
                for attempt in range(1, max_attempts + 1):
                    candidate = base_identifier if attempt == 1 else f"{base_identifier}-{attempt}"
                    project_request = ProjectCreateRequest(
                        name=clean_name,
                        description=description.strip() if description else "",
                        parent_id=parent_id,
                        status=status,
                        identifier=candidate,
                    )
                    try:
                        result = await openproject_client.create_project(project_request)
                        return json.dumps({
                            "success": True,
                            "message": f"Project '{clean_name}' created successfully",
                            "project": {
                                "id": result.get("id"),
                                "name": result.get("name"),
                                "identifier": result.get("identifier"),
                                "description": result.get("description", {}).get("raw", ""),
                                "status": result.get("status"),
                                "url": f"{settings.openproject_url}/projects/{result.get('identifier', result.get('id'))}"
                            }
                        }, indent=2)
                    except OpenProjectAPIError as e:
                        last_error = e
                        if _is_identifier_taken_error(e) and not user_supplied_identifier:
                            continue
                        raise

                payload = _format_api_error(last_error) if last_error else {
                    "success": False, "error": "Could not generate a unique identifier"
                }
                payload["error"] = (
                    f"Could not create project: identifier '{base_identifier}' and "
                    f"{max_attempts - 1} numeric suffixes are all taken. {payload.get('error', '')}"
                )
                return json.dumps(payload, indent=2)

            except OpenProjectAPIError as e:
                return json.dumps(_format_api_error(e), indent=2)
            except Exception as e:
                return json.dumps({
                    "success": False,
                    "error": f"Unexpected error: {str(e)}"
                }, indent=2)

        @self.tool
        async def update_project(
            project_id: int,
            name: Optional[str] = None,
            description: Optional[str] = None,
            parent_id: Optional[int] = None,
            status: Optional[str] = None,
        ) -> str:
            """Update an existing project in OpenProject (PATCH).

            Only provided fields change; status is one of on_track | off_track |
            at_risk | not_started | finished | discontinued.
            """
            try:
                if not isinstance(project_id, int) or project_id <= 0:
                    return json.dumps({
                        "success": False,
                        "error": "project_id is required and must be a positive integer"
                    })

                if status is not None:
                    try:
                        validate_project_status(status)
                    except ValueError as ve:
                        return json.dumps({"success": False, "error": str(ve)}, indent=2)

                update_request = ProjectUpdateRequest(
                    name=name.strip() if name else None,
                    description=description if description is not None else None,
                    parent_id=parent_id,
                    status=status,
                )

                result = await openproject_client.update_project(project_id, update_request)

                return json.dumps({
                    "success": True,
                    "message": f"Project {project_id} updated successfully",
                    "project": {
                        "id": result.get("id"),
                        "name": result.get("name"),
                        "identifier": result.get("identifier"),
                        "description": result.get("description", {}).get("raw", ""),
                        "status": result.get("status"),
                        "url": f"{settings.openproject_url}/projects/{result.get('identifier', result.get('id'))}"
                    }
                }, indent=2)

            except OpenProjectAPIError as e:
                return json.dumps(_format_api_error(e), indent=2)
            except Exception as e:
                return json.dumps({
                    "success": False,
                    "error": f"Unexpected error: {str(e)}"
                }, indent=2)
        
        @self.tool
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
            """Create a work package in a project with dates for Gantt chart."""
            try:
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
        
        @self.tool
        async def create_work_package_dependency(
            from_work_package_id: int,
            to_work_package_id: int,
            relation_type: str = "follows",
            description: str = "",
            lag: int = 0
        ) -> str:
            """Create a dependency between two work packages for Gantt chart visualization."""
            try:
                if from_work_package_id <= 0:
                    return json.dumps({
                        "success": False,
                        "error": "from_work_package_id must be a positive integer"
                    })
                
                if to_work_package_id <= 0:
                    return json.dumps({
                        "success": False,
                        "error": "to_work_package_id must be a positive integer"
                    })
                
                if from_work_package_id == to_work_package_id:
                    return json.dumps({
                        "success": False,
                        "error": "Work package cannot have a relation with itself"
                    })
                
                valid_relations = ["follows", "precedes", "blocks", "blocked", "relates", "duplicates", "duplicated"]
                if relation_type not in valid_relations:
                    return json.dumps({
                        "success": False,
                        "error": f"Invalid relation type. Must be one of: {', '.join(valid_relations)}"
                    })
                
                if lag < 0:
                    return json.dumps({
                        "success": False,
                        "error": "Lag must be zero or positive (working days)"
                    })
                
                result = await openproject_client.create_work_package_relation(
                    from_work_package_id, to_work_package_id, relation_type, description, lag
                )
                
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
        
        @self.tool
        async def get_work_package_relations(work_package_id: int) -> str:
            """Get all relations for a specific work package."""
            try:
                if work_package_id <= 0:
                    return json.dumps({
                        "success": False,
                        "error": "Work package ID must be a positive integer"
                    })
                
                relations = await openproject_client.get_work_package_relations(work_package_id)
                
                relation_list = []
                for relation in relations:
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
        
        @self.tool
        async def delete_work_package_relation(relation_id: int) -> str:
            """Delete a work package relation."""
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
        
        @self.tool
        async def get_projects() -> str:
            """Get list of all projects from OpenProject."""
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
        
        @self.tool
        async def get_work_packages(project_id: int) -> str:
            """Get work packages for a specific project."""
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
    
    def _register_resources(self):
        """Register resource handlers (simplified for Python 3.9)."""
        pass
    
    def _register_prompts(self):
        """Register prompt handlers (simplified for Python 3.9)."""
        pass
    
    async def handle_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Handle an MCP request."""
        try:
            method = request.get("method")
            params = request.get("params", {})
            
            if method == "tools/list":
                return {
                    "tools": [
                        {
                            "name": name,
                            "description": tool["description"],
                            "inputSchema": {
                                "type": "object",
                                "properties": {},
                                "required": []
                            }
                        }
                        for name, tool in self.tools.items()
                    ]
                }
            
            elif method == "tools/call":
                tool_name = params.get("name")
                arguments = params.get("arguments", {})
                
                if tool_name not in self.tools:
                    return {"error": f"Unknown tool: {tool_name}"}
                
                tool_func = self.tools[tool_name]["function"]
                try:
                    result = await tool_func(**arguments)
                    return {"content": [{"type": "text", "text": result}]}
                except Exception as e:
                    return {"error": f"Tool execution failed: {str(e)}"}
            
            else:
                return {"error": f"Unknown method: {method}"}
                
        except Exception as e:
            return {"error": f"Request handling failed: {str(e)}"}
    
    async def run_stdio(self):
        """Run the server in stdio mode for MCP protocol."""
        print("OpenProject MCP Server (Python 3.9 Compatible) starting...", file=sys.stderr)
        print(f"Connected to OpenProject: {settings.openproject_url}", file=sys.stderr)
        
        # Test connection
        try:
            connection_result = await openproject_client.test_connection()
            if connection_result.get('success'):
                print(f"✅ OpenProject connection successful: {connection_result.get('openproject_version')}", file=sys.stderr)
            else:
                print(f"❌ OpenProject connection failed: {connection_result.get('message')}", file=sys.stderr)
        except Exception as e:
            print(f"❌ Error testing connection: {e}", file=sys.stderr)
        
        print("MCP Server ready for requests", file=sys.stderr)
        
        # Simple JSONRPC-like handler for stdin/stdout
        try:
            while True:
                line = sys.stdin.readline()
                if not line:
                    break
                
                try:
                    request = json.loads(line.strip())
                    response = await self.handle_request(request)
                    print(json.dumps(response))
                    sys.stdout.flush()
                except json.JSONDecodeError:
                    print(json.dumps({"error": "Invalid JSON"}))
                    sys.stdout.flush()
                except Exception as e:
                    print(json.dumps({"error": f"Request error: {str(e)}"}))
                    sys.stdout.flush()
                    
        except KeyboardInterrupt:
            print("Server shutting down...", file=sys.stderr)
        finally:
            await openproject_client.close()


# Server instance
app = MCPServer()


async def main():
    """Run the MCP server."""
    await app.run_stdio()


if __name__ == "__main__":
    asyncio.run(main())
