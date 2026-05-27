# Docker Networking Configuration

## Overview

The OpenProject MCP Server runs in a Docker container with two separate services exposed on different ports:

1. **MCP SSE Server** - Main protocol handler for MCP tool requests
2. **HTTP Status Server** - Health checks and status endpoints

## Port Configuration

### Internal Container Ports

| Service | Port | Purpose |
|---------|------|---------|
| MCP SSE Server | `39127` (configurable via `MCP_PORT`) | MCP tool requests, SSE transport |
| HTTP Status Server | `8081` | Health checks (`/health`), server info (`/`) |

### Host Port Mapping

The `docker-compose.yml` maps container ports to host ports:

```yaml
ports:
  - "${MCP_PORT:-39127}:${MCP_PORT:-39127}"  # Host:Container mapping
  - "39128:8081"                               # Host:Container mapping
```

| Service | Container → Host |
|---------|------------------|
| MCP SSE Server | `39127:39127` (default) |
| HTTP Status Server | `8081:39128` |

### Access from Different Contexts

#### From Host Machine
```bash
# Status server
curl http://localhost:39128/health
curl http://localhost:39128/

# MCP server (via HTTP)
http://localhost:39127
```

#### From Container on Same Network (`mcp-network`)
```bash
# Using container DNS name
http://openproject-mcp:39127     # MCP SSE server
http://openproject-mcp:8081      # HTTP status server
```

#### From Container on Different Network
```bash
# Using host gateway (requires 'extra_hosts' in docker-compose)
http://host.docker.internal:39127      # MCP SSE server (via host)
http://host.docker.internal:39128      # HTTP status server (via host)
```

## Environment Variables

Configure these in `.env` or pass via `-e` flag to `docker-compose`:

```bash
OPENPROJECT_URL=http://host.docker.internal:8080     # OpenProject API URL
OPENPROJECT_API_KEY=your-api-key                      # OpenProject API token
MCP_HOST=0.0.0.0                                      # Bind address (0.0.0.0 = all interfaces)
MCP_PORT=39127                                        # MCP server port
MCP_LOG_LEVEL=INFO                                    # Log level (DEBUG, INFO, WARNING, ERROR)
```

## Health Checks

### HTTP Status Server Endpoints

**GET `/health`** - Detailed health status
```json
{
  "status": "healthy|degraded|unhealthy",
  "message": "...",
  "openproject_connection": "connected|failed",
  "openproject_version": "13.0.0",
  "openproject_url": "http://host.docker.internal:8080"
}
```

**GET `/`** - Server information
```json
{
  "name": "OpenProject MCP Server",
  "status": "running",
  "endpoints": {
    "/health": "...",
    "/": "..."
  },
  "ports": {
    "mcp_sse": 39127,
    "http_status": 39128
  }
}
```

### Docker Health Check

The container includes a HEALTHCHECK that:
- Runs every 30 seconds
- Waits 40 seconds before first check
- Times out after 10 seconds
- Fails after 3 consecutive failures

Check status:
```bash
docker ps --format "table {{.Names}}\t{{.Status}}"
```

## Network Architecture

```
┌─────────────────────────────────────────┐
│ Docker Host (localhost)                 │
│                                         │
│  ┌──────────────────────────────────┐  │
│  │ mcp-network (bridge)             │  │
│  │                                  │  │
│  │  ┌──────────────────────────┐    │  │
│  │  │ openproject-mcp:39127    │    │  │
│  │  │ openproject-mcp:8081     │    │  │
│  │  │ - MCP SSE server         │    │  │
│  │  │ - HTTP status server     │    │  │
│  │  └──────────────────────────┘    │  │
│  │                                  │  │
│  └──────────────────────────────────┘  │
│         ↓              ↓                │
│  Port 39127       Port 39128            │
│     (MCP)      (HTTP Status)            │
│         ↓              ↓                │
└─────────────────────────────────────────┘
         ↓              ↓
  Host localhost:39127  localhost:39128
```

## Connecting from Other Containers

### Option 1: Add to Same Network
```yaml
services:
  nanoclaw:
    networks:
      - mcp-network
    # Then use:
    # http://openproject-mcp:39127
```

### Option 2: Use Host Gateway
```yaml
services:
  nanoclaw:
    extra_hosts:
      - "host.docker.internal:host-gateway"
    # Then use:
    # http://host.docker.internal:39127
    # http://host.docker.internal:39128
```

### Option 3: Create Shared External Network
```bash
docker network create shared-mcp-network
```

Then connect both containers:
```bash
docker network connect shared-mcp-network openproject-mcp-server
docker network connect shared-mcp-network nanoclaw
```

## Troubleshooting

### Container fails to start
```bash
docker logs openproject-mcp-server
```

### Health check fails
```bash
# Check detailed health status
curl http://localhost:39128/health

# Verify OpenProject connection
docker exec openproject-mcp-server python3 -c \
  "import asyncio; from src.openproject_client import OpenProjectClient; \
   asyncio.run(OpenProjectClient().test_connection())"
```

### Cannot reach from another container
1. Verify containers are on same network: `docker network inspect mcp-network`
2. Verify container DNS: `docker exec nanoclaw ping openproject-mcp`
3. Check firewall rules on host
4. Use `host.docker.internal` as fallback

### Port already in use
```bash
# Find what's using port 39127
lsof -i :39127

# Or choose different port via environment
docker-compose up -e MCP_PORT=39999
```

## Performance Tuning

Resource limits (in `docker-compose.yml`):
```yaml
deploy:
  resources:
    limits:
      memory: 512M
      cpus: '0.5'
    reservations:
      memory: 256M
      cpus: '0.25'
```

Adjust based on:
- OpenProject API response time
- Number of concurrent MCP requests
- Local machine resources

## Security Considerations

1. **Don't expose ports outside firewall** - The current setup only binds to `0.0.0.0:127.0.0.1`
2. **API key management** - Store in `.env` file, never commit to git
3. **Network isolation** - Use bridge networks to isolate containers
4. **Host gateway access** - Only use `host.docker.internal` for internal container communication
