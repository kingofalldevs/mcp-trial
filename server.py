import os
import json
import uuid
import sqlite3
import psycopg2
from datetime import datetime
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv
from cryptography.fernet import Fernet

import contextvars

import firebase_admin
from firebase_admin import credentials, auth as firebase_auth

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.responses import JSONResponse, HTMLResponse, RedirectResponse, Response
from starlette.requests import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.cors import CORSMiddleware
import uvicorn
load_dotenv()

# Set up symmetric encryption key for secure user memories at rest
ENCRYPTION_KEY = os.environ.get("ENCRYPTION_KEY")
if not ENCRYPTION_KEY:
    try:
        ENCRYPTION_KEY = Fernet.generate_key().decode()
        env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
        if os.path.exists(env_path):
            with open(env_path, "a") as f:
                f.write(f"\nENCRYPTION_KEY={ENCRYPTION_KEY}\n")
        else:
            with open(env_path, "w") as f:
                f.write(f"ENCRYPTION_KEY={ENCRYPTION_KEY}\n")
        print("Generated new ENCRYPTION_KEY and saved to .env")
    except Exception as e:
        print(f"Error auto-generating ENCRYPTION_KEY: {e}")
        ENCRYPTION_KEY = ""

def encrypt_content(plain_text: str) -> str:
    """Encrypts text using the server-wide Fernet key."""
    if not plain_text or not ENCRYPTION_KEY:
        return plain_text or ""
    try:
        f = Fernet(ENCRYPTION_KEY.encode())
        return f.encrypt(plain_text.encode()).decode("utf-8")
    except Exception as e:
        print(f"[CRYPTO] Encryption error: {e}")
        return plain_text

def decrypt_content(encrypted_text: str) -> str:
    """Decrypts text. Falls back to plain text if decryption fails (for legacy memories)."""
    if not encrypted_text or not ENCRYPTION_KEY:
        return encrypted_text or ""
    try:
        f = Fernet(ENCRYPTION_KEY.encode())
        return f.decrypt(encrypted_text.encode()).decode("utf-8")
    except Exception:
        # Fallback to plain text for legacy memories
        return encrypted_text
# We use a ContextVar to store the user's email securely across the async call chain
user_email_var = contextvars.ContextVar("user_email", default=None)
client_name_var = contextvars.ContextVar("client_name", default="Generic AI")

mcp = FastMCP(
    "ai-memory-server",
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False)
)

DATABASE_URL = os.environ.get("DATABASE_URL")
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "memory.db")

# Admin emails configuration
ADMIN_EMAILS_RAW = os.environ.get("ADMIN_EMAILS", "")
ADMIN_EMAILS = [email.strip().lower() for email in ADMIN_EMAILS_RAW.split(",") if email.strip()]

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
                
                cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_name='memories' AND column_name='client_name'")
                if not cursor.fetchone():
                    cursor.execute("ALTER TABLE memories ADD COLUMN client_name TEXT DEFAULT 'Generic AI'")
                
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
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS landing_events (
                        id SERIAL PRIMARY KEY,
                        session_id TEXT NOT NULL,
                        user_email TEXT DEFAULT '',
                        event_type TEXT NOT NULL,
                        target_name TEXT NOT NULL,
                        timestamp TEXT NOT NULL,
                        user_agent TEXT,
                        referrer TEXT DEFAULT 'Direct',
                        ip_address TEXT DEFAULT '',
                        location TEXT DEFAULT 'Unknown'
                    )
                ''')
                cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_name='landing_events' AND column_name='referrer'")
                if not cursor.fetchone():
                    cursor.execute("ALTER TABLE landing_events ADD COLUMN referrer TEXT DEFAULT 'Direct'")
                
                cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_name='landing_events' AND column_name='ip_address'")
                if not cursor.fetchone():
                    cursor.execute("ALTER TABLE landing_events ADD COLUMN ip_address TEXT DEFAULT ''")
                
                cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_name='landing_events' AND column_name='location'")
                if not cursor.fetchone():
                    cursor.execute("ALTER TABLE landing_events ADD COLUMN location TEXT DEFAULT 'Unknown'")
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
            if 'client_name' not in columns:
                cursor.execute("ALTER TABLE memories ADD COLUMN client_name TEXT DEFAULT 'Generic AI'")
                
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
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS landing_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    user_email TEXT DEFAULT '',
                    event_type TEXT NOT NULL,
                    target_name TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    user_agent TEXT,
                    referrer TEXT DEFAULT 'Direct',
                    ip_address TEXT DEFAULT '',
                    location TEXT DEFAULT 'Unknown'
                )
            ''')
            cursor.execute("PRAGMA table_info(landing_events)")
            le_columns = [info[1] for info in cursor.fetchall()]
            if 'referrer' not in le_columns:
                cursor.execute("ALTER TABLE landing_events ADD COLUMN referrer TEXT DEFAULT 'Direct'")
            if 'ip_address' not in le_columns:
                cursor.execute("ALTER TABLE landing_events ADD COLUMN ip_address TEXT DEFAULT ''")
            if 'location' not in le_columns:
                cursor.execute("ALTER TABLE landing_events ADD COLUMN location TEXT DEFAULT 'Unknown'")
            conn.commit()

init_db()

def get_client_name_from_user_agent(user_agent: str) -> str:
    """Classifies a user agent string to identify the client name."""
    ua = (user_agent or "").lower()
    if "claude" in ua:
        return "Claude"
    elif "chatgpt" in ua or "openai" in ua:
        return "ChatGPT"
    elif "cursor" in ua:
        return "Cursor"
    elif "windsurf" in ua:
        return "Windsurf"
    elif "manus" in ua:
        return "Manus"
    else:
        if "vscode" in ua:
            return "Cursor / Windsurf (VSCode)"
        elif "postman" in ua:
            return "Postman / API Test"
        elif "python" in ua:
            return "Python Client"
    return "Generic AI"

def record_client_activity(email: str, user_agent: str):
    """Logs the client name and activity time."""
    client_name = get_client_name_from_user_agent(user_agent)
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
        if request.method != "OPTIONS" and request.url.path in ["/sse", "/messages", "/messages/"]:
            token = None
            auth_header = request.headers.get("Authorization")
            print(f"[MW] {request.method} {request.url.path} | Auth header: {repr(auth_header)} | Query params: {dict(request.query_params)}")
            if auth_header and auth_header.startswith("Bearer "):
                token = auth_header.split(" ")[1]
            else:
                # Check common alternative token param names
                token = (request.query_params.get("token") or
                         request.query_params.get("access_token") or
                         request.query_params.get("api_key"))
                
            if not token:
                print(f"[MW] All headers: { {k: v for k, v in request.headers.items()} }")
                base_url = str(request.base_url).rstrip("/")
                auth_header_val = f'Bearer resource_metadata="{base_url}/.well-known/oauth-protected-resource"'
                return JSONResponse({"error": "Unauthorized", "details": "Missing access token"}, status_code=401, headers={"WWW-Authenticate": auth_header_val})
            
            email = get_email_for_access_token(token)
            
            if not email:
                base_url = str(request.base_url).rstrip("/")
                auth_header_val = f'Bearer resource_metadata="{base_url}/.well-known/oauth-protected-resource", error="invalid_token"'
                return JSONResponse({"error": "Unauthorized", "details": "Invalid access token"}, status_code=401, headers={"WWW-Authenticate": auth_header_val})
            
            # Save the email in context so the tools can magically read it
            user_email_var.set(email)
            
            user_agent = request.headers.get("user-agent", "")
            client_name = get_client_name_from_user_agent(user_agent)
            client_name_var.set(client_name)
            
            # Record client connection activity
            try:
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

    client_name = client_name_var.get()
    encrypted_content = encrypt_content(content)

    try:
        timestamp = datetime.utcnow().isoformat() + "Z"
        if DATABASE_URL:
            with psycopg2.connect(DATABASE_URL) as conn:
                with conn.cursor() as cursor:
                    cursor.execute('INSERT INTO memories (timestamp, content, user_email, client_name) VALUES (%s, %s, %s, %s) RETURNING id', (timestamp, encrypted_content, user_email, client_name))
                    memory_id = cursor.fetchone()[0]
                conn.commit()
                return json.dumps({"status": "success", "message": "Memory saved successfully.", "id": memory_id})
        else:
            with sqlite3.connect(DB_PATH) as conn:
                cursor = conn.cursor()
                cursor.execute('INSERT INTO memories (timestamp, content, user_email, client_name) VALUES (?, ?, ?, ?)', (timestamp, encrypted_content, user_email, client_name))
                conn.commit()
                return json.dumps({"status": "success", "message": "Memory saved successfully.", "id": cursor.lastrowid})
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)})

@mcp.tool()
def search_memory(query: str, client_name: str = None) -> str:
    """Searches past memories based on a text query for the authenticated user. Optionally filter by client_name (e.g. 'Claude', 'ChatGPT', 'Cursor', etc.)."""
    user_email = user_email_var.get()
    if not user_email:
        return json.dumps({"status": "error", "message": "Unauthorized. Cannot determine user."})

    try:
        # Fetch all user memories from db to perform in-memory decryption and search
        if DATABASE_URL:
            with psycopg2.connect(DATABASE_URL) as conn:
                with conn.cursor() as cursor:
                    if client_name:
                        cursor.execute('SELECT id, timestamp, content, client_name FROM memories WHERE user_email = %s AND client_name ILIKE %s ORDER BY timestamp DESC', (user_email, f'%{client_name}%'))
                    else:
                        cursor.execute('SELECT id, timestamp, content, client_name FROM memories WHERE user_email = %s ORDER BY timestamp DESC', (user_email,))
                    rows = cursor.fetchall()
        else:
            with sqlite3.connect(DB_PATH) as conn:
                cursor = conn.cursor()
                if client_name:
                    cursor.execute('SELECT id, timestamp, content, client_name FROM memories WHERE user_email = ? AND client_name LIKE ? ORDER BY timestamp DESC', (user_email, f'%{client_name}%'))
                else:
                    cursor.execute('SELECT id, timestamp, content, client_name FROM memories WHERE user_email = ? ORDER BY timestamp DESC', (user_email,))
                rows = cursor.fetchall()
                
        # Decrypt content and filter by query in-memory
        results = []
        for r in rows:
            decrypted = decrypt_content(r[2])
            if not query or query.lower() in decrypted.lower():
                results.append({
                    "id": r[0],
                    "timestamp": r[1],
                    "content": decrypted,
                    "client_name": r[3]
                })
        return json.dumps({"status": "success", "results": results}, indent=2)
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)})

@mcp.tool()
def list_memories(limit: int = 10, client_name: str = None) -> str:
    """Lists the most recent memories for the authenticated user. Optionally filter by client_name (e.g. 'Claude', 'ChatGPT', 'Cursor', etc.)."""
    user_email = user_email_var.get()
    if not user_email:
        return json.dumps({"status": "error", "message": "Unauthorized. Cannot determine user."})

    try:
        if DATABASE_URL:
            with psycopg2.connect(DATABASE_URL) as conn:
                with conn.cursor() as cursor:
                    if client_name:
                        cursor.execute('SELECT id, timestamp, content, client_name FROM memories WHERE user_email = %s AND client_name ILIKE %s ORDER BY timestamp DESC LIMIT %s', (user_email, f'%{client_name}%', limit))
                    else:
                        cursor.execute('SELECT id, timestamp, content, client_name FROM memories WHERE user_email = %s ORDER BY timestamp DESC LIMIT %s', (user_email, limit))
                    rows = cursor.fetchall()
        else:
            with sqlite3.connect(DB_PATH) as conn:
                cursor = conn.cursor()
                if client_name:
                    cursor.execute('SELECT id, timestamp, content, client_name FROM memories WHERE user_email = ? AND client_name LIKE ? ORDER BY timestamp DESC LIMIT ?', (user_email, f'%{client_name}%', limit))
                else:
                    cursor.execute('SELECT id, timestamp, content, client_name FROM memories WHERE user_email = ? ORDER BY timestamp DESC LIMIT ?', (user_email, limit))
                rows = cursor.fetchall()

        results = []
        for r in rows:
            results.append({
                "id": r[0],
                "timestamp": r[1],
                "content": decrypt_content(r[2]),
                "client_name": r[3]
            })
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
def inject_firebase_config(html: str) -> str:
    """Injects Firebase configuration from environment variables into HTML template."""
    html = html.replace("{{FIREBASE_API_KEY}}", os.environ.get("FIREBASE_API_KEY", ""))
    html = html.replace("{{FIREBASE_AUTH_DOMAIN}}", os.environ.get("FIREBASE_AUTH_DOMAIN", ""))
    html = html.replace("{{FIREBASE_PROJECT_ID}}", os.environ.get("FIREBASE_PROJECT_ID", ""))
    html = html.replace("{{FIREBASE_STORAGE_BUCKET}}", os.environ.get("FIREBASE_STORAGE_BUCKET", ""))
    html = html.replace("{{FIREBASE_MESSAGING_SENDER_ID}}", os.environ.get("FIREBASE_MESSAGING_SENDER_ID", ""))
    html = html.replace("{{FIREBASE_APP_ID}}", os.environ.get("FIREBASE_APP_ID", ""))
    html = html.replace("{{FIREBASE_MEASUREMENT_ID}}", os.environ.get("FIREBASE_MEASUREMENT_ID", ""))
    return html

@mcp.custom_route("/landing", methods=["GET"])
async def serve_landing(request: Request) -> HTMLResponse:
    """Serves the landing page."""
    try:
        landing_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "public", "landing.html")
        with open(landing_path, "r", encoding="utf-8") as f:
            html = f.read()
        return HTMLResponse(inject_firebase_config(html))
    except Exception as e:
        return HTMLResponse(f"<h1>Error loading landing page: {str(e)}</h1>", status_code=500)

@mcp.custom_route("/pricing", methods=["GET"])
async def serve_pricing(request: Request) -> HTMLResponse:
    """Serves the pricing page."""
    try:
        pricing_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "public", "pricing.html")
        with open(pricing_path, "r", encoding="utf-8") as f:
            html = f.read()
        return HTMLResponse(inject_firebase_config(html))
    except Exception as e:
        return HTMLResponse(f"<h1>Error loading pricing page: {str(e)}</h1>", status_code=500)

@mcp.custom_route("/mcp", methods=["GET"])
async def serve_mcp(request: Request) -> HTMLResponse:
    """Serves the MCP page."""
    try:
        mcp_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "public", "mcp.html")
        with open(mcp_path, "r", encoding="utf-8") as f:
            html = f.read()
        return HTMLResponse(inject_firebase_config(html))
    except Exception as e:
        return HTMLResponse(f"<h1>Error loading mcp page: {str(e)}</h1>", status_code=500)

@mcp.custom_route("/privacy", methods=["GET"])
async def serve_privacy(request: Request) -> HTMLResponse:
    """Serves the privacy policy page."""
    try:
        privacy_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "public", "privacy.html")
        with open(privacy_path, "r", encoding="utf-8") as f:
            html = f.read()
        return HTMLResponse(inject_firebase_config(html))
    except Exception as e:
        return HTMLResponse(f"<h1>Error loading privacy policy page: {str(e)}</h1>", status_code=500)

@mcp.custom_route("/terms", methods=["GET"])
async def serve_terms(request: Request) -> HTMLResponse:
    """Serves the terms of service page."""
    try:
        terms_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "public", "terms.html")
        with open(terms_path, "r", encoding="utf-8") as f:
            html = f.read()
        return HTMLResponse(inject_firebase_config(html))
    except Exception as e:
        return HTMLResponse(f"<h1>Error loading terms of service page: {str(e)}</h1>", status_code=500)

@mcp.custom_route("/signup", methods=["GET"])
async def serve_signup(request: Request) -> HTMLResponse:
    """Serves the signup page."""
    try:
        signup_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "public", "signup.html")
        with open(signup_path, "r", encoding="utf-8") as f:
            html = f.read()
            
        return HTMLResponse(inject_firebase_config(html))
    except Exception as e:
        return HTMLResponse(f"<h1>Error loading signup page: {str(e)}</h1>", status_code=500)

@mcp.custom_route("/signin", methods=["GET"])
async def serve_signin(request: Request) -> HTMLResponse:
    """Serves the signin page."""
    try:
        signin_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "public", "signin.html")
        with open(signin_path, "r", encoding="utf-8") as f:
            html = f.read()
            
        return HTMLResponse(inject_firebase_config(html))
    except Exception as e:
        return HTMLResponse(f"<h1>Error loading signin page: {str(e)}</h1>", status_code=500)


@mcp.custom_route("/dashboard", methods=["GET"])
async def serve_dashboard(request: Request) -> HTMLResponse:
    """Serves the main dashboard UI."""
    try:
        index_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "public", "index.html")
        with open(index_path, "r", encoding="utf-8") as f:
            html = f.read()
            
        return HTMLResponse(inject_firebase_config(html))
    except Exception as e:
        return HTMLResponse(f"<h1>Error loading dashboard: {str(e)}</h1>", status_code=500)


@mcp.custom_route("/meadmin", methods=["GET"])
async def serve_meadmin(request: Request) -> HTMLResponse:
    """Serves the admin dashboard UI."""
    try:
        meadmin_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "public", "meadmin.html")
        with open(meadmin_path, "r", encoding="utf-8") as f:
            html = f.read()
            
        return HTMLResponse(inject_firebase_config(html))
    except Exception as e:
        return HTMLResponse(f"<h1>Error loading admin dashboard: {str(e)}</h1>", status_code=500)


@mcp.custom_route("/api/admin/stats", methods=["GET"])
async def api_admin_stats(request: Request) -> JSONResponse:
    """API endpoint for the admin dashboard to fetch overall statistics."""
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return JSONResponse({"status": "error", "message": "Missing Bearer token"}, status_code=401)
        
    id_token = auth_header.split(" ")[1]
    
    try:
        decoded_token = firebase_auth.verify_id_token(id_token)
        email = decoded_token.get("email")
        if not email:
            return JSONResponse({"status": "error", "message": "No email found in token"}, status_code=400)
            
        email_lower = email.strip().lower()
        
        # Check authorization
        is_dev_mode = len(ADMIN_EMAILS) == 0
        if not is_dev_mode and email_lower not in ADMIN_EMAILS:
            return JSONResponse({"status": "error", "message": f"User {email} is not authorized as an administrator."}, status_code=403)
            
        db_engine = "PostgreSQL" if DATABASE_URL else "SQLite"
        
        if DATABASE_URL:
            with psycopg2.connect(DATABASE_URL) as conn:
                with conn.cursor() as cursor:
                    # 1. Total memories
                    cursor.execute("SELECT COUNT(*) FROM memories")
                    total_memories = cursor.fetchone()[0]
                    
                    # 2. Total sessions
                    cursor.execute("SELECT COUNT(*) FROM oauth_sessions")
                    total_sessions = cursor.fetchone()[0]
                    
                    # 3. All emails
                    cursor.execute("""
                        SELECT DISTINCT user_email FROM oauth_sessions WHERE user_email IS NOT NULL AND user_email != ''
                        UNION
                        SELECT DISTINCT user_email FROM client_connections WHERE user_email IS NOT NULL AND user_email != ''
                        UNION
                        SELECT DISTINCT user_email FROM memories WHERE user_email IS NOT NULL AND user_email != ''
                    """)
                    all_emails = [row[0] for row in cursor.fetchall()]
                    total_users = len(all_emails)
                    
                    # 4. Client connections
                    cursor.execute("SELECT user_email, client_name, last_active, user_agent FROM client_connections")
                    connections_rows = cursor.fetchall()
                    
                    # 5. Client breakdown
                    cursor.execute("SELECT client_name, COUNT(*) FROM memories GROUP BY client_name ORDER BY COUNT(*) DESC")
                    breakdown_rows = cursor.fetchall()
                    
                    # 6. Recent memories
                    cursor.execute("SELECT user_email, client_name, timestamp, content FROM memories ORDER BY timestamp DESC LIMIT 20")
                    recent_memories_rows = cursor.fetchall()

                    # 7. Landing Page Analytics Counts
                    cursor.execute("SELECT COUNT(*) FROM landing_events")
                    landing_total_events = cursor.fetchone()[0]
                    
                    cursor.execute("SELECT COUNT(*) FROM landing_events WHERE event_type = 'copy_prompt'")
                    landing_total_copies = cursor.fetchone()[0]
                    
                    cursor.execute("SELECT COUNT(DISTINCT session_id) FROM landing_events")
                    landing_total_sessions = cursor.fetchone()[0]
                    
                    # 8. Prompts copies breakdown
                    cursor.execute("SELECT target_name, COUNT(*) FROM landing_events WHERE event_type = 'copy_prompt' GROUP BY target_name ORDER BY COUNT(*) DESC")
                    landing_prompt_rows = cursor.fetchall()
                    
                    # 9. Clicks breakdown
                    cursor.execute("SELECT target_name, COUNT(*) FROM landing_events WHERE event_type IN ('click_button', 'click_link') GROUP BY target_name ORDER BY COUNT(*) DESC")
                    landing_clicks_rows = cursor.fetchall()
                    
                    # 10. Recent landing events
                    cursor.execute("SELECT session_id, user_email, event_type, target_name, timestamp, user_agent, referrer, ip_address, location FROM landing_events ORDER BY timestamp DESC LIMIT 30")
                    landing_recent_rows = cursor.fetchall()
        else:
            with sqlite3.connect(DB_PATH) as conn:
                cursor = conn.cursor()
                # 1. Total memories
                cursor.execute("SELECT COUNT(*) FROM memories")
                total_memories = cursor.fetchone()[0]
                
                # 2. Total sessions
                cursor.execute("SELECT COUNT(*) FROM oauth_sessions")
                total_sessions = cursor.fetchone()[0]
                
                # 3. All emails
                cursor.execute("""
                    SELECT DISTINCT user_email FROM oauth_sessions WHERE user_email IS NOT NULL AND user_email != ''
                    UNION
                    SELECT DISTINCT user_email FROM client_connections WHERE user_email IS NOT NULL AND user_email != ''
                    UNION
                    SELECT DISTINCT user_email FROM memories WHERE user_email IS NOT NULL AND user_email != ''
                """)
                all_emails = [row[0] for row in cursor.fetchall()]
                total_users = len(all_emails)
                
                # 4. Client connections
                cursor.execute("SELECT user_email, client_name, last_active, user_agent FROM client_connections")
                connections_rows = cursor.fetchall()
                
                # 5. Client breakdown
                cursor.execute("SELECT client_name, COUNT(*) FROM memories GROUP BY client_name ORDER BY COUNT(*) DESC")
                breakdown_rows = cursor.fetchall()
                
                # 6. Recent memories
                cursor.execute("SELECT user_email, client_name, timestamp, content FROM memories ORDER BY timestamp DESC LIMIT 20")
                recent_memories_rows = cursor.fetchall()

                # 7. Landing Page Analytics Counts
                cursor.execute("SELECT COUNT(*) FROM landing_events")
                landing_total_events = cursor.fetchone()[0]
                
                cursor.execute("SELECT COUNT(*) FROM landing_events WHERE event_type = 'copy_prompt'")
                landing_total_copies = cursor.fetchone()[0]
                
                cursor.execute("SELECT COUNT(DISTINCT session_id) FROM landing_events")
                landing_total_sessions = cursor.fetchone()[0]
                
                # 8. Prompts copies breakdown
                cursor.execute("SELECT target_name, COUNT(*) FROM landing_events WHERE event_type = 'copy_prompt' GROUP BY target_name ORDER BY COUNT(*) DESC")
                landing_prompt_rows = cursor.fetchall()
                
                # 9. Clicks breakdown
                cursor.execute("SELECT target_name, COUNT(*) FROM landing_events WHERE event_type IN ('click_button', 'click_link') GROUP BY target_name ORDER BY COUNT(*) DESC")
                landing_clicks_rows = cursor.fetchall()
                
                # 10. Recent landing events
                cursor.execute("SELECT session_id, user_email, event_type, target_name, timestamp, user_agent, referrer, ip_address, location FROM landing_events ORDER BY timestamp DESC LIMIT 30")
                landing_recent_rows = cursor.fetchall()
                
        # Post-process data
        from datetime import datetime
        
        def parse_iso_datetime(dt_str):
            try:
                clean_str = dt_str.replace("Z", "")
                if "." in clean_str:
                    clean_str = clean_str.split(".")[0]
                return datetime.fromisoformat(clean_str)
            except:
                return None

        now = datetime.utcnow()
        active_users_24h_set = set()
        
        user_connections_map = {}
        for email_addr in all_emails:
            user_connections_map[email_addr] = {
                "email": email_addr,
                "clients": [],
                "last_active": None,
                "last_client": None
            }
            
        for row in connections_rows:
            user_email, client_name, last_active_str, user_agent = row
            if not user_email:
                continue
            if user_email in user_connections_map:
                user_connections_map[user_email]["clients"].append(client_name)
                dt = parse_iso_datetime(last_active_str)
                if dt:
                    if (now - dt).total_seconds() <= 86400:
                        active_users_24h_set.add(user_email)
                    current_last_active = user_connections_map[user_email]["last_active"]
                    if not current_last_active or last_active_str > current_last_active:
                        user_connections_map[user_email]["last_active"] = last_active_str
                        user_connections_map[user_email]["last_client"] = client_name
                        
        users_list = []
        for email_addr, udata in user_connections_map.items():
            unique_clients = sorted(list(set(udata["clients"])))
            users_list.append({
                "email": email_addr,
                "clients": ", ".join(unique_clients),
                "last_active": udata["last_active"],
                "last_client": udata["last_client"]
            })
            
        users_list.sort(key=lambda u: u["last_active"] or "", reverse=True)
        
        client_breakdown = []
        for row in breakdown_rows:
            client_breakdown.append({
                "client_name": row[0] or "Generic AI",
                "memories_count": row[1]
            })
            
        recent_memories = []
        for row in recent_memories_rows:
            recent_memories.append({
                "user_email": row[0],
                "client_name": row[1] or "Generic AI",
                "timestamp": row[2],
                "content": row[3]
            })

        landing_prompt_breakdown = [{"target_name": r[0], "count": r[1]} for r in landing_prompt_rows]
        landing_clicks_breakdown = [{"target_name": r[0], "count": r[1]} for r in landing_clicks_rows]
        landing_recent_events = [{
            "session_id": r[0],
            "user_email": r[1],
            "event_type": r[2],
            "target_name": r[3],
            "timestamp": r[4],
            "user_agent": r[5],
            "referrer": r[6] if len(r) > 6 else 'Direct',
            "ip_address": r[7] if len(r) > 7 else '',
            "location": r[8] if len(r) > 8 else 'Unknown'
        } for r in landing_recent_rows]
            
        results = {
            "total_memories": total_memories,
            "total_sessions": total_sessions,
            "total_users": total_users,
            "active_users_24h": len(active_users_24h_set),
            "client_breakdown": client_breakdown,
            "users": users_list,
            "recent_memories": recent_memories,
            "db_engine": db_engine,
            "dev_mode": is_dev_mode,
            "landing_analytics": {
                "total_events": landing_total_events,
                "total_copies": landing_total_copies,
                "total_sessions": landing_total_sessions,
                "prompt_breakdown": landing_prompt_breakdown,
                "clicks_breakdown": landing_clicks_breakdown,
                "recent_events": landing_recent_events
            }
        }
        
        return JSONResponse({"status": "success", "results": results})
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


@mcp.custom_route("/api/analytics/event", methods=["POST"])
async def api_analytics_event(request: Request) -> JSONResponse:
    """Logs a user interaction event from the landing page."""
    try:
        body = await request.json()
        session_id = body.get("session_id", "unknown")
        user_email = body.get("user_email", "")
        event_type = body.get("event_type")
        target_name = body.get("target_name")
        
        if not event_type or not target_name:
            return JSONResponse({"status": "error", "message": "Missing event_type or target_name"}, status_code=400)
            
        user_agent = request.headers.get("user-agent", "")
        timestamp = datetime.utcnow().isoformat() + "Z"
        
        referrer = body.get("referrer") or request.headers.get("referer") or "Direct"
        
        # Get IP address from headers or connection
        x_forwarded_for = request.headers.get("x-forwarded-for")
        if x_forwarded_for:
            ip_address = x_forwarded_for.split(",")[0].strip()
        else:
            ip_address = request.headers.get("x-real-ip") or (request.client.host if request.client else "")
            
        ip_address = body.get("ip_address") or ip_address or "127.0.0.1"
        location = body.get("location") or "Unknown"
        
        if DATABASE_URL:
            with psycopg2.connect(DATABASE_URL) as conn:
                with conn.cursor() as cursor:
                    cursor.execute('''
                        INSERT INTO landing_events (session_id, user_email, event_type, target_name, timestamp, user_agent, referrer, ip_address, location)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ''', (session_id, user_email, event_type, target_name, timestamp, user_agent, referrer, ip_address, location))
                conn.commit()
        else:
            with sqlite3.connect(DB_PATH) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO landing_events (session_id, user_email, event_type, target_name, timestamp, user_agent, referrer, ip_address, location)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (session_id, user_email, event_type, target_name, timestamp, user_agent, referrer, ip_address, location))
                conn.commit()
                
        return JSONResponse({"status": "success", "message": "Event recorded successfully"})
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)

@mcp.custom_route("/robots.txt", methods=["GET"])
async def serve_robots(request: Request):
    """Serves the robots.txt file."""
    content = """User-agent: *
Allow: /
Sitemap: https://www.rulip.co/sitemap.xml
"""
    return Response(content=content, media_type="text/plain")

@mcp.custom_route("/sitemap.xml", methods=["GET"])
async def serve_sitemap(request: Request):
    """Serves the XML sitemap."""
    content = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
    <url>
        <loc>https://www.rulip.co/</loc>
        <changefreq>weekly</changefreq>
        <priority>1.0</priority>
    </url>
    <url>
        <loc>https://www.rulip.co/landing</loc>
        <changefreq>weekly</changefreq>
        <priority>0.9</priority>
    </url>
    <url>
        <loc>https://www.rulip.co/pricing</loc>
        <changefreq>monthly</changefreq>
        <priority>0.8</priority>
    </url>
    <url>
        <loc>https://www.rulip.co/mcp</loc>
        <changefreq>monthly</changefreq>
        <priority>0.8</priority>
    </url>
    <url>
        <loc>https://www.rulip.co/signup</loc>
        <changefreq>monthly</changefreq>
        <priority>0.7</priority>
    </url>
    <url>
        <loc>https://www.rulip.co/signin</loc>
        <changefreq>monthly</changefreq>
        <priority>0.7</priority>
    </url>
    <url>
        <loc>https://www.rulip.co/privacy</loc>
        <changefreq>yearly</changefreq>
        <priority>0.5</priority>
    </url>
    <url>
        <loc>https://www.rulip.co/terms</loc>
        <changefreq>yearly</changefreq>
        <priority>0.3</priority>
    </url>
    <url>
        <loc>https://www.rulip.co/signin</loc>
        <changefreq>monthly</changefreq>
        <priority>0.5</priority>
    </url>
    <url>
        <loc>https://www.rulip.co/signup</loc>
        <changefreq>monthly</changefreq>
        <priority>0.5</priority>
    </url>
</urlset>
"""
    return Response(content=content, media_type="application/xml")

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
                    cursor.execute('SELECT id, timestamp, content, client_name FROM memories WHERE user_email = %s ORDER BY timestamp DESC', (email,))
                    results = cursor.fetchall()
        else:
            with sqlite3.connect(DB_PATH) as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT id, timestamp, content, client_name FROM memories WHERE user_email = ? ORDER BY timestamp DESC', (email,))
                results = [{"id": row[0], "timestamp": row[1], "content": row[2], "client_name": row[3]} for row in cursor.fetchall()]
                
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
        "token_endpoint_auth_methods_supported": ["none", "client_secret_post", "client_secret_basic"],
        "scopes_supported": ["mcp"],
    })

@mcp.custom_route("/.well-known/oauth-protected-resource", methods=["GET"])
async def oauth_protected_resource_metadata(request: Request) -> JSONResponse:
    """OAuth 2.0 Protected Resource Metadata (RFC 9728). Required by Claude.ai to discover the auth server."""
    base_url = str(request.base_url).rstrip("/")
    return JSONResponse({
        "resource": base_url,
        "authorization_servers": [base_url],
        "bearer_methods_supported": ["header", "query"],
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
            <div id="loader" style="display: none;">Authenticating...</div>
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

            let oauthCompleted = false;

            function approveOAuth(user) {{
                if (oauthCompleted) return;
                oauthCompleted = true;
                
                document.getElementById('firebaseui-auth-container').style.display = 'none';
                document.getElementById('loader').style.display = 'block';
                document.getElementById('loader').innerText = 'Returning to AI platform...';
                
                user.getIdToken().then(function(idToken) {{
                    fetch('/oauth/verify_firebase_token', {{
                        method: 'POST',
                        headers: {{ 'Content-Type': 'application/json' }},
                        body: JSON.stringify({{ idToken: idToken }})
                    }})
                    .then(response => response.json())
                    .then(data => {{
                        if(data.status === 'success') {{
                            const sep = "{redirect_uri}".includes("?") ? "&" : "?";
                            const redirectUri = "{redirect_uri}" + sep + "code=" + data.auth_code + "&state={state}";
                            window.location.href = redirectUri;
                        }} else {{
                            document.getElementById('loader').innerText = 'Verification failed: ' + data.message;
                        }}
                    }})
                    .catch(err => {{
                        document.getElementById('loader').innerText = 'Connection error: ' + err;
                    }});
                }});
            }}

            const ui = new firebaseui.auth.AuthUI(firebase.auth());
            const uiConfig = {{
                callbacks: {{
                    signInSuccessWithAuthResult: function(authResult, redirectUrl) {{
                        approveOAuth(authResult.user);
                        return false;
                    }},
                    uiShown: function() {{
                        document.getElementById('loader').style.display = 'none';
                    }}
                }},
                signInFlow: 'popup',
                signInOptions: [ 
                    {{
                        provider: firebase.auth.GoogleAuthProvider.PROVIDER_ID,
                        customParameters: {{ prompt: 'select_account' }}
                    }}
                ]
            }};

            firebase.auth().onAuthStateChanged(function(user) {{
                if (user) {{
                    approveOAuth(user);
                }} else {{
                    document.getElementById('loader').style.display = 'none';
                    ui.start('#firebaseui-auth-container', uiConfig);
                }}
            }});
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
