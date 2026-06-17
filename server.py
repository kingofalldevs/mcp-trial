from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
import json
from datetime import datetime
from starlette.responses import JSONResponse
from starlette.requests import Request

# Initialize FastMCP server with DNS rebinding protection disabled for cloud hosting
mcp = FastMCP(
    "simple-json-server",
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False)
)

@mcp.custom_route("/", methods=["GET"])
async def home(request: Request) -> JSONResponse:
    return JSONResponse({
        "status": "online",
        "message": "Simple JSON MCP Server is running!",
        "version": "1.0.0",
        "endpoints": {
            "sse": "/sse",
            "messages": "/messages/"
        }
    })

import sqlite3
import os
import json
from datetime import datetime
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL")
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "memory.db")

def init_db():
    if DATABASE_URL:
        with psycopg2.connect(DATABASE_URL) as conn:
            with conn.cursor() as cursor:
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS memories (
                        id SERIAL PRIMARY KEY,
                        timestamp TEXT NOT NULL,
                        content TEXT NOT NULL
                    )
                ''')
            conn.commit()
    else:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    content TEXT NOT NULL
                )
            ''')
            conn.commit()

init_db()

@mcp.tool()
def save_memory(content: str) -> str:
    """Saves a piece of information, a summary, or a memory into the AI's persistent storage."""
    try:
        timestamp = datetime.utcnow().isoformat() + "Z"
        if DATABASE_URL:
            with psycopg2.connect(DATABASE_URL) as conn:
                with conn.cursor() as cursor:
                    cursor.execute('INSERT INTO memories (timestamp, content) VALUES (%s, %s) RETURNING id', (timestamp, content))
                    memory_id = cursor.fetchone()[0]
                conn.commit()
                return json.dumps({"status": "success", "message": "Memory saved successfully.", "id": memory_id})
        else:
            with sqlite3.connect(DB_PATH) as conn:
                cursor = conn.cursor()
                cursor.execute('INSERT INTO memories (timestamp, content) VALUES (?, ?)', (timestamp, content))
                conn.commit()
                return json.dumps({"status": "success", "message": "Memory saved successfully.", "id": cursor.lastrowid})
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)})

@mcp.tool()
def search_memory(query: str) -> str:
    """Searches past memories based on a text query. Use this to remember previous conversations or facts."""
    try:
        if DATABASE_URL:
            with psycopg2.connect(DATABASE_URL) as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute('SELECT id, timestamp, content FROM memories WHERE content ILIKE %s ORDER BY timestamp DESC', (f'%{query}%',))
                    results = cursor.fetchall()
                    return json.dumps({"status": "success", "results": results}, indent=2)
        else:
            with sqlite3.connect(DB_PATH) as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT id, timestamp, content FROM memories WHERE content LIKE ? ORDER BY timestamp DESC', (f'%{query}%',))
                results = [{"id": row[0], "timestamp": row[1], "content": row[2]} for row in cursor.fetchall()]
                return json.dumps({"status": "success", "results": results}, indent=2)
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)})

@mcp.tool()
def list_memories(limit: int = 10) -> str:
    """Lists the most recent memories stored by the AI."""
    try:
        if DATABASE_URL:
            with psycopg2.connect(DATABASE_URL) as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute('SELECT id, timestamp, content FROM memories ORDER BY timestamp DESC LIMIT %s', (limit,))
                    results = cursor.fetchall()
                    return json.dumps({"status": "success", "results": results}, indent=2)
        else:
            with sqlite3.connect(DB_PATH) as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT id, timestamp, content FROM memories ORDER BY timestamp DESC LIMIT ?', (limit,))
                results = [{"id": row[0], "timestamp": row[1], "content": row[2]} for row in cursor.fetchall()]
                return json.dumps({"status": "success", "results": results}, indent=2)
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)})

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
