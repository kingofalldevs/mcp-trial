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
            background: transparent;
            z-index: 100;
        }

        .sidebar {
            width: 260px;
            background: rgba(0, 0, 0, 0.04);
            border-right: 1px solid var(--glass-border);
            padding: 2rem;
            display: flex;
            flex-direction: column;
            color: #000000;
        }

        .sidebar .logo {
            margin-bottom: 3rem;
            font-size: 1.5rem;
        }

        .tab-btn {
            background: transparent;
            border: none;
            color: #000000;
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
            background: rgba(0, 0, 0, 0.05);
            color: #1e293b;
        }

        .tab-btn.active {
            background: rgba(16, 185, 129, 0.15);
            color: #10b981;
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
if "/* Sidebar layout */" not in content:
    content = content.replace("/* Dashboard View */", css_addition + "\n        /* Dashboard View */")

# 2. Add IDs to header and main to hide them when sidebar is active
if "<header>" in content:
    content = content.replace("<header>", '<header id="main-header">')
if "<main>" in content:
    content = content.replace("<main>", '<main id="main-content">')

# 3. Rewrite dashboard-view HTML
dashboard_html_start = content.find('<div id="dashboard-view"')
if dashboard_html_start == -1:
    dashboard_html_start = content.find('<div id="dashboard-view">')

dashboard_html_end = content.find('</main>')

if dashboard_html_start != -1 and dashboard_html_end != -1:
    dashboard_old = content[dashboard_html_start:dashboard_html_end]
    dashboard_new = """<!-- Dashboard View -->
        <div id="dashboard-view" class="sidebar-layout" style="display: none;">
        <!-- Sidebar -->
        <aside class="sidebar">
            <div class="logo">
                <a href="/landing" style="display: flex; align-items: center; gap: 0.5rem; text-decoration: none; color: #0f172a;">
                    <svg viewBox="0 0 24 24" style="width: 1.6rem; height: 1.6rem; fill: none; stroke: currentColor; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; color: var(--primary); flex-shrink: 0;">
                        <path d="M12 2L20.7 7v10L12 22L3.3 17V7L12 2Z" stroke-width="1.8" />
                        <path d="M12 22V12" stroke-width="1.8" />
                        <path d="M12 12L20.7 7" stroke-width="1.8" />
                        <path d="M12 12L3.3 7" stroke-width="1.8" />
                        <path d="M12 12L20.7 7V17L12 22Z" fill="currentColor" fill-opacity="0.15" stroke="none" />
                        <circle cx="12" cy="7" r="1.5" fill="currentColor" stroke="none" />
                        <line x1="12" y1="7" x2="7.65" y2="4.5" stroke-width="1.2" opacity="0.8" />
                        <line x1="12" y1="7" x2="16.35" y2="4.5" stroke-width="1.2" opacity="0.8" />
                        <line x1="12" y1="7" x2="12" y2="12" stroke-width="1.2" opacity="0.8" />
                        <circle cx="7.65" cy="4.5" r="1" fill="currentColor" stroke="none" />
                        <circle cx="16.35" cy="4.5" r="1" fill="currentColor" stroke="none" />
                    </svg>
                    <span style="font-family: 'Inter', sans-serif; font-weight: 700; font-size: 1.5rem; letter-spacing: 0.06em; text-transform: uppercase;">Rulip</span>
                </a>
            </div>
            <nav style="display: flex; flex-direction: column; gap: 0.5rem;">
                <button class="tab-btn active" onclick="switchTab('connect')" id="btn-connect"><i class="ph ph-plug"></i> Connect AI</button>
                <button class="tab-btn" onclick="switchTab('memories')" id="btn-memories"><i class="ph ph-grid-four"></i> Memories</button>
                <button class="tab-btn" onclick="switchTab('support')" id="btn-support"><i class="ph ph-lifebuoy"></i> Support</button>
            </nav>
            <div style="margin-top: auto; padding-top: 2rem; border-top: 1px solid var(--glass-border);">
                <div style="display: flex; align-items: center; gap: 0.5rem; cursor: pointer; padding: 0.5rem;" title="Go to Account Settings" onclick="switchTab('account')">
                    <img id="sidebar-avatar" src="" style="width: 32px; height: 32px; border-radius: 50%; object-fit: cover; display: none; border: 2px solid var(--glass-border);">
                    <i id="sidebar-icon" class="ph-fill ph-user-circle" style="font-size: 32px; color: #94a3b8; display: none;"></i>
                    <div style="overflow: hidden;">
                        <div id="sidebar-email" style="font-size: 0.85rem; color: #0f172a; font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;"></div>
                        <div style="font-size: 0.7rem; color: #94a3b8;">Manage Account</div>
                    </div>
                </div>
            </div>
        </aside>

        <!-- Main Content Area -->
        <div style="flex: 1; padding: 2rem 3rem; overflow-y: hidden; position: relative; display: flex; flex-direction: column; height: 100%; min-height: 0;">
            

            <!-- Memories Tab -->
            <div id="tab-memories" class="tab-content" style="flex: 1; flex-direction: column; overflow: hidden; min-height: 0;">
                <div class="dashboard-header" style="flex-shrink: 0; margin-bottom: 1.5rem; padding-bottom: 0.75rem;">
                    <div>
                        <h2 style="font-weight: 700; font-size: 1.85rem;">Your Memories</h2>
                        <p style="color: #334155; margin-top: 0.4rem; font-size: 1rem;">Everything your AI has learned.</p>
                    </div>
                </div>
                <div id="memories-loading" class="spinner" style="margin-top: 3rem; width: 40px; height: 40px; flex-shrink: 0;"></div>
                <div id="memories-container" class="memories-grid" style="flex: 1; overflow-y: auto; padding-right: 0.5rem; padding-bottom: 2rem; margin-top: 0.5rem;"></div>
            </div>

            <!-- Support Tab -->
            <div id="tab-support" class="tab-content" style="flex: 1; flex-direction: column; overflow: hidden; min-height: 0;">
                <div class="dashboard-header" style="flex-shrink: 0; margin-bottom: 1.5rem; padding-bottom: 0.75rem;">
                    <div>
                        <h2 style="font-weight: 700; font-size: 1.85rem;">Support</h2>
                        <p style="color: #334155; margin-top: 0.4rem; font-size: 1rem;">Get help with your integrations and memory settings.</p>
                    </div>
                </div>
                <div style="flex: 1; overflow-y: auto; padding-right: 0.5rem; padding-bottom: 2rem; margin-top: 0.5rem;">
                    <div class="glass-container-wide" style="display: flex; flex-direction: column; gap: 1rem;">
                        <h3 style="font-size: 1.4rem; color: #0f172a; font-weight: 700; margin-bottom: 0.5rem;">Need Assistance?</h3>
                        <p style="color: #334155; line-height: 1.6;">If you are experiencing issues connecting your AI agents or have questions about how memories are stored, please reach out to our team.</p>
                        <a href="mailto:support@memorie.ai" style="display: inline-block; background: var(--primary); color: white; text-decoration: none; padding: 0.75rem 1.5rem; border-radius: 8px; font-weight: 600; width: fit-content; margin-top: 1rem; transition: background 0.2s ease;">Contact Support</a>
                    </div>
                </div>
            </div>

            <!-- Account Tab -->
            <div id="tab-account" class="tab-content" style="flex: 1; flex-direction: column; overflow: hidden; min-height: 0;">
                <div class="dashboard-header" style="flex-shrink: 0; margin-bottom: 1.5rem; padding-bottom: 0.75rem;">
                    <div>
                        <h2 style="font-weight: 700; font-size: 1.85rem;">Account Settings</h2>
                        <p style="color: #334155; margin-top: 0.4rem; font-size: 1rem;">Manage your profile and authentication.</p>
                    </div>
                </div>
                <div style="flex: 1; overflow-y: auto; padding-right: 0.5rem; padding-bottom: 2rem; margin-top: 0.5rem;">
                    <div class="glass-container-wide" style="display: flex; flex-direction: column; gap: 1.5rem; max-width: 600px;">
                        <div>
                            <label style="display: block; font-size: 0.9rem; font-weight: 600; color: #475569; margin-bottom: 0.5rem;">Email Address</label>
                            <div id="account-email-display" style="padding: 0.8rem 1rem; background: rgba(0,0,0,0.03); border: 1px solid rgba(0,0,0,0.05); border-radius: 8px; font-weight: 500; color: #1c1917;">Loading...</div>
                        </div>
                        <div style="border-top: 1px solid rgba(0,0,0,0.05); padding-top: 1.5rem; margin-top: 0.5rem;">
                            <button onclick="firebase.auth().signOut()" style="background: white; color: #ef4444; border: 1px solid #ef4444; padding: 0.6rem 1.2rem; border-radius: 8px; font-weight: 600; cursor: pointer; transition: all 0.2s ease;">Sign Out</button>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Connect Tab -->
             <div id="tab-connect" class="tab-content active">
                <style>
                    .ai-card {
                        background: rgba(255, 255, 255, 0.2);
                        border: 2px solid var(--glass-border);
                        border-radius: 16px;
                        padding: 1.4rem 1rem;
                        cursor: pointer;
                        transition: all 0.2s ease;
                        display: flex;
                        flex-direction: row;
                        align-items: center;
                        gap: 0.85rem;
                        text-align: left;
                        justify-content: flex-start;
                    }
                    .ai-card:hover {
                        border-color: rgba(16, 185, 129, 0.4);
                        background: rgba(255, 255, 255, 0.4);
                    }
                    .ai-card.active {
                        background: rgba(255, 255, 255, 0.5) !important;
                        border-color: var(--primary) !important;
                        box-shadow: none;
                    }
                    .ai-panel {
                        display: none;
                        animation: slideUp 0.3s ease;
                        height: 100%;
                    }
                    .ai-panel.active {
                        display: flex;
                        flex-direction: column;
                        height: 100%;
                        overflow: hidden;
                    }
                    @keyframes slideUp {
                        from { opacity: 0; transform: translateY(8px); }
                        to { opacity: 1; transform: translateY(0); }
                    }
                </style>

                 <div class="dashboard-header" style="flex-shrink: 0; margin-bottom: 1.25rem; padding-bottom: 0.75rem;">
                    <div>
                        <h2 style="font-weight: 700; font-size: 1.85rem;">Connect Your AI</h2>
                        <p style="color: #334155; margin-top: 0.4rem; font-size: 1rem;">Give your agents access to your long-term memory.</p>
                    </div>
                </div>

                <!-- SELECTOR GRID -->
                <div class="ai-selector-grid" style="display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 1.25rem; margin-bottom: 1.75rem; flex-shrink: 0;">
                    <div class="ai-card active" onclick="selectAI('chatgpt')" id="ai-card-chatgpt">
                        <img src="https://www.google.com/s2/favicons?sz=64&domain=chatgpt.com" alt="ChatGPT" style="width: 28px; height: 28px; border-radius: 6px; flex-shrink: 0;">
                        <div style="display: flex; flex-direction: column; gap: 0.2rem; flex: 1; min-width: 0;">
                            <div style="font-weight: 700; font-size: 0.85rem; color: #0f172a; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">ChatGPT</div>
                            <div style="display: flex; align-items: center; gap: 0.4rem; flex-wrap: wrap;">
                                <div id="ai-status-badge-chatgpt" style="font-size: 0.62rem; font-weight: 600; color: #64748b; display: flex; align-items: center; gap: 0.2rem; background: rgba(100, 116, 139, 0.08); padding: 0.12rem 0.4rem; border-radius: 10px; transition: all 0.2s ease; flex-shrink: 0;">
                                    <span id="ai-dot-chatgpt" style="width: 4px; height: 4px; border-radius: 50%; background: #64748b; display: inline-block; transition: all 0.2s ease;"></span>
                                    <span id="ai-status-text-chatgpt">Offline</span>
                                </div>
                                <span id="ai-time-chatgpt" style="font-size: 0.65rem; color: #64748b; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">Never connected</span>
                            </div>
                        </div>
                    </div>
                    <div class="ai-card" onclick="selectAI('claude')" id="ai-card-claude">
                        <img src="https://www.google.com/s2/favicons?sz=64&domain=claude.ai" alt="Claude" style="width: 28px; height: 28px; border-radius: 6px; flex-shrink: 0;">
                        <div style="display: flex; flex-direction: column; gap: 0.2rem; flex: 1; min-width: 0;">
                            <div style="font-weight: 700; font-size: 0.85rem; color: #0f172a; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">Claude</div>
                            <div style="display: flex; align-items: center; gap: 0.4rem; flex-wrap: wrap;">
                                <div id="ai-status-badge-claude" style="font-size: 0.62rem; font-weight: 600; color: #64748b; display: flex; align-items: center; gap: 0.2rem; background: rgba(100, 116, 139, 0.08); padding: 0.12rem 0.4rem; border-radius: 10px; transition: all 0.2s ease; flex-shrink: 0;">
                                    <span id="ai-dot-claude" style="width: 4px; height: 4px; border-radius: 50%; background: #64748b; display: inline-block; transition: all 0.2s ease;"></span>
                                    <span id="ai-status-text-claude">Offline</span>
                                </div>
                                <span id="ai-time-claude" style="font-size: 0.65rem; color: #64748b; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">Never connected</span>
                            </div>
                        </div>
                    </div>
                    <div class="ai-card" onclick="selectAI('cursor')" id="ai-card-cursor">
                        <img src="https://www.google.com/s2/favicons?sz=64&domain=cursor.com" alt="Cursor" style="width: 28px; height: 28px; border-radius: 6px; flex-shrink: 0;">
                        <div style="display: flex; flex-direction: column; gap: 0.2rem; flex: 1; min-width: 0;">
                            <div style="font-weight: 700; font-size: 0.85rem; color: #0f172a; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">Cursor</div>
                            <div style="display: flex; align-items: center; gap: 0.4rem; flex-wrap: wrap;">
                                <div id="ai-status-badge-cursor" style="font-size: 0.62rem; font-weight: 600; color: #64748b; display: flex; align-items: center; gap: 0.2rem; background: rgba(100, 116, 139, 0.08); padding: 0.12rem 0.4rem; border-radius: 10px; transition: all 0.2s ease; flex-shrink: 0;">
                                    <span id="ai-dot-cursor" style="width: 4px; height: 4px; border-radius: 50%; background: #64748b; display: inline-block; transition: all 0.2s ease;"></span>
                                    <span id="ai-status-text-cursor">Offline</span>
                                </div>
                                <span id="ai-time-cursor" style="font-size: 0.65rem; color: #64748b; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">Never connected</span>
                            </div>
                        </div>
                    </div>
                    <div class="ai-card" onclick="selectAI('windsurf')" id="ai-card-windsurf">
                        <img src="https://www.google.com/s2/favicons?sz=64&domain=codeium.com" alt="Windsurf" style="width: 28px; height: 28px; border-radius: 6px; flex-shrink: 0;">
                        <div style="display: flex; flex-direction: column; gap: 0.2rem; flex: 1; min-width: 0;">
                            <div style="font-weight: 700; font-size: 0.85rem; color: #0f172a; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">Windsurf</div>
                            <div style="display: flex; align-items: center; gap: 0.4rem; flex-wrap: wrap;">
                                <div id="ai-status-badge-windsurf" style="font-size: 0.62rem; font-weight: 600; color: #64748b; display: flex; align-items: center; gap: 0.2rem; background: rgba(100, 116, 139, 0.08); padding: 0.12rem 0.4rem; border-radius: 10px; transition: all 0.2s ease; flex-shrink: 0;">
                                    <span id="ai-dot-windsurf" style="width: 4px; height: 4px; border-radius: 50%; background: #64748b; display: inline-block; transition: all 0.2s ease;"></span>
                                    <span id="ai-status-text-windsurf">Offline</span>
                                </div>
                                <span id="ai-time-windsurf" style="font-size: 0.65rem; color: #64748b; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">Never connected</span>
                            </div>
                        </div>
                    </div>
                    <div class="ai-card" onclick="selectAI('manus')" id="ai-card-manus">
                        <img src="https://www.google.com/s2/favicons?sz=64&domain=manus.im" alt="Manus" style="width: 28px; height: 28px; border-radius: 6px; flex-shrink: 0;">
                        <div style="display: flex; flex-direction: column; gap: 0.2rem; flex: 1; min-width: 0;">
                            <div style="font-weight: 700; font-size: 0.85rem; color: #0f172a; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">Manus</div>
                            <div style="display: flex; align-items: center; gap: 0.4rem; flex-wrap: wrap;">
                                <div id="ai-status-badge-manus" style="font-size: 0.62rem; font-weight: 600; color: #64748b; display: flex; align-items: center; gap: 0.2rem; background: rgba(100, 116, 139, 0.08); padding: 0.12rem 0.4rem; border-radius: 10px; transition: all 0.2s ease; flex-shrink: 0;">
                                    <span id="ai-dot-manus" style="width: 4px; height: 4px; border-radius: 50%; background: #64748b; display: inline-block; transition: all 0.2s ease;"></span>
                                    <span id="ai-status-text-manus">Offline</span>
                                </div>
                                <span id="ai-time-manus" style="font-size: 0.65rem; color: #64748b; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">Never connected</span>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- Flex layout container for side-by-side view -->
                <div style="display: flex; gap: 2rem; align-items: stretch; width: 100%; flex: 1; min-height: 0; overflow: hidden;">
                    <!-- CONNECTION DETAIL PANELS -->
                    <div class="glass-container-wide" style="flex: 1; margin-bottom: 0; display: flex; flex-direction: column; overflow: hidden; padding: 2rem 2.5rem;">
                        <!-- ChatGPT Panel -->
                        <div id="panel-chatgpt" class="ai-panel active">
                            <h3 style="font-size: 1.4rem; color: #0f172a; font-weight: 700; margin-bottom: 0.8rem; display: flex; align-items: center; gap: 0.75rem;">
                                <img src="https://www.google.com/s2/favicons?sz=64&domain=chatgpt.com" alt="ChatGPT" style="width: 24px; height: 24px; border-radius: 6px;"> 
                                Connect to ChatGPT (Custom MCP)
                            </h3>

                            
                            <div class="panel-content-layout">
                                <!-- Left side: video -->
                                <div class="panel-video-col">
                                    <div class="video-guide-wrapper">
                                        <iframe src="https://www.youtube.com/embed/eur8dUO9mvE?autoplay=1&mute=1&loop=1&playlist=eur8dUO9mvE&controls=0&modestbranding=1&rel=0&iv_load_policy=3" title="YouTube video player" frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" allowfullscreen style="position: absolute; top: -12%; left: -12%; width: 124%; height: 124%; border: 0;"></iframe>
                                    </div>
                                </div>
                                <!-- Right side: details -->
                                <div class="panel-details-col">
                                    <div class="parameter-group">
                                        <span class="parameter-label">Action SSE URL</span>
                                        <div class="parameter-box">
                                            <span class="parameter-value" id="mcp-url-chatgpt"></span>
                                            <button onclick="copyText(this, 'mcp-url-chatgpt')" class="copy-btn-new" title="Copy"><i class="ph ph-copy"></i></button>
                                        </div>
                                    </div>
                                    <div class="parameter-group">
                                        <span class="parameter-label">Authentication Type</span>
                                        <div class="parameter-box">
                                            <span class="parameter-value">OAuth (Authorization Code Flow)</span>
                                            <span style="font-size: 0.72rem; color: #10b981; font-weight: 700; background: rgba(16, 185, 129, 0.1); padding: 0.2rem 0.5rem; border-radius: 6px; flex-shrink: 0;">Recommended</span>
                                        </div>
                                    </div>
                                    <div class="parameter-group">
                                        <span class="parameter-label">Client ID</span>
                                        <div class="parameter-box">
                                            <span class="parameter-value" id="client-id-chatgpt">rulip</span>
                                            <button onclick="copyText(this, 'client-id-chatgpt')" class="copy-btn-new" title="Copy"><i class="ph ph-copy"></i></button>
                                        </div>
                                    </div>
                                    <div class="parameter-group">
                                        <span class="parameter-label">Client Secret</span>
                                        <div class="parameter-box">
                                            <span class="parameter-value" id="client-secret-chatgpt">rulip</span>
                                            <button onclick="copyText(this, 'client-secret-chatgpt')" class="copy-btn-new" title="Copy"><i class="ph ph-copy"></i></button>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>

                        <!-- Claude Panel -->
                        <div id="panel-claude" class="ai-panel">
                            <h3 style="font-size: 1.4rem; color: #0f172a; font-weight: 700; margin-bottom: 0.8rem; display: flex; align-items: center; gap: 0.75rem;">
                                <img src="https://www.google.com/s2/favicons?sz=64&domain=claude.ai" alt="Claude" style="width: 24px; height: 24px; border-radius: 6px;"> 
                                Connect to Claude (MCP Server)
                            </h3>

                            
                            <div class="panel-content-layout">
                                <!-- Left side: video -->
                                <div class="panel-video-col">
                                    <div class="video-guide-wrapper">
                                        <iframe src="https://www.youtube.com/embed/eur8dUO9mvE?autoplay=1&mute=1&loop=1&playlist=eur8dUO9mvE&controls=0&modestbranding=1&rel=0&iv_load_policy=3" title="YouTube video player" frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" allowfullscreen style="position: absolute; top: -12%; left: -12%; width: 124%; height: 124%; border: 0;"></iframe>
                                    </div>
                                </div>
                                <!-- Right side: details -->
                                <div class="panel-details-col">
                                    <div class="parameter-group">
                                        <span class="parameter-label">App Name</span>
                                        <div class="parameter-box">
                                            <span class="parameter-value" id="client-name-claude">Memories</span>
                                            <button onclick="copyText(this, 'client-name-claude')" class="copy-btn-new" title="Copy"><i class="ph ph-copy"></i></button>
                                        </div>
                                    </div>
                                    <div class="parameter-group">
                                        <span class="parameter-label">MCP URL</span>
                                        <div class="parameter-box">
                                            <span class="parameter-value" id="mcp-url-claude"></span>
                                            <button onclick="copyText(this, 'mcp-url-claude')" class="copy-btn-new" title="Copy"><i class="ph ph-copy"></i></button>
                                        </div>
                                    </div>
                                    <div class="parameter-group">
                                        <span class="parameter-label">OAuth Client ID</span>
                                        <div class="parameter-box">
                                            <span class="parameter-value" id="client-id-claude">rulip</span>
                                            <button onclick="copyText(this, 'client-id-claude')" class="copy-btn-new" title="Copy"><i class="ph ph-copy"></i></button>
                                        </div>
                                    </div>
                                    <div class="parameter-group">
                                        <span class="parameter-label">OAuth Client Secret</span>
                                        <div class="parameter-box">
                                            <span class="parameter-value" id="client-secret-claude">rulip</span>
                                            <button onclick="copyText(this, 'client-secret-claude')" class="copy-btn-new" title="Copy"><i class="ph ph-copy"></i></button>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>

                        <!-- Cursor Panel -->
                        <div id="panel-cursor" class="ai-panel">
                            <h3 style="font-size: 1.4rem; color: #0f172a; font-weight: 700; margin-bottom: 0.8rem; display: flex; align-items: center; gap: 0.75rem;">
                                <img src="https://www.google.com/s2/favicons?sz=64&domain=cursor.com" alt="Cursor" style="width: 24px; height: 24px; border-radius: 6px;"> 
                                Connect to Cursor IDE (SSE Server)
                            </h3>

                            
                            <div class="panel-content-layout">
                                <!-- Left side: video -->
                                <div class="panel-video-col">
                                    <div class="video-guide-wrapper">
                                        <iframe src="https://www.youtube.com/embed/eur8dUO9mvE?autoplay=1&mute=1&loop=1&playlist=eur8dUO9mvE&controls=0&modestbranding=1&rel=0&iv_load_policy=3" title="YouTube video player" frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" allowfullscreen style="position: absolute; top: -12%; left: -12%; width: 124%; height: 124%; border: 0;"></iframe>
                                    </div>
                                </div>
                                <!-- Right side: details -->
                                <div class="panel-details-col">
                                    <div class="parameter-group">
                                        <span class="parameter-label">Name</span>
                                        <div class="parameter-box">
                                            <span class="parameter-value">Memories</span>
                                        </div>
                                    </div>
                                    <div class="parameter-group">
                                        <span class="parameter-label">Type</span>
                                        <div class="parameter-box">
                                            <span class="parameter-value">SSE</span>
                                        </div>
                                    </div>
                                    <div class="parameter-group">
                                        <span class="parameter-label">URL</span>
                                        <div class="parameter-box">
                                            <span class="parameter-value" id="mcp-url-cursor"></span>
                                            <button onclick="copyText(this, 'mcp-url-cursor')" class="copy-btn-new" title="Copy"><i class="ph ph-copy"></i></button>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>

                        <!-- Windsurf Panel -->
                        <div id="panel-windsurf" class="ai-panel">
                            <h3 style="font-size: 1.4rem; color: #0f172a; font-weight: 700; margin-bottom: 0.8rem; display: flex; align-items: center; gap: 0.75rem;">
                                <img src="https://www.google.com/s2/favicons?sz=64&domain=codeium.com" alt="Windsurf" style="width: 24px; height: 24px; border-radius: 6px;"> 
                                Connect to Windsurf IDE (SSE Server)
                            </h3>

                            
                            <div class="panel-content-layout">
                                <!-- Left side: video -->
                                <div class="panel-video-col">
                                    <div class="video-guide-wrapper">
                                        <iframe src="https://www.youtube.com/embed/eur8dUO9mvE?autoplay=1&mute=1&loop=1&playlist=eur8dUO9mvE&controls=0&modestbranding=1&rel=0&iv_load_policy=3" title="YouTube video player" frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" allowfullscreen style="position: absolute; top: -12%; left: -12%; width: 124%; height: 124%; border: 0;"></iframe>
                                    </div>
                                </div>
                                <!-- Right side: details -->
                                <div class="panel-details-col">
                                    <div class="code-block-container">
                                        <div class="code-block-header">
                                            <div style="display: flex; align-items: center; gap: 0.4rem;">
                                                <i class="ph ph-file-code" style="font-size: 0.95rem;"></i>
                                                <span>mcp.json</span>
                                            </div>
                                            <button onclick="copyText(this, 'windsurf-json')" class="copy-btn-new" title="Copy to clipboard"><i class="ph ph-copy"></i></button>
                                        </div>
                                        <div class="code-block-body">
                                            <pre id="windsurf-json"></pre>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>

                        <!-- Manus Panel -->
                        <div id="panel-manus" class="ai-panel">
                            <h3 style="font-size: 1.4rem; color: #0f172a; font-weight: 700; margin-bottom: 0.8rem; display: flex; align-items: center; gap: 0.75rem;">
                                <img src="https://www.google.com/s2/favicons?sz=64&domain=manus.im" alt="Manus" style="width: 24px; height: 24px; border-radius: 6px;"> 
                                Connect to Manus / Custom Client (Headers Token)
                            </h3>

                            
                            <div class="panel-content-layout">
                                <!-- Left side: video -->
                                <div class="panel-video-col">
                                    <div class="video-guide-wrapper">
                                        <iframe src="https://www.youtube.com/embed/eur8dUO9mvE?autoplay=1&mute=1&loop=1&playlist=eur8dUO9mvE&controls=0&modestbranding=1&rel=0&iv_load_policy=3" title="YouTube video player" frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" allowfullscreen style="position: absolute; top: -12%; left: -12%; width: 124%; height: 124%; border: 0;"></iframe>
                                    </div>
                                </div>
                                <!-- Right side: details -->
                                <div class="panel-details-col">
                                    <div class="parameter-group">
                                        <span class="parameter-label">SSE Endpoint</span>
                                        <div class="parameter-box">
                                            <span class="parameter-value" id="mcp-url-manus"></span>
                                            <button onclick="copyText(this, 'mcp-url-manus')" class="copy-btn-new" title="Copy"><i class="ph ph-copy"></i></button>
                                        </div>
                                    </div>
                                    <div class="parameter-group">
                                        <span class="parameter-label">Custom Header</span>
                                        <div class="parameter-box">
                                            <span class="parameter-value" id="manual-header-manus">Loading...</span>
                                            <button onclick="copyText(this, 'manual-header-manus')" class="copy-btn-new" title="Copy"><i class="ph ph-copy"></i></button>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>

                </div>
            </div>



        </div>
    </div>"""
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
if "function switchTab" not in content:
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

if auth_state_old in content:
    content = content.replace(auth_state_old, auth_state_new)

with open("public/index.html", "w") as f:
    f.write(content)
