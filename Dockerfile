# Multi-stage build for OpenProject MCP Server
FROM python:3.11-slim as builder

# Set working directory
WORKDIR /app

# Install system dependencies for building
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --user -r requirements.txt

# Production stage
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Create non-root user for security
RUN groupadd -r mcp && useradd -r -g mcp mcp

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy Python packages from builder
COPY --from=builder /root/.local /home/mcp/.local

# Copy application code
COPY src/ ./src/
COPY scripts/ ./scripts/

# Set up environment
ENV PATH=/home/mcp/.local/bin:$PATH
ENV PYTHONPATH=/app/src
ENV PYTHONUNBUFFERED=1

# Create directories for logs and data
RUN mkdir -p /app/logs /app/data && \
    chown -R mcp:mcp /app

# Switch to non-root user
USER mcp

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python3 -c "import asyncio; import sys; sys.path.insert(0, '/app/src'); from openproject_client import OpenProjectClient; \
    async def check(): \
        client = OpenProjectClient(); \
        result = await client.test_connection(); \
        await client.close(); \
        exit(0 if result['success'] else 1); \
    asyncio.run(check())" || exit 1

# Expose ports for MCP and status endpoints
EXPOSE 8080 8081

# Default command - run HTTP server with status endpoints
CMD ["python3", "scripts/run_http_server_with_status.py"]


