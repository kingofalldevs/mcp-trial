import re

with open("public/index.html", "r") as f:
    content = f.read()

# 1. Update CSS
css_addition = """
        /* Sidebar layout */
        .sidebar-layout {
            display: flex;
            width: 100vw;
            height: 100vh;
            position: fixed;
            top: 0;
            left: 0;
            background: linear-gradient(135deg, #0f172a 0%, #1e1b4b 100%);
            z-index: 100;
        }

        .sidebar {
            width: 260px;
            background: rgba(0,0,0,0.2);
            border-right: 1px solid var(--glass-border);
            padding: 2rem;
            display: flex;
            flex-direction: column;
        }

        .sidebar .logo {
            margin-bottom: 3rem;
            font-size: 1.5rem;
        }

        .tab-btn {
            background: transparent;
            border: none;
            color: #94a3b8;
            padding: 0.8rem 1rem;
            text-align: left;
            border-radius: 8px;
            cursor: pointer;
            font-size: 1rem;
            font-weight: 500;
            display: flex;
            align-items: center;
            gap: 0.75rem;
            transition: all 0.2s;
        }

        .tab-btn:hover {
            background: rgba(255,255,255,0.05);
            color: #f8fafc;
        }

        .tab-btn.active {
            background: rgba(99, 102, 241, 0.15);
            color: #818cf8;
            font-weight: 600;
        }

        .tab-content {
            display: none;
            animation: fadeIn 0.3s ease;
        }

        .tab-content.active {
            display: block;
        }

        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(5px); }
            to { opacity: 1; transform: translateY(0); }
        }
"""
content = content.replace("/* Dashboard View */", css_addition + "\n        /* Dashboard View */")

# 2. Add IDs to header and main to hide them when sidebar is active
content = content.replace("<header>", '<header id="main-header">')
content = content.replace("<main>", '<main id="main-content">')

# 3. Rewrite dashboard-view HTML
dashboard_html_start = content.find('<div id="dashboard-view">')
dashboard_html_end = content.find('</main>')
dashboard_old = content[dashboard_html_start:dashboard_html_end]

dashboard_new = """<div id="dashboard-view" class="sidebar-layout" style="display: none;">
        <!-- Sidebar -->
        <aside class="sidebar">
            <div class="logo">
                <i class="ph-fill ph-brain" style="color: var(--primary);"></i> Memorie
            </div>
            <nav style="display: flex; flex-direction: column; gap: 0.5rem;">
                <button class="tab-btn active" onclick="switchTab('memories')" id="btn-memories"><i class="ph ph-grid-four"></i> Memories</button>
                <button class="tab-btn" onclick="switchTab('connect')" id="btn-connect"><i class="ph ph-plug"></i> Connect AI</button>
                <button class="tab-btn" onclick="switchTab('account')" id="btn-account"><i class="ph ph-user"></i> Account</button>
            </nav>
            <div style="margin-top: auto; padding-top: 2rem; border-top: 1px solid var(--glass-border);">
                <div style="display: flex; align-items: center; gap: 0.5rem; cursor: pointer; padding: 0.5rem;" title="Click to sign out" onclick="firebase.auth().signOut()">
                    <img id="sidebar-avatar" src="" style="width: 32px; height: 32px; border-radius: 50%; object-fit: cover; display: none; border: 2px solid var(--glass-border);">
                    <i id="sidebar-icon" class="ph-fill ph-user-circle" style="font-size: 32px; color: #94a3b8; display: none;"></i>
                    <div style="overflow: hidden;">
                        <div id="sidebar-email" style="font-size: 0.85rem; color: #e2e8f0; font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;"></div>
                        <div style="font-size: 0.7rem; color: #94a3b8;">Sign Out</div>
                    </div>
                </div>
            </div>
        </aside>

        <!-- Main Content Area -->
        <div style="flex: 1; padding: 3rem; overflow-y: auto;">
            
            <!-- Memories Tab -->
            <div id="tab-memories" class="tab-content active">
                <div class="dashboard-header">
                    <div>
                        <h2 style="font-weight: 600; font-size: 2rem;">Your Memories</h2>
                        <p style="color: #94a3b8; margin-top: 0.5rem;">Everything your AI has learned.</p>
                    </div>
                </div>
                <div id="memories-loading" class="spinner" style="margin-top: 3rem; width: 40px; height: 40px;"></div>
                <div id="memories-container" class="memories-grid"></div>
            </div>

            <!-- Connect Tab -->
            <div id="tab-connect" class="tab-content">
                <div class="dashboard-header">
                    <div>
                        <h2 style="font-weight: 600; font-size: 2rem;">Connect Your AI</h2>
                        <p style="color: #94a3b8; margin-top: 0.5rem;">Give your agents access to your long-term memory.</p>
                    </div>
                </div>
                
                <div class="glass-container" style="max-width: 100%; margin-bottom: 3rem; text-align: left; padding: 2rem;">
                    <div style="display: flex; align-items: center; gap: 1.5rem; flex-wrap: wrap; margin-bottom: 1.5rem;">
                        <h3 style="font-size: 1.2rem; color: #f8fafc; font-weight: 600;">Connection Details</h3>
                        <div style="display: flex; gap: 0.75rem; font-size: 0.85rem; font-weight: 400; color: #cbd5e1; background: rgba(0,0,0,0.2); padding: 0.4rem 1rem; border-radius: 20px; border: 1px solid var(--glass-border); align-items: center;">
                            <span style="color: #94a3b8; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.5px; margin-right: 0.25rem;">Works with:</span>
                            <span style="display: flex; align-items: center; gap: 0.4rem;"><img src="https://www.google.com/s2/favicons?sz=64&domain=chatgpt.com" alt="ChatGPT" style="width: 14px; height: 14px; border-radius: 3px;"> ChatGPT</span> • 
                            <span style="display: flex; align-items: center; gap: 0.4rem;"><img src="https://www.google.com/s2/favicons?sz=64&domain=claude.ai" alt="Claude" style="width: 14px; height: 14px; border-radius: 3px;"> Claude</span> • 
                            <span style="display: flex; align-items: center; gap: 0.4rem;"><img src="https://www.google.com/s2/favicons?sz=64&domain=cursor.com" alt="Cursor" style="width: 14px; height: 14px; border-radius: 3px;"> Cursor</span> • 
                            <span style="display: flex; align-items: center; gap: 0.4rem;"><img src="https://www.google.com/s2/favicons?sz=64&domain=manus.im" alt="Manus" style="width: 14px; height: 14px; border-radius: 3px;"> Manus</span> • 
                            <span style="display: flex; align-items: center; gap: 0.4rem;"><img src="https://www.google.com/s2/favicons?sz=64&domain=codeium.com" alt="Windsurf" style="width: 14px; height: 14px; border-radius: 3px;"> Windsurf</span>
                        </div>
                    </div>
                    
                    <p style="color: #94a3b8; margin-bottom: 1.5rem; line-height: 1.5;">To give your AI access to these memories, go to your AI client, click "Create App" (or "Attach Custom MCP Server"), and enter these exact details:</p>
                    
                    <div style="background: rgba(0,0,0,0.3); border: 1px solid var(--glass-border); border-radius: 12px; padding: 1.5rem; font-family: monospace; color: #a5b4fc; font-size: 0.95rem; line-height: 1.8;">
                        <div style="margin-bottom: 0.5rem;"><strong style="color: #fff;">Connection URL:</strong> <span id="mcp-url"></span></div>
                        <div style="margin-bottom: 0.5rem;"><strong style="color: #fff;">Authentication:</strong> OAuth</div>
                        <div style="margin-bottom: 0.5rem;"><strong style="color: #fff;">Authorization URL:</strong> <span id="auth-url"></span></div>
                        <div style="margin-bottom: 0.5rem;"><strong style="color: #fff;">Token URL:</strong> <span id="token-url"></span></div>
                        <div style="margin-bottom: 0.5rem;"><strong style="color: #fff;">Client ID:</strong> memorie-client</div>
                        <div style="margin-bottom: 0;"><strong style="color: #fff;">Client Secret:</strong> secret-123</div>
                    </div>
                </div>
            </div>

            <!-- Account Tab -->
            <div id="tab-account" class="tab-content">
                <div class="dashboard-header">
                    <div>
                        <h2 style="font-weight: 600; font-size: 2rem;">Account Profile</h2>
                    </div>
                </div>
                <div class="glass-container" style="max-width: 400px; padding: 2rem; text-align: left; display: flex; flex-direction: column; gap: 1.5rem;">
                    <div style="display: flex; align-items: center; gap: 1rem;">
                        <img id="account-avatar" src="" style="width: 64px; height: 64px; border-radius: 50%; object-fit: cover; display: none; border: 2px solid var(--primary);">
                        <i id="account-icon" class="ph-fill ph-user-circle" style="font-size: 64px; color: #94a3b8; display: none;"></i>
                        <div>
                            <div style="font-size: 0.9rem; color: #94a3b8; margin-bottom: 0.25rem;">Signed in as</div>
                            <div id="account-email" style="font-size: 1.1rem; color: #fff; font-weight: 500;"></div>
                        </div>
                    </div>
                    <button style="background: rgba(239, 68, 68, 0.1); color: #ef4444; border: 1px solid rgba(239, 68, 68, 0.2); padding: 0.75rem; border-radius: 8px; cursor: pointer; font-weight: 600; transition: all 0.2s; width: 100%;" onclick="firebase.auth().signOut()">Sign Out of Memorie</button>
                </div>
            </div>

        </div>
    </div>
"""
content = content.replace(dashboard_old, dashboard_new)

# 4. JS updates
js_addition = """
        function switchTab(tabId) {
            // Hide all contents
            document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
            // Remove active from all buttons
            document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));
            
            // Show selected content
            document.getElementById('tab-' + tabId).classList.add('active');
            // Set active button
            document.getElementById('btn-' + tabId).classList.add('active');
        }
"""
content = content.replace("function renderMemories", js_addition + "\n        function renderMemories")

# 5. Auth State updates
auth_state_old = """                    if (user.photoURL) {
                        document.getElementById('user-avatar').src = user.photoURL;
                        document.getElementById('user-avatar').title = user.email;
                        document.getElementById('user-avatar').style.display = 'block';
                        document.getElementById('user-icon').style.display = 'none';
                    } else {
                        document.getElementById('user-icon').title = user.email;
                        document.getElementById('user-icon').style.display = 'block';
                        document.getElementById('user-avatar').style.display = 'none';
                    }"""

auth_state_new = """                    document.getElementById('main-header').style.display = 'none';
                    document.getElementById('main-content').style.display = 'none';
                    
                    // Set sidebar account info
                    document.getElementById('sidebar-email').innerText = user.email;
                    document.getElementById('account-email').innerText = user.email;
                    if (user.photoURL) {
                        document.getElementById('sidebar-avatar').src = user.photoURL;
                        document.getElementById('sidebar-avatar').style.display = 'block';
                        document.getElementById('sidebar-icon').style.display = 'none';
                        
                        document.getElementById('account-avatar').src = user.photoURL;
                        document.getElementById('account-avatar').style.display = 'block';
                        document.getElementById('account-icon').style.display = 'none';
                    } else {
                        document.getElementById('sidebar-icon').style.display = 'block';
                        document.getElementById('sidebar-avatar').style.display = 'none';
                        
                        document.getElementById('account-icon').style.display = 'block';
                        document.getElementById('account-avatar').style.display = 'none';
                    }"""

content = content.replace(auth_state_old, auth_state_new)

with open("public/index.html", "w") as f:
    f.write(content)
