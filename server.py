from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.responses import JSONResponse, HTMLResponse
from starlette.requests import Request
import sqlite3
import os
import json
import uuid
from datetime import datetime
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

import firebase_admin
from firebase_admin import credentials, auth as firebase_auth

load_dotenv()

# Initialize FastMCP server
mcp = FastMCP(
    "simple-json-server",
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
                # Memories table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS memories (
                        id SERIAL PRIMARY KEY,
                        timestamp TEXT NOT NULL,
                        content TEXT NOT NULL,
                        user_email TEXT NOT NULL
                    )
                ''')
                # Sessions table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS sessions (
                        auth_code TEXT PRIMARY KEY,
                        user_email TEXT,
                        status TEXT NOT NULL
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
                    content TEXT NOT NULL,
                    user_email TEXT NOT NULL
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS sessions (
                    auth_code TEXT PRIMARY KEY,
                    user_email TEXT,
                    status TEXT NOT NULL
                )
            ''')
            conn.commit()

init_db()

def get_session_email(auth_code: str):
    """Returns the email for an auth_code if verified, else None."""
    if DATABASE_URL:
        with psycopg2.connect(DATABASE_URL) as conn:
            with conn.cursor() as cursor:
                cursor.execute('SELECT user_email, status FROM sessions WHERE auth_code = %s', (auth_code,))
                row = cursor.fetchone()
                if row and row[1] == 'verified':
                    return row[0]
    else:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT user_email, status FROM sessions WHERE auth_code = ?', (auth_code,))
            row = cursor.fetchone()
            if row and row[1] == 'verified':
                return row[0]
    return None

@mcp.tool()
def get_auth_link() -> str:
    """Generates a secure login link. The AI should tell the user to visit this link to authenticate. Returns the auth_code and the URL."""
    auth_code = str(uuid.uuid4())[:8].upper()
    try:
        if DATABASE_URL:
            with psycopg2.connect(DATABASE_URL) as conn:
                with conn.cursor() as cursor:
                    cursor.execute('INSERT INTO sessions (auth_code, status) VALUES (%s, %s)', (auth_code, 'pending'))
                conn.commit()
        else:
            with sqlite3.connect(DB_PATH) as conn:
                cursor = conn.cursor()
                cursor.execute('INSERT INTO sessions (auth_code, status) VALUES (?, ?)', (auth_code, 'pending'))
                conn.commit()
        
        # Replace this with your actual Render URL later if hardcoding, or use a generic one
        login_url = f"http://localhost:8000/login?code={auth_code}" 
        return json.dumps({
            "message": f"Please ask the user to visit this URL to authenticate.",
            "auth_code": auth_code,
            "url": login_url,
            "instructions_for_ai": "Display the URL to the user. Once they verify, you can use the 'auth_code' in subsequent tool calls."
        }, indent=2)
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)})

@mcp.tool()
def save_memory(auth_code: str, content: str) -> str:
    """Saves a memory for the user. Requires a verified auth_code."""
    user_email = get_session_email(auth_code)
    if not user_email:
        return json.dumps({"status": "error", "message": "Unauthorized. Call get_auth_link() and ask the user to sign in."})

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
def search_memory(auth_code: str, query: str) -> str:
    """Searches past memories based on a text query. Requires a verified auth_code."""
    user_email = get_session_email(auth_code)
    if not user_email:
        return json.dumps({"status": "error", "message": "Unauthorized. Call get_auth_link() and ask the user to sign in."})

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
def list_memories(auth_code: str, limit: int = 10) -> str:
    """Lists the most recent memories. Requires a verified auth_code."""
    user_email = get_session_email(auth_code)
    if not user_email:
        return json.dumps({"status": "error", "message": "Unauthorized. Call get_auth_link() and ask the user to sign in."})

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


@mcp.custom_route("/", methods=["GET"])
async def home(request: Request) -> JSONResponse:
    return JSONResponse({
        "status": "online",
        "message": "AI Memory MCP Server is running!",
        "version": "1.1.0"
    })

@mcp.custom_route("/login", methods=["GET"])
async def login_page(request: Request) -> HTMLResponse:
    """Serves the Firebase UI login page."""
    code = request.query_params.get("code")
    if not code:
        return HTMLResponse("<h1>Missing auth code</h1>", status_code=400)
    
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Login - AI Memory Server</title>
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
            <h2>Sign in to connect your AI</h2>
            <p>Auth Code: <strong>{code}</strong></p>
            <div id="firebaseui-auth-container"></div>
            <div id="loader">Loading...</div>
            <div id="success-message" style="display: none; color: green;">
                <h3>Verified!</h3>
                <p>You can close this window and return to your AI assistant.</p>
            </div>
        </div>

        <script>
            // Initialize Firebase from environment variables injected by server
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
                        document.getElementById('loader').innerText = 'Verifying token...';
                        
                        // Get ID token and send to backend
                        authResult.user.getIdToken().then(function(idToken) {{
                            fetch('/verify_token', {{
                                method: 'POST',
                                headers: {{ 'Content-Type': 'application/json' }},
                                body: JSON.stringify({{ code: '{code}', idToken: idToken }})
                            }})
                            .then(response => response.json())
                            .then(data => {{
                                if(data.status === 'success') {{
                                    document.getElementById('loader').style.display = 'none';
                                    document.getElementById('success-message').style.display = 'block';
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
                signInOptions: [ firebase.auth.EmailAuthProvider.PROVIDER_ID ]
            }};
            ui.start('#firebaseui-auth-container', uiConfig);
        </script>
    </body>
    </html>
    """
    return HTMLResponse(html)

@mcp.custom_route("/verify_token", methods=["POST"])
async def verify_token(request: Request) -> JSONResponse:
    """Receives the Firebase ID token from the client, verifies it, and links the session."""
    try:
        body = await request.json()
        code = body.get("code")
        id_token = body.get("idToken")

        if not code or not id_token:
            return JSONResponse({"status": "error", "message": "Missing code or token"}, status_code=400)

        # Verify the token using Firebase Admin
        decoded_token = firebase_auth.verify_id_token(id_token)
        email = decoded_token.get("email")

        if not email:
            return JSONResponse({"status": "error", "message": "Token does not contain an email"}, status_code=400)

        # Update the session in the database
        if DATABASE_URL:
            with psycopg2.connect(DATABASE_URL) as conn:
                with conn.cursor() as cursor:
                    cursor.execute('UPDATE sessions SET user_email = %s, status = %s WHERE auth_code = %s', (email, 'verified', code))
                conn.commit()
        else:
            with sqlite3.connect(DB_PATH) as conn:
                cursor = conn.cursor()
                cursor.execute('UPDATE sessions SET user_email = ?, status = ? WHERE auth_code = ?', (email, 'verified', code))
                conn.commit()

        return JSONResponse({"status": "success", "message": "Verified successfully"})

    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


if __name__ == "__main__":
    port = os.environ.get("PORT")
    if port:
        print(f"Starting SSE server on port {port}")
        mcp.settings.host = "0.0.0.0"
        mcp.settings.port = int(port)
        mcp.run(transport="sse")
    else:
        mcp.run()
