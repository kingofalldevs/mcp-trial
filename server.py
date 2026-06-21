import os
import json
import uuid
import sqlite3
import psycopg2
from datetime import datetime
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

import contextvars

import firebase_admin
from firebase_admin import credentials, auth as firebase_auth

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.responses import JSONResponse, HTMLResponse, RedirectResponse
from starlette.requests import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.cors import CORSMiddleware
import uvicorn

load_dotenv()

# We use a ContextVar to store the user's email securely across the async call chain
user_email_var = contextvars.ContextVar("user_email", default=None)

mcp = FastMCP(
    "ai-memory-server",
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False)
)

DATABASE_URL = os.environ.get("DATABASE_URL")
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "memory.db")

# Initialize Firebase Admin
firebase_sa_json = os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON")
if firebase_sa_json:
    try:
        cred_dict = json.loads(firebase_sa_json)
        cred = credentials.Certificate(cred_dict)
        firebase_admin.initialize_app(cred)
        print("Firebase Admin initialized successfully.")
    except Exception as e:
        print(f"Error initializing Firebase Admin: {e}")

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
                cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_name='memories' AND column_name='user_email'")
                if not cursor.fetchone():
                    cursor.execute("ALTER TABLE memories ADD COLUMN user_email TEXT DEFAULT ''")
                
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS oauth_sessions (
                        auth_code TEXT PRIMARY KEY,
                        access_token TEXT,
                        user_email TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    )
                ''')
                
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS client_connections (
                        user_email TEXT NOT NULL,
                        client_name TEXT NOT NULL,
                        user_agent TEXT,
                        last_active TEXT NOT NULL,
                        PRIMARY KEY (user_email, client_name)
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
            cursor.execute("PRAGMA table_info(memories)")
            columns = [info[1] for info in cursor.fetchall()]
            if 'user_email' not in columns:
                cursor.execute("ALTER TABLE memories ADD COLUMN user_email TEXT DEFAULT ''")
                
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS oauth_sessions (
                    auth_code TEXT PRIMARY KEY,
                    access_token TEXT,
                    user_email TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS client_connections (
                    user_email TEXT NOT NULL,
                    client_name TEXT NOT NULL,
                    user_agent TEXT,
                    last_active TEXT NOT NULL,
                    PRIMARY KEY (user_email, client_name)
                )
            ''')
            conn.commit()

init_db()

def record_client_activity(email: str, user_agent: str):
    """Logs the client name and activity time."""
    ua = (user_agent or "").lower()
    client_name = "Generic AI"
    
    if "claude" in ua:
        client_name = "Claude"
    elif "chatgpt" in ua or "openai" in ua:
        client_name = "ChatGPT"
    elif "cursor" in ua:
        client_name = "Cursor"
    elif "windsurf" in ua:
        client_name = "Windsurf"
    elif "manus" in ua:
        client_name = "Manus"
    else:
        # vscode and postman check
        if "vscode" in ua:
            client_name = "Cursor / Windsurf (VSCode)"
        elif "postman" in ua:
            client_name = "Postman / API Test"
        elif "python" in ua:
            client_name = "Python Client"
            
    timestamp = datetime.utcnow().isoformat() + "Z"
    
    if DATABASE_URL:
        with psycopg2.connect(DATABASE_URL) as conn:
            with conn.cursor() as cursor:
                cursor.execute('''
                    INSERT INTO client_connections (user_email, client_name, user_agent, last_active)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (user_email, client_name)
                    DO UPDATE SET last_active = EXCLUDED.last_active, user_agent = EXCLUDED.user_agent
                ''', (email, client_name, user_agent, timestamp))
            conn.commit()
    else:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO client_connections (user_email, client_name, user_agent, last_active)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_email, client_name)
                DO UPDATE SET last_active = excluded.last_active, user_agent = excluded.user_agent
            ''', (email, client_name, user_agent, timestamp))
            conn.commit()

def get_email_for_access_token(access_token: str):
    """Verifies the bearer token against the database."""
    if not access_token:
        print("[AUTH] get_email_for_access_token: empty token")
        return None
    print(f"[AUTH] Looking up token: {access_token[:16]}... (db={'pg' if DATABASE_URL else 'sqlite'})")
    try:
        if DATABASE_URL:
            with psycopg2.connect(DATABASE_URL) as conn:
                with conn.cursor() as cursor:
                    cursor.execute('SELECT user_email FROM oauth_sessions WHERE access_token = %s', (access_token,))
                    row = cursor.fetchone()
                    print(f"[AUTH] DB result: {row}")
                    return row[0] if row else None
        else:
            with sqlite3.connect(DB_PATH) as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT user_email FROM oauth_sessions WHERE access_token = ?', (access_token,))
                row = cursor.fetchone()
                print(f"[AUTH] DB result: {row}")
                return row[0] if row else None
    except Exception as e:
        print(f"[AUTH] DB error in get_email_for_access_token: {e}")
        return None

class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # We only protect the MCP streaming endpoints
        if request.url.path in ["/sse", "/messages/"]:
            token = None
            auth_header = request.headers.get("Authorization")
            if auth_header and auth_header.startswith("Bearer "):
                token = auth_header.split(" ")[1]
            else:
                token = request.query_params.get("token")
                
            if not token:
                return JSONResponse({"error": "Unauthorized", "details": "Missing access token"}, status_code=401)
            
            email = get_email_for_access_token(token)
            
            if not email:
                return JSONResponse({"error": "Unauthorized", "details": "Invalid access token"}, status_code=401)
            
            # Save the email in context so the tools can magically read it
            user_email_var.set(email)
            
            # Record client connection activity
            try:
                user_agent = request.headers.get("user-agent", "")
                record_client_activity(email, user_agent)
            except Exception as e:
                print(f"Error recording client activity: {e}")
            
        return await call_next(request)

@mcp.tool()
def save_memory(content: str) -> str:
    """Saves a piece of information, a summary, or a memory into the AI's persistent storage for the authenticated user."""
    user_email = user_email_var.get()
    if not user_email:
        return json.dumps({"status": "error", "message": "Unauthorized. Cannot determine user."})

    try:
        timestamp = datetime.utcnow().isoformat() + "Z"
        if DATABASE_URL:
            with psycopg2.connect(DATABASE_URL) as conn:
                with conn.cursor() as cursor:
                    cursor.execute('INSERT INTO memories (timestamp, content, user_email) VALUES (%s, %s, %s) RETURNING id', (timestamp, content, user_email))
                    memory_id = cursor.fetchone()[0]
                conn.commit()
                return json.dumps({"status": "success", "message": "Memory saved successfully.", "id": memory_id, "user": user_email})
        else:
            with sqlite3.connect(DB_PATH) as conn:
                cursor = conn.cursor()
                cursor.execute('INSERT INTO memories (timestamp, content, user_email) VALUES (?, ?, ?)', (timestamp, content, user_email))
                conn.commit()
                return json.dumps({"status": "success", "message": "Memory saved successfully.", "id": cursor.lastrowid, "user": user_email})
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)})

@mcp.tool()
def search_memory(query: str) -> str:
    """Searches past memories based on a text query for the authenticated user."""
    user_email = user_email_var.get()
    if not user_email:
        return json.dumps({"status": "error", "message": "Unauthorized. Cannot determine user."})

    try:
        if DATABASE_URL:
            with psycopg2.connect(DATABASE_URL) as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute('SELECT id, timestamp, content FROM memories WHERE content ILIKE %s AND user_email = %s ORDER BY timestamp DESC', (f'%{query}%', user_email))
                    results = cursor.fetchall()
                    return json.dumps({"status": "success", "results": results}, indent=2)
        else:
            with sqlite3.connect(DB_PATH) as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT id, timestamp, content FROM memories WHERE content LIKE ? AND user_email = ? ORDER BY timestamp DESC', (f'%{query}%', user_email))
                results = [{"id": row[0], "timestamp": row[1], "content": row[2]} for row in cursor.fetchall()]
                return json.dumps({"status": "success", "results": results}, indent=2)
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)})

@mcp.tool()
def list_memories(limit: int = 10) -> str:
    """Lists the most recent memories for the authenticated user."""
    user_email = user_email_var.get()
    if not user_email:
        return json.dumps({"status": "error", "message": "Unauthorized. Cannot determine user."})

    try:
        if DATABASE_URL:
            with psycopg2.connect(DATABASE_URL) as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute('SELECT id, timestamp, content FROM memories WHERE user_email = %s ORDER BY timestamp DESC LIMIT %s', (user_email, limit))
                    results = cursor.fetchall()
                    return json.dumps({"status": "success", "results": results}, indent=2)
        else:
            with sqlite3.connect(DB_PATH) as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT id, timestamp, content FROM memories WHERE user_email = ? ORDER BY timestamp DESC LIMIT ?', (user_email, limit))
                results = [{"id": row[0], "timestamp": row[1], "content": row[2]} for row in cursor.fetchall()]
                return json.dumps({"status": "success", "results": results}, indent=2)
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)})
@mcp.custom_route("/static/{filename}", methods=["GET"])
async def serve_static(request: Request):
    """Serves static files from the public directory."""
    from starlette.responses import FileResponse, Response
    filename = request.path_params.get("filename", "")
    # Basic security: no path traversal
    if ".." in filename or "/" in filename:
        return Response("Forbidden", status_code=403)
    file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "public", filename)
    if os.path.isfile(file_path):
        return FileResponse(file_path)
    return Response("Not found", status_code=404)

@mcp.custom_route("/landing", methods=["GET"])
async def serve_landing(request: Request) -> HTMLResponse:
    """Serves the landing page."""
    try:
        landing_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "public", "landing.html")
        with open(landing_path, "r", encoding="utf-8") as f:
            html = f.read()
        return HTMLResponse(html)
    except Exception as e:
        return HTMLResponse(f"<h1>Error loading landing page: {str(e)}</h1>", status_code=500)

@mcp.custom_route("/pricing", methods=["GET"])
async def serve_pricing(request: Request) -> HTMLResponse:
    """Serves the pricing page."""
    try:
        pricing_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "public", "pricing.html")
        with open(pricing_path, "r", encoding="utf-8") as f:
            html = f.read()
        return HTMLResponse(html)
    except Exception as e:
        return HTMLResponse(f"<h1>Error loading pricing page: {str(e)}</h1>", status_code=500)

@mcp.custom_route("/mcp", methods=["GET"])
async def serve_mcp(request: Request) -> HTMLResponse:
    """Serves the MCP page."""
    try:
        mcp_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "public", "mcp.html")
        with open(mcp_path, "r", encoding="utf-8") as f:
            html = f.read()
        return HTMLResponse(html)
    except Exception as e:
        return HTMLResponse(f"<h1>Error loading mcp page: {str(e)}</h1>", status_code=500)

@mcp.custom_route("/privacy", methods=["GET"])
async def serve_privacy(request: Request) -> HTMLResponse:
    """Serves the privacy policy page."""
    try:
        privacy_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "public", "privacy.html")
        with open(privacy_path, "r", encoding="utf-8") as f:
            html = f.read()
        return HTMLResponse(html)
    except Exception as e:
        return HTMLResponse(f"<h1>Error loading privacy policy page: {str(e)}</h1>", status_code=500)

@mcp.custom_route("/terms", methods=["GET"])
async def serve_terms(request: Request) -> HTMLResponse:
    """Serves the terms of service page."""
    try:
        terms_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "public", "terms.html")
        with open(terms_path, "r", encoding="utf-8") as f:
            html = f.read()
        return HTMLResponse(html)
    except Exception as e:
        return HTMLResponse(f"<h1>Error loading terms of service page: {str(e)}</h1>", status_code=500)

@mcp.custom_route("/signup", methods=["GET"])
async def serve_signup(request: Request) -> HTMLResponse:
    """Serves the signup page."""
    try:
        signup_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "public", "signup.html")
        with open(signup_path, "r", encoding="utf-8") as f:
            html = f.read()
            
        # Inject Firebase config into the HTML
        html = html.replace("{{FIREBASE_API_KEY}}", os.environ.get("FIREBASE_API_KEY", ""))
        html = html.replace("{{FIREBASE_AUTH_DOMAIN}}", os.environ.get("FIREBASE_AUTH_DOMAIN", ""))
        html = html.replace("{{FIREBASE_PROJECT_ID}}", os.environ.get("FIREBASE_PROJECT_ID", ""))
        html = html.replace("{{FIREBASE_STORAGE_BUCKET}}", os.environ.get("FIREBASE_STORAGE_BUCKET", ""))
        html = html.replace("{{FIREBASE_MESSAGING_SENDER_ID}}", os.environ.get("FIREBASE_MESSAGING_SENDER_ID", ""))
        html = html.replace("{{FIREBASE_APP_ID}}", os.environ.get("FIREBASE_APP_ID", ""))
        
        return HTMLResponse(html)
    except Exception as e:
        return HTMLResponse(f"<h1>Error loading signup page: {str(e)}</h1>", status_code=500)

@mcp.custom_route("/signin", methods=["GET"])
async def serve_signin(request: Request) -> HTMLResponse:
    """Serves the signin page."""
    try:
        signin_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "public", "signin.html")
        with open(signin_path, "r", encoding="utf-8") as f:
            html = f.read()
            
        # Inject Firebase config into the HTML
        html = html.replace("{{FIREBASE_API_KEY}}", os.environ.get("FIREBASE_API_KEY", ""))
        html = html.replace("{{FIREBASE_AUTH_DOMAIN}}", os.environ.get("FIREBASE_AUTH_DOMAIN", ""))
        html = html.replace("{{FIREBASE_PROJECT_ID}}", os.environ.get("FIREBASE_PROJECT_ID", ""))
        html = html.replace("{{FIREBASE_STORAGE_BUCKET}}", os.environ.get("FIREBASE_STORAGE_BUCKET", ""))
        html = html.replace("{{FIREBASE_MESSAGING_SENDER_ID}}", os.environ.get("FIREBASE_MESSAGING_SENDER_ID", ""))
        html = html.replace("{{FIREBASE_APP_ID}}", os.environ.get("FIREBASE_APP_ID", ""))
        
        return HTMLResponse(html)
    except Exception as e:
        return HTMLResponse(f"<h1>Error loading signin page: {str(e)}</h1>", status_code=500)


@mcp.custom_route("/dashboard", methods=["GET"])
async def serve_dashboard(request: Request) -> HTMLResponse:
    """Serves the main dashboard UI."""
    try:
        index_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "public", "index.html")
        with open(index_path, "r", encoding="utf-8") as f:
            html = f.read()
            
        # Inject Firebase config into the HTML
        html = html.replace("{{FIREBASE_API_KEY}}", os.environ.get("FIREBASE_API_KEY", ""))
        html = html.replace("{{FIREBASE_AUTH_DOMAIN}}", os.environ.get("FIREBASE_AUTH_DOMAIN", ""))
        html = html.replace("{{FIREBASE_PROJECT_ID}}", os.environ.get("FIREBASE_PROJECT_ID", ""))
        html = html.replace("{{FIREBASE_STORAGE_BUCKET}}", os.environ.get("FIREBASE_STORAGE_BUCKET", ""))
        html = html.replace("{{FIREBASE_MESSAGING_SENDER_ID}}", os.environ.get("FIREBASE_MESSAGING_SENDER_ID", ""))
        html = html.replace("{{FIREBASE_APP_ID}}", os.environ.get("FIREBASE_APP_ID", ""))
        
        return HTMLResponse(html)
    except Exception as e:
        return HTMLResponse(f"<h1>Error loading dashboard: {str(e)}</h1>", status_code=500)

@mcp.custom_route("/", methods=["GET"])
async def serve_root(request: Request) -> RedirectResponse:
    """Redirects root to the landing page."""
    return RedirectResponse(url="/landing")


@mcp.custom_route("/api/memories", methods=["GET"])
async def api_memories(request: Request) -> JSONResponse:
    """API endpoint for the dashboard to fetch memories using a Firebase ID token."""
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return JSONResponse({"status": "error", "message": "Missing Bearer token"}, status_code=401)
        
    id_token = auth_header.split(" ")[1]
    
    try:
        decoded_token = firebase_auth.verify_id_token(id_token)
        email = decoded_token.get("email")
        if not email:
            return JSONResponse({"status": "error", "message": "No email found in token"}, status_code=400)
            
        if DATABASE_URL:
            with psycopg2.connect(DATABASE_URL) as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute('SELECT id, timestamp, content FROM memories WHERE user_email = %s ORDER BY timestamp DESC', (email,))
                    results = cursor.fetchall()
        else:
            with sqlite3.connect(DB_PATH) as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT id, timestamp, content FROM memories WHERE user_email = ? ORDER BY timestamp DESC', (email,))
                results = [{"id": row[0], "timestamp": row[1], "content": row[2]} for row in cursor.fetchall()]
                
        return JSONResponse({"status": "success", "results": results})
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=401)

@mcp.custom_route("/api/generate_token", methods=["POST"])
async def api_generate_token(request: Request) -> JSONResponse:
    """Generates a personal access token for clients that don't support OAuth."""
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return JSONResponse({"status": "error", "message": "Missing Bearer token"}, status_code=401)
        
    id_token = auth_header.split(" ")[1]
    
    try:
        decoded_token = firebase_auth.verify_id_token(id_token)
        email = decoded_token.get("email")
        if not email:
            return JSONResponse({"status": "error", "message": "No email found in token"}, status_code=400)
            
        access_token = "memorie-" + str(uuid.uuid4())
        auth_code = "pat-" + str(uuid.uuid4())
        created_at = datetime.utcnow().isoformat()
        
        if DATABASE_URL:
            with psycopg2.connect(DATABASE_URL) as conn:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT access_token FROM oauth_sessions WHERE user_email = %s AND auth_code LIKE 'pat-%%' LIMIT 1", (email,))
                    row = cursor.fetchone()
                    if row:
                        return JSONResponse({"status": "success", "token": row[0]})
                        
                    cursor.execute('INSERT INTO oauth_sessions (auth_code, access_token, user_email, created_at) VALUES (%s, %s, %s, %s)', (auth_code, access_token, email, created_at))
                conn.commit()
        else:
            with sqlite3.connect(DB_PATH) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT access_token FROM oauth_sessions WHERE user_email = ? AND auth_code LIKE 'pat-%' LIMIT 1", (email,))
                row = cursor.fetchone()
                if row:
                    return JSONResponse({"status": "success", "token": row[0]})
                    
                cursor.execute('INSERT INTO oauth_sessions (auth_code, access_token, user_email, created_at) VALUES (?, ?, ?, ?)', (auth_code, access_token, email, created_at))
                conn.commit()
                
        return JSONResponse({"status": "success", "token": access_token})
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)

@mcp.custom_route("/api/connected_clients", methods=["GET"])
async def api_connected_clients(request: Request) -> JSONResponse:
    """API endpoint for the dashboard to fetch the list of connected clients and their last active status."""
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return JSONResponse({"status": "error", "message": "Missing Bearer token"}, status_code=401)
        
    id_token = auth_header.split(" ")[1]
    
    try:
        decoded_token = firebase_auth.verify_id_token(id_token)
        email = decoded_token.get("email")
        if not email:
            return JSONResponse({"status": "error", "message": "No email found in token"}, status_code=400)
            
        results = []
        if DATABASE_URL:
            with psycopg2.connect(DATABASE_URL) as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute('SELECT client_name, last_active, user_agent FROM client_connections WHERE user_email = %s ORDER BY last_active DESC', (email,))
                    results = cursor.fetchall()
        else:
            with sqlite3.connect(DB_PATH) as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT client_name, last_active, user_agent FROM client_connections WHERE user_email = ? ORDER BY last_active DESC', (email,))
                results = [{"client_name": row[0], "last_active": row[1], "user_agent": row[2]} for row in cursor.fetchall()]
                
        return JSONResponse({"status": "success", "results": results})
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)

@mcp.custom_route("/.well-known/oauth-authorization-server", methods=["GET"])
async def oauth_authorization_server_metadata(request: Request) -> JSONResponse:
    """OAuth 2.0 Authorization Server Metadata (RFC 8414). Required by Claude.ai and other MCP clients."""
    base_url = str(request.base_url).rstrip("/")
    return JSONResponse({
        "issuer": base_url,
        "authorization_endpoint": f"{base_url}/authorize",
        "token_endpoint": f"{base_url}/token",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code"],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": ["none"],
        "scopes_supported": ["mcp"],
    })

@mcp.custom_route("/.well-known/oauth-protected-resource", methods=["GET"])
async def oauth_protected_resource_metadata(request: Request) -> JSONResponse:
    """OAuth 2.0 Protected Resource Metadata (RFC 9728). Required by Claude.ai to discover the auth server."""
    base_url = str(request.base_url).rstrip("/")
    return JSONResponse({
        "resource": base_url,
        "authorization_servers": [base_url],
        "bearer_methods_supported": ["header"],
        "resource_documentation": f"{base_url}/mcp",
    })

@mcp.custom_route("/authorize", methods=["GET"])
async def authorize(request: Request) -> HTMLResponse:
    """The OAuth 2.0 Authorization Endpoint. Displays the Firebase Login page."""
    redirect_uri = request.query_params.get("redirect_uri")
    state = request.query_params.get("state")
    
    if not redirect_uri:
        return HTMLResponse("<h1>Missing redirect_uri parameter</h1>", status_code=400)
    
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Login - Connect AI</title>
        <script src="https://www.gstatic.com/firebasejs/9.22.2/firebase-app-compat.js"></script>
        <script src="https://www.gstatic.com/firebasejs/9.22.2/firebase-auth-compat.js"></script>
        <script src="https://www.gstatic.com/firebasejs/ui/6.0.2/firebase-ui-auth.js"></script>
        <link type="text/css" rel="stylesheet" href="https://www.gstatic.com/firebasejs/ui/6.0.2/firebase-ui-auth.css" />
        <style>
            body {{ font-family: sans-serif; display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100vh; background-color: #f5f5f5; }}
            .container {{ background: white; padding: 2rem; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); text-align: center; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h2>Authorize AI Access</h2>
            <div id="firebaseui-auth-container"></div>
            <div id="loader">Loading...</div>
        </div>

        <script>
            const firebaseConfig = {{
                apiKey: "{os.environ.get('FIREBASE_API_KEY', '')}",
                authDomain: "{os.environ.get('FIREBASE_AUTH_DOMAIN', '')}",
                projectId: "{os.environ.get('FIREBASE_PROJECT_ID', '')}",
                storageBucket: "{os.environ.get('FIREBASE_STORAGE_BUCKET', '')}",
                messagingSenderId: "{os.environ.get('FIREBASE_MESSAGING_SENDER_ID', '')}",
                appId: "{os.environ.get('FIREBASE_APP_ID', '')}"
            }};
            firebase.initializeApp(firebaseConfig);

            const ui = new firebaseui.auth.AuthUI(firebase.auth());
            const uiConfig = {{
                callbacks: {{
                    signInSuccessWithAuthResult: function(authResult, redirectUrl) {{
                        document.getElementById('firebaseui-auth-container').style.display = 'none';
                        document.getElementById('loader').innerText = 'Verifying and redirecting...';
                        
                        authResult.user.getIdToken().then(function(idToken) {{
                            fetch('/oauth/verify_firebase_token', {{
                                method: 'POST',
                                headers: {{ 'Content-Type': 'application/json' }},
                                body: JSON.stringify({{ idToken: idToken }})
                            }})
                            .then(response => response.json())
                            .then(data => {{
                                if(data.status === 'success') {{
                                    // Complete OAuth flow by redirecting back with code and state
                                    const sep = "{redirect_uri}".includes("?") ? "&" : "?";
                                    const redirectUri = "{redirect_uri}" + sep + "code=" + data.auth_code + "&state={state}";
                                    window.location.href = redirectUri;
                                }} else {{
                                    document.getElementById('loader').innerText = 'Verification failed: ' + data.message;
                                }}
                            }});
                        }});
                        return false;
                    }},
                    uiShown: function() {{ document.getElementById('loader').style.display = 'none'; }}
                }},
                signInFlow: 'popup',
                signInOptions: [ 
                    {{
                        provider: firebase.auth.GoogleAuthProvider.PROVIDER_ID,
                        customParameters: {{ prompt: 'select_account' }}
                    }}
                ]
            }};
            ui.start('#firebaseui-auth-container', uiConfig);
        </script>
    </body>
    </html>
    """
    return HTMLResponse(html)

@mcp.custom_route("/oauth/verify_firebase_token", methods=["POST"])
async def oauth_verify_firebase(request: Request) -> JSONResponse:
    """Internal route. Verifies Firebase token and creates an OAuth authorization code."""
    try:
        body = await request.json()
        id_token = body.get("idToken")
        
        if not id_token:
            return JSONResponse({"status": "error", "message": "Missing idToken"}, status_code=400)
            
        decoded_token = firebase_auth.verify_id_token(id_token)
        email = decoded_token.get("email")
        if not email:
            return JSONResponse({"status": "error", "message": "No email found in token"}, status_code=400)
            
        auth_code = str(uuid.uuid4())
        created_at = datetime.utcnow().isoformat()
        
        if DATABASE_URL:
            with psycopg2.connect(DATABASE_URL) as conn:
                with conn.cursor() as cursor:
                    cursor.execute('INSERT INTO oauth_sessions (auth_code, user_email, created_at) VALUES (%s, %s, %s)', (auth_code, email, created_at))
                conn.commit()
        else:
            with sqlite3.connect(DB_PATH) as conn:
                cursor = conn.cursor()
                cursor.execute('INSERT INTO oauth_sessions (auth_code, user_email, created_at) VALUES (?, ?, ?)', (auth_code, email, created_at))
                conn.commit()
                
        return JSONResponse({"status": "success", "auth_code": auth_code})
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)

@mcp.custom_route("/token", methods=["POST", "OPTIONS"])
async def token_endpoint(request: Request) -> JSONResponse:
    """The OAuth 2.0 Token Endpoint. Exchanges an auth_code for an access_token."""
    # Support CORS for browser-based OAuth flows if needed
    if request.method == "OPTIONS":
        return JSONResponse({}, headers={"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Methods": "POST", "Access-Control-Allow-Headers": "Content-Type"})
        
    try:
        content_type = request.headers.get("content-type", "")
        if "application/x-www-form-urlencoded" in content_type:
            form = await request.form()
            code = form.get("code")
        else:
            body = await request.json()
            code = body.get("code")
    except:
        return JSONResponse({"error": "invalid_request"}, status_code=400)
            
    if not code:
        return JSONResponse({"error": "invalid_request", "error_description": "Missing code"}, status_code=400)
        
    access_token = str(uuid.uuid4()) + "-token"
    
    # Verify auth_code and swap it for access_token
    updated = False
    if DATABASE_URL:
        with psycopg2.connect(DATABASE_URL) as conn:
            with conn.cursor() as cursor:
                cursor.execute('UPDATE oauth_sessions SET access_token = %s WHERE auth_code = %s RETURNING user_email', (access_token, code))
                if cursor.fetchone():
                    updated = True
            conn.commit()
    else:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute('UPDATE oauth_sessions SET access_token = ? WHERE auth_code = ?', (access_token, code))
            if cursor.rowcount > 0:
                updated = True
            conn.commit()
            
    if not updated:
        print(f"[TOKEN] No row found for auth_code: {code[:16] if code else 'None'}...")
        return JSONResponse({"error": "invalid_grant"}, status_code=400)

    print(f"[TOKEN] Stored access_token: {access_token[:16]}... for code: {code[:16] if code else 'None'}... (db={'pg' if DATABASE_URL else 'sqlite'})")
    return JSONResponse({
        "access_token": access_token,
        "token_type": "Bearer",
        "expires_in": 31536000 # 1 year
    }, headers={"Access-Control-Allow-Origin": "*"})


if __name__ == "__main__":
    app = mcp.sse_app()
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=False, allow_methods=["*"], allow_headers=["*"])
    app.add_middleware(AuthMiddleware)
    
    port = int(os.environ.get("PORT", "8000"))
    print(f"Starting MCP Server with Native OAuth on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
