#!/usr/bin/env python3
"""
Run the OpenProject MCP Server in HTTP mode with status endpoints

This script starts both the FastMCP server and a simple HTTP status server.
"""
import sys
import os
import asyncio
import json
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

# Add src directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

class StatusHandler(BaseHTTPRequestHandler):
    """HTTP handler for status endpoints."""
    
    def do_GET(self):
        """Handle GET requests."""
        parsed_path = urlparse(self.path)
        
        if parsed_path.path == '/health':
            self.send_health_response()
        elif parsed_path.path == '/':
            self.send_root_response()
        else:
            self.send_error(404, "Not Found")
    
    def send_health_response(self):
        """Send health check response."""
        try:
            # Import here to avoid issues during module loading
            from openproject_client import OpenProjectClient
            from config import settings
            
            # Create a new event loop for this thread
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            async def check_health():
                client = OpenProjectClient()
                try:
                    connection_result = await client.test_connection()
                    if connection_result.get('success'):
                        return {
                            "status": "healthy",
                            "message": "OpenProject MCP Server is currently running",
                            "openproject_connection": "connected",
                            "openproject_version": connection_result.get('openproject_version', 'unknown'),
                            "openproject_url": settings.openproject_url
                        }
                    else:
                        return {
                            "status": "degraded", 
                            "message": "OpenProject MCP Server is running but OpenProject connection failed",
                            "openproject_connection": "failed",
                            "error": connection_result.get('message', 'Unknown connection error'),
                            "openproject_url": settings.openproject_url
                        }
                finally:
                    await client.close()
            
            result = loop.run_until_complete(check_health())
            loop.close()
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps(result, indent=2).encode())
            
        except Exception as e:
            error_result = {
                "status": "unhealthy",
                "message": "OpenProject MCP Server encountered an error",
                "error": str(e)
            }
            
            self.send_response(500)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps(error_result, indent=2).encode())
    
    def send_root_response(self):
        """Send root endpoint response."""
        result = {
            "name": "OpenProject MCP Server",
            "status": "running",
            "message": "OpenProject MCP Server is currently running",
            "endpoints": {
                "/health": "Health check with OpenProject connection status",
                "/": "Basic server information"
            },
            "mcp_tools": [
                "health_check",
                "create_project",
                "get_project",
                "get_projects",
                "create_work_package", 
                "create_work_package_dependency",
                "get_work_packages",
                "get_work_package_relations",
                "get_work_package_types",
                "get_work_package_statuses",
                "get_priorities",
                "get_project_members"
            ],
            "ports": {
                "mcp_sse": 39127,
                "http_status": 39128
            }
        }
        
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(result, indent=2).encode())
    
    def log_message(self, format, *args):
        """Override to reduce log noise."""
        pass


def run_status_server():
    """Run the HTTP status server."""
    server = HTTPServer(('0.0.0.0', 8081), StatusHandler)
    print("Starting status server on port 8081...")
    server.serve_forever()


def run_mcp_server():
    """Run the MCP server."""
    try:
        from mcp_server import app
        from config import settings
        print(f"Starting OpenProject MCP Server in HTTP mode on port {settings.mcp_port}...")
        app.run(transport="sse", host=settings.mcp_host, port=settings.mcp_port)
    except ImportError as e:
        print(f"Import error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Error running MCP server: {e}")
        sys.exit(1)


if __name__ == "__main__":
    # Start status server in a separate thread
    status_thread = threading.Thread(target=run_status_server, daemon=True)
    status_thread.start()
    
    # Run MCP server in main thread
    run_mcp_server()
