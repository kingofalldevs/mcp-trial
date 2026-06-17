from mcp.server.fastmcp import FastMCP
import json
from datetime import datetime

# Initialize FastMCP server
mcp = FastMCP("simple-json-server")

@mcp.tool()
def get_json_data() -> str:
    """Returns a mock JSON dataset representing user info and system status."""
    data = {
        "status": "success",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "serverInfo": {
            "name": "simple-json-server",
            "type": "Model Context Protocol (MCP)",
            "status": "online",
            "environment": "Python"
        },
        "payload": {
            "users": [
                { "id": 101, "name": "Sarah Connor", "role": "Leader" },
                { "id": 102, "name": "John Connor", "role": "Commander" },
                { "id": 103, "name": "T-800", "role": "Guardian" }
            ],
            "config": {
                "debug": True,
                "mode": "autonomous",
                "location": "Los Angeles"
            }
        }
    }
    return json.dumps(data, indent=2)

if __name__ == "__main__":
    import os
    # If PORT env variable is present (like on Render/Railway), run as SSE server
    port = os.environ.get("PORT")
    if port:
        print(f"Starting SSE server on port {port}")
        mcp.settings.host = "0.0.0.0"
        mcp.settings.port = int(port)
        mcp.run(transport="sse")
    else:
        mcp.run()
