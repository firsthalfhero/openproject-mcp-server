#!/usr/bin/env python3
"""
Health check script for OpenProject MCP Server.
Used by Docker HEALTHCHECK directive.
"""
import sys
import os
import asyncio

# Add src directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


async def check_health():
    """Check if OpenProject connection is healthy."""
    try:
        from openproject_client import OpenProjectClient

        client = OpenProjectClient()
        try:
            result = await client.test_connection()
            return 0 if result.get('success') else 1
        finally:
            await client.close()
    except Exception as e:
        print(f"Health check failed: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(check_health())
    sys.exit(exit_code)
