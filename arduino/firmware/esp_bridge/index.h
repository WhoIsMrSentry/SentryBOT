#ifndef INDEX_H
#define INDEX_H

const char* INDEX_HTML = R"=====(
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>SentryBOT Dashboard</title>
    <style>
        :root {
            --bg-color: #0f172a;
            --panel-bg: rgba(30, 41, 59, 0.7);
            --btn-bg: rgba(51, 65, 85, 0.8);
            --btn-hover: rgba(71, 85, 105, 0.9);
            --btn-active: rgba(99, 102, 241, 0.8);
            --text-main: #f8fafc;
            --text-muted: #94a3b8;
            --accent: #6366f1;
            --accent-glow: rgba(99, 102, 241, 0.4);
            --success: #10b981;
            --danger: #ef4444;
            --warning: #f59e0b;
            --info: #3b82f6;
        }

        * {
            box-sizing: border-box;
            user-select: none;
            -webkit-tap-highlight-color: transparent;
        }

        body {
            margin: 0;
            padding: 0;
            font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
            background-color: var(--bg-color);
            color: var(--text-main);
            display: flex;
            flex-direction: column;
            min-height: 100vh;
            background: radial-gradient(circle at 50% 0%, #1e293b 0%, #0f172a 100%);
            overflow-x: hidden;
        }

        header {
            width: 100%;
            padding: 1.2rem 1rem;
            text-align: center;
            backdrop-filter: blur(10px);
            -webkit-backdrop-filter: blur(10px);
            background: rgba(15, 23, 42, 0.8);
            border-bottom: 1px solid rgba(255,255,255,0.05);
            position: sticky;
            top: 0;
            z-index: 10;
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 8px;
        }

        h1 {
            margin: 0;
            font-size: 1.5rem;
            font-weight: 700;
            letter-spacing: 1px;
            background: linear-gradient(to right, #818cf8, #c084fc);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }

        .status-indicator {
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
            font-size: 0.8rem;
            color: var(--text-muted);
            background: rgba(0,0,0,0.3);
            padding: 4px 12px;
            border-radius: 20px;
            border: 1px solid rgba(255,255,255,0.05);
        }

        .dot {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background-color: var(--danger);
            transition: background-color 0.3s;
        }
        .dot.connected {
            background-color: var(--success);
            box-shadow: 0 0 8px var(--success);
        }

        /* Tabs Navigation */
        .tabs {
            display: flex;
            width: 100%;
            background: rgba(15, 23, 42, 0.9);
            border-bottom: 1px solid rgba(255,255,255,0.05);
        }

        .tab-btn {
            flex: 1;
            padding: 1rem 0;
            text-align: center;
            background: none;
            border: none;
            color: var(--text-muted);
            font-weight: 600;
            font-size: 0.95rem;
            cursor: pointer;
            transition: all 0.3s;
            position: relative;
        }

        .tab-btn.active {
            color: var(--accent);
        }

        .tab-btn.active::after {
            content: '';
            position: absolute;
            bottom: 0;
            left: 20%;
            width: 60%;
            height: 3px;
            background: var(--accent);
            border-radius: 3px 3px 0 0;
            box-shadow: 0 -2px 10px var(--accent-glow);
        }

        /* Tab Content */
        .tab-content {
            display: none;
            flex: 1;
            padding: 1.5rem 1rem;
            width: 100%;
            max-width: 500px;
            margin: 0 auto;
            flex-direction: column;
            gap: 1.5rem;
            animation: fadeIn 0.3s ease;
        }

        .tab-content.active {
            display: flex;
        }

        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(10px); }
            to { opacity: 1; transform: translateY(0); }
        }

        .panel {
            background: var(--panel-bg);
            backdrop-filter: blur(12px);
            -webkit-backdrop-filter: blur(12px);
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 20px;
            padding: 1.5rem;
            box-shadow: 0 10px 30px rgba(0,0,0,0.3);
        }

        .panel h2 {
            margin: 0 0 1rem 0;
            font-size: 1.1rem;
            color: var(--text-muted);
            border-bottom: 1px solid rgba(255, 255, 255, 0.1);
            padding-bottom: 0.5rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        /* Common Buttons */
        .btn {
            background: var(--btn-bg);
            border: 1px solid rgba(255,255,255,0.05);
            border-radius: 12px;
            color: var(--text-main);
            font-size: 1rem;
            font-weight: 600;
            padding: 0.8rem;
            display: flex;
            align-items: center;
            justify-content: center;
            cursor: pointer;
            transition: all 0.15s ease;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }

        .btn:active {
            transform: scale(0.95);
            background: var(--btn-active);
            border-color: var(--accent);
        }

        /* D-Pad Layout */
        .dpad-container {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            grid-template-rows: repeat(3, 1fr);
            gap: 10px;
            width: 240px;
            height: 240px;
            margin: 0 auto;
        }

        .btn-up { grid-column: 2; grid-row: 1; border-radius: 16px 16px 8px 8px; font-size: 1.5rem; }
        .btn-down { grid-column: 2; grid-row: 3; border-radius: 8px 8px 16px 16px; font-size: 1.5rem; }
        .btn-left { grid-column: 1; grid-row: 2; border-radius: 16px 8px 8px 16px; font-size: 1.5rem; }
        .btn-right { grid-column: 3; grid-row: 2; border-radius: 8px 16px 16px 8px; font-size: 1.5rem; }
        .btn-ok { 
            grid-column: 2; grid-row: 2; 
            border-radius: 50%;
            background: linear-gradient(135deg, #4f46e5, #7c3aed);
            border: none;
            box-shadow: 0 4px 15px rgba(99, 102, 241, 0.4);
            font-size: 1.2rem;
        }
        .btn-ok:active { background: linear-gradient(135deg, #4338ca, #6d28d9); }

        .action-row { display: flex; gap: 10px; }
        .action-row .btn { flex: 1; }

        .numpad {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 8px;
        }

        /* Telemetry Grid */
        .telemetry-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 1rem;
        }

        .metric {
            background: rgba(0,0,0,0.2);
            border: 1px solid rgba(255,255,255,0.03);
            border-radius: 12px;
            padding: 1rem;
            text-align: center;
        }

        .metric-title {
            font-size: 0.8rem;
            color: var(--text-muted);
            margin-bottom: 0.5rem;
            text-transform: uppercase;
            letter-spacing: 1px;
        }

        .metric-value {
            font-size: 1.3rem;
            font-weight: 700;
            color: var(--accent);
            text-shadow: 0 0 10px var(--accent-glow);
        }

        .metric-value.small {
            font-size: 1rem;
            letter-spacing: 2px;
        }

        .metric-value.danger { color: var(--danger); text-shadow: 0 0 10px rgba(239, 68, 68, 0.4); }
        .metric-value.warning { color: var(--warning); text-shadow: 0 0 10px rgba(245, 158, 11, 0.4); }
        .metric-value.success { color: var(--success); text-shadow: 0 0 10px rgba(16, 185, 129, 0.4); }

        /* Grid for buttons */
        .grid-2 {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 10px;
        }
        
        .grid-3 {
            display: grid;
            grid-template-columns: 1fr 1fr 1fr;
            gap: 8px;
        }

        .grid-3 .btn {
            font-size: 0.85rem;
            padding: 0.6rem;
        }

        /* Temp list */
        .temp-list {
            display: flex;
            flex-direction: column;
            gap: 8px;
            margin-top: 10px;
        }

        .temp-item {
            display: flex;
            justify-content: space-between;
            background: rgba(255, 255, 255, 0.05);
            padding: 8px 12px;
            border-radius: 8px;
            font-size: 0.9rem;
        }

        .temp-val { font-weight: bold; color: var(--warning); }

        /* Input styling */
        input[type="text"] {
            flex: 1;
            background: rgba(0, 0, 0, 0.3);
            border: 1px solid rgba(255, 255, 255, 0.1);
            color: white;
            border-radius: 12px;
            padding: 0.8rem 1rem;
            font-size: 1rem;
            outline: none;
        }

        input[type="text"]:focus {
            border-color: var(--accent);
            box-shadow: 0 0 8px var(--accent-glow);
        }
    </style>
</head>
<body>

    <header>
        <h1>SentryBOT</h1>
        <div class="status-indicator" id="statusBox">
            <div class="dot" id="statusDot"></div>
            <span id="statusText">Connecting...</span>
        </div>
    </header>

    <div class="tabs">
        <button class="tab-btn active" onclick="switchTab('remote', this)">Remote</button>
        <button class="tab-btn" onclick="switchTab('sensors', this)">Sensors</button>
        <button class="tab-btn" onclick="switchTab('actions', this)">Actions</button>
        <button class="tab-btn" onclick="switchTab('dev', this)">Dev</button>
    </div>

    <!-- TAB 1: REMOTE -->
    <div id="tab-remote" class="tab-content active">
        <button class="btn" onclick="sendCmd({cmd:'estop'})"
            style="background: var(--danger); width: 100%; padding: 1rem; font-size: 1.2rem; margin-bottom: 10px; box-shadow: 0 0 15px rgba(239, 68, 68, 0.5);">EMERGENCY
            STOP</button>

        <div class="action-row">
            <button class="btn" onclick="sendIrKey('*')">HOME</button>
            <button class="btn" onclick="sendCmd({cmd:'stand'})">STAND</button>
            <button class="btn" onclick="sendCmd({cmd:'sit'})">SIT</button>
            <button class="btn" onclick="sendIrKey('#')">BACK</button>
        </div>

        <div class="panel">
            <h2>Menu Shortcuts</h2>
            <div class="grid-3" style="margin-bottom: 15px;">
                <button class="btn" onclick="sendCmd({cmd:'menu_goto', menu:'home'})">Home</button>
                <button class="btn" onclick="sendCmd({cmd:'menu_goto', menu:'system'})">System</button>
                <button class="btn" onclick="sendCmd({cmd:'menu_goto', menu:'servo'})">Servos</button>
                <button class="btn" onclick="sendCmd({cmd:'menu_goto', menu:'sound'})">Sound</button>
                <button class="btn" onclick="sendCmd({cmd:'menu_goto', menu:'imu'})">IMU</button>
                <button class="btn" onclick="sendCmd({cmd:'menu_goto', menu:'temps'})">Temps</button>
                <button class="btn" onclick="sendCmd({cmd:'menu_goto', menu:'rfid'})">RFID</button>
                <button class="btn" onclick="sendCmd({cmd:'menu_goto', menu:'ultra'})">Ultra</button>
                <button class="btn" onclick="sendCmd({cmd:'menu_goto', menu:'laser'})">Laser</button>
            </div>

            <div class="dpad-container">
                <button class="btn btn-up" onclick="sendIrKey('UP')">▲</button>
                <button class="btn btn-left" onclick="sendIrKey('LEFT')">◀</button>
                <button class="btn btn-ok" onclick="sendIrKey('OK')">OK</button>
                <button class="btn btn-right" onclick="sendIrKey('RIGHT')">▶</button>
                <button class="btn btn-down" onclick="sendIrKey('DOWN')">▼</button>
            </div>
        </div>

        <div class="panel">
            <div class="numpad">
                <button class="btn" onclick="sendIrKey('1')">1</button>
                <button class="btn" onclick="sendIrKey('2')">2</button>
                <button class="btn" onclick="sendIrKey('3')">3</button>
                <button class="btn" onclick="sendIrKey('4')">4</button>
                <button class="btn" onclick="sendIrKey('5')">5</button>
                <button class="btn" onclick="sendIrKey('6')">6</button>
                <button class="btn" onclick="sendIrKey('7')">7</button>
                <button class="btn" onclick="sendIrKey('8')">8</button>
                <button class="btn" onclick="sendIrKey('9')">9</button>
                <button class="btn" style="grid-column: 2;" onclick="sendIrKey('0')">0</button>
            </div>
        </div>
    </div>

    <!-- TAB 2: SENSORS -->
    <div id="tab-sensors" class="tab-content">
        <div class="panel">
            <h2>IMU Data</h2>
            <div class="telemetry-grid">
                <div class="metric">
                    <div class="metric-title">Pitch</div>
                    <div class="metric-value" id="val-pitch">--°</div>
                </div>
                <div class="metric">
                    <div class="metric-title">Roll</div>
                    <div class="metric-value" id="val-roll">--°</div>
                </div>
            </div>
        </div>

        <div class="panel">
            <h2>Environment & Mode</h2>
            <div class="telemetry-grid">
                <div class="metric">
                    <div class="metric-title">Obstacle Dist</div>
                    <div class="metric-value" id="val-ultra">-- cm</div>
                </div>
                <div class="metric">
                    <div class="metric-title">Robot Mode</div>
                    <div class="metric-value" id="val-mode" style="font-size: 1.1rem;">Unknown</div>
                </div>
            </div>
        </div>

        <div class="panel">
            <h2>Security & Modules</h2>
            <div class="telemetry-grid">
                <div class="metric" style="grid-column: span 2;">
                    <div class="metric-title">Last RFID Tag</div>
                    <div class="metric-value small" id="val-rfid" style="color: var(--info);">--</div>
                </div>
            </div>
        </div>

        <div class="panel">
            <h2>DS18 Temperatures</h2>
            <div class="temp-list" id="temp-list-container">
                <div class="temp-item"><span>Loading sensors...</span></div>
            </div>
        </div>
        
        <div class="action-row">
            <button class="btn" onclick="sendCmd({cmd:'imu_cal'})" style="background: var(--warning); color: #000;">Calibrate IMU</button>
            <button class="btn" onclick="sendCmd({cmd:'cal'})" style="background: var(--warning); color: #000;">Calibrate Pose</button>
        </div>
    </div>

    <!-- TAB 3: ACTIONS & SOUNDS -->
    <div id="tab-actions" class="tab-content">

        <div class="panel">
            <h2>LCD Screen Message</h2>
            <div style="display: flex; gap: 8px; margin-bottom: 10px;">
                <input type="text" id="lcd-text" placeholder="Enter message..." maxlength="16">
                <button class="btn" onclick="sendLcdMessage()" style="background: var(--info); border:none;">Show
                    (5s)</button>
            </div>
            <p style="font-size: 0.8rem; color: var(--text-muted); margin:0;">Bu mesaj robotun LCD ekranında 5 sn
                görünüp ana menüye dönecektir.</p>
        </div>

        <div class="panel">
            <h2>Morse Code Player</h2>
            <div style="display: flex; gap: 8px; margin-bottom: 10px;">
                <input type="text" id="morse-text" placeholder="Enter text..." maxlength="30">
                <button class="btn" onclick="sendMorse()"
                    style="background: var(--warning); color:#000; border:none;">Play Morse</button>
            </div>
            <p style="font-size: 0.8rem; color: var(--text-muted); margin:0;">Yazdığınız metin mors alfabesine çevrilip
                robotun buzzer'ından çalınır.</p>
        </div>

        <div class="panel">
            <h2>System Toggles</h2>
            <div class="grid-2">
                <button class="btn" onclick="sendCmd({cmd:'avoid', enable:true})"
                    style="border-color: var(--success);">Avoid ON</button>
                <button class="btn" onclick="sendCmd({cmd:'avoid', enable:false})">Avoid OFF</button>
                <button class="btn" onclick="sendCmd({cmd:'sound', out:'loud'})">Vol: LOUD</button>
                <button class="btn" onclick="sendCmd({cmd:'sound', out:'quiet'})">Vol: QUIET</button>
                <button class="btn" onclick="sendCmd({cmd:'laser', both:true, on:true})"
                    style="border-color: var(--danger);">Lasers ON</button>
                <button class="btn" onclick="sendCmd({cmd:'laser', on:false})">Lasers OFF</button>
            </div>
        </div>

        <div class="panel">
            <h2>Songs & Themes</h2>
            <div class="grid-2">
                <button class="btn" onclick="sendCmd({cmd:'sound_play', name:'walle', out:'loud'})">Wall-E Theme</button>
                <button class="btn" onclick="sendCmd({cmd:'sound_play', name:'bb8', out:'loud'})">BB-8 Theme</button>
            </div>
        </div>

        <div class="panel">
            <h2>All Cute Expressions</h2>
            <div class="grid-3">
                <button class="btn" onclick="sendCmd({cmd:'cute', name:'connection'})">Connect</button>
                <button class="btn" onclick="sendCmd({cmd:'cute', name:'disconnect'})">Disconn</button>
                <button class="btn" onclick="sendCmd({cmd:'cute', name:'button'})">Button</button>
                <button class="btn" onclick="sendCmd({cmd:'cute', name:'mode1'})">Mode 1</button>
                <button class="btn" onclick="sendCmd({cmd:'cute', name:'mode2'})">Mode 2</button>
                <button class="btn" onclick="sendCmd({cmd:'cute', name:'mode3'})">Mode 3</button>
                <button class="btn" onclick="sendCmd({cmd:'cute', name:'happy'})">Happy</button>
                <button class="btn" onclick="sendCmd({cmd:'cute', name:'happy_short'})">H-Short</button>
                <button class="btn" onclick="sendCmd({cmd:'cute', name:'super_happy'})">S-Happy</button>
                <button class="btn" onclick="sendCmd({cmd:'cute', name:'sad'})">Sad</button>
                <button class="btn" onclick="sendCmd({cmd:'cute', name:'surprise'})">Surprise</button>
                <button class="btn" onclick="sendCmd({cmd:'cute', name:'ohooh'})">Oh-ooh</button>
                <button class="btn" onclick="sendCmd({cmd:'cute', name:'ohooh2'})">Oh-ooh 2</button>
                <button class="btn" onclick="sendCmd({cmd:'cute', name:'cuddly'})">Cuddly</button>
                <button class="btn" onclick="sendCmd({cmd:'cute', name:'confused'})">Confused</button>
                <button class="btn" onclick="sendCmd({cmd:'cute', name:'sleeping'})">Sleeping</button>
                <button class="btn" onclick="sendCmd({cmd:'cute', name:'fart1'})">Fart 1</button>
                <button class="btn" onclick="sendCmd({cmd:'cute', name:'fart2'})">Fart 2</button>
                <button class="btn" onclick="sendCmd({cmd:'cute', name:'fart3'})">Fart 3</button>
                <button class="btn" onclick="sendCmd({cmd:'cute', name:'jump'})">Jump</button>
            </div>
        </div>
    </div>

    <!-- TAB 4: DEVELOPER (Low-Level Control) -->
    <div id="tab-dev" class="tab-content">
        <div class="panel">
            <h2>Drive Controls (Skate)</h2>
            <div class="grid-3" style="margin-bottom: 10px;">
                <button class="btn" onclick="sendCmd({cmd:'drive', value: 800})" style="background: var(--info);">FWD Fast</button>
                <button class="btn" onclick="sendCmd({cmd:'drive', value: 0})" style="background: var(--danger);">STOP</button>
                <button class="btn" onclick="sendCmd({cmd:'drive', value: -800})" style="background: var(--warning); color:#000;">REV Fast</button>
            </div>
            <p style="font-size: 0.8rem; color: var(--text-muted); margin:0;">Bu tuşlar skate (kaykay) modunda iken motorlara direkt hız komutu yollar.</p>
        </div>

        <div class="panel">
            <h2>Raw Servos (Head)</h2>
            <div class="grid-3">
                <button class="btn" onclick="sendCmd({cmd:'set_servo', index:0, deg:0})">Pan Left</button>
                <button class="btn" onclick="sendCmd({cmd:'set_servo', index:0, deg:90})">Pan Center</button>
                <button class="btn" onclick="sendCmd({cmd:'set_servo', index:0, deg:180})">Pan Right</button>
                <button class="btn" onclick="sendCmd({cmd:'set_servo', index:1, deg:45})">Tilt Up</button>
                <button class="btn" onclick="sendCmd({cmd:'set_servo', index:1, deg:90})">Tilt Center</button>
                <button class="btn" onclick="sendCmd({cmd:'set_servo', index:1, deg:135})">Tilt Down</button>
            </div>
        </div>

        <div class="panel">
            <h2>Steppers & Memory</h2>
            <div class="grid-2">
                <button class="btn" onclick="sendCmd({cmd:'home'})">Home Steppers</button>
                <button class="btn" onclick="sendCmd({cmd:'zero_now'})">Zero Now</button>
                <button class="btn" onclick="sendCmd({cmd:'pid_reset'})">PID Reset</button>
                <button class="btn" onclick="sendCmd({cmd:'pid_clear_stall'})">Clear Stall</button>
                <button class="btn" onclick="sendCmd({cmd:'eeprom_save'})" style="background: var(--info);">EEPROM Save</button>
                <button class="btn" onclick="sendCmd({cmd:'eeprom_load'})" style="background: var(--info);">EEPROM Load</button>
            </div>
        </div>

        <div class="panel">
            <h2>Advanced Calibration</h2>
            <div class="grid-2">
                <button class="btn" onclick="sendCmd({cmd:'encoder_calibrate', duration_ms:5000})">Calibrate Encoders</button>
                <button class="btn" onclick="sendCmd({cmd:'hello'})" style="background: var(--success);">Get Sys Info</button>
            </div>
        </div>
    </div>

    <script>
        // Tab Switching
        let currentTab = 'remote';
        function switchTab(tabId, btnEl) {
            currentTab = tabId;
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
            
            if (btnEl) btnEl.classList.add('active');
            document.getElementById('tab-' + tabId).classList.add('active');

            // Trigger immediate poll if sensors tab is opened
            if (tabId === 'sensors') pollSensors();
        }

        // Status Management
        const statusText = document.getElementById('statusText');
        const statusDot = document.getElementById('statusDot');
        
        function updateStatus(connected, text = "") {
            if (connected) {
                statusDot.classList.add('connected');
                statusText.textContent = text || 'Connected';
            } else {
                statusDot.classList.remove('connected');
                statusText.textContent = text || 'Disconnected';
            }
        }

        // API Calls
        function haptic() {
            if (navigator.vibrate) navigator.vibrate(40);
        }

        async function sendCmd(payloadObj) {
            haptic();
            try {
                const res = await fetch('/send', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payloadObj)
                });
                if (!res.ok) updateStatus(false, 'Send Error');
            } catch (e) {
                updateStatus(false, 'Network Error');
            }
        }

        function sendIrKey(key) {
            sendCmd({ cmd: "ir_key", key: key });
        }

        async function sendLcdMessage() {
            const txt = document.getElementById('lcd-text').value;
            if (!txt) return;
            // Send LCD
            await sendCmd({ cmd: 'lcd', top: 'WEB MSG:', bottom: txt });
            document.getElementById('lcd-text').value = '';
            // Wait 5 seconds and return home
            setTimeout(() => {
                sendCmd({ cmd: 'menu_goto', menu: 'home' });
            }, 5000);
        }

        async function sendMorse() {
            const txt = document.getElementById('morse-text').value;
            if (!txt) return;
            // Set speech text
            await sendCmd({ cmd: 'speech', text: txt });
            // Play it
            await sendCmd({ cmd: 'speech_play' });
            document.getElementById('morse-text').value = '';
        }

        // Polling Logic
        async function fetchRequest(payloadObj) {
            try {
                const res = await fetch('/request', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payloadObj)
                });
                if (res.ok) {
                    updateStatus(true, 'Bridge Ready');
                    return await res.json();
                }
            } catch (e) {
                // Ignore timeout visually to prevent flickering, just return null
            }
            return null;
        }

        let isPolling = false;
        async function pollSensors() {
            if (currentTab !== 'sensors' || isPolling) return;
            isPolling = true;

            try {
                // Poll IMU and State
                const state = await fetchRequest({ cmd: "get_state" });
                if (state && state.ok) {
                    document.getElementById('val-pitch').textContent = state.pitch.toFixed(1) + '°';
                    document.getElementById('val-roll').textContent = state.roll.toFixed(1) + '°';
                    document.getElementById('val-mode').textContent = state.mode ? state.mode.toUpperCase() : 'UNKNOWN';
                }

                await new Promise(r => setTimeout(r, 50));

                // Poll Ultrasonic
                const ultra = await fetchRequest({ cmd: "ultra_read" });
                if (ultra && ultra.ok) {
                    const cmEl = document.getElementById('val-ultra');
                    if (ultra.cm === null || ultra.cm === 0) {
                        cmEl.textContent = 'Out of Range';
                        cmEl.className = 'metric-value';
                    } else {
                        cmEl.textContent = ultra.cm.toFixed(1) + ' cm';
                        if (ultra.cm < 10) cmEl.className = 'metric-value danger';
                        else if (ultra.cm < 25) cmEl.className = 'metric-value warning';
                        else cmEl.className = 'metric-value success';
                    }
                }

                await new Promise(r => setTimeout(r, 50));

                // Poll RFID
                const rfid = await fetchRequest({ cmd: "rfid_last" });
                if (rfid && rfid.ok && rfid.rfid) {
                    document.getElementById('val-rfid').textContent = rfid.rfid || 'NO TAG';
                }

                await new Promise(r => setTimeout(r, 50));

                // Poll Temperatures
                const temp = await fetchRequest({ cmd: "temp_read" });
                if (temp && temp.ok && temp.temps) {
                    const container = document.getElementById('temp-list-container');
                    container.innerHTML = '';
                    let tempHtml = '';
                    temp.temps.forEach((t, i) => {
                        let tStr = t === null ? '--.-' : t.toFixed(1);
                        tempHtml += `<div class="temp-item"><span>Sensor ${i + 1}</span><span class="temp-val">${tStr} °C</span></div>`;
                    });
                    if (tempHtml === '') tempHtml = '<div class="temp-item"><span>No sensors found</span></div>';
                    container.innerHTML = tempHtml;
                }

            } finally {
                isPolling = false;
            }
        }

        // Background loops
        setInterval(async () => {
            try {
                const res = await fetch('/healthz');
                if (res.ok) {
                    const data = await res.json();
                    updateStatus(data.ok, data.ok ? 'Bridge Ready' : 'Bridge Error');
                } else updateStatus(false);
            } catch (e) { updateStatus(false); }
        }, 3000);

        setInterval(pollSensors, 1500); // Poll sensors every 1.5s when active
    </script>
</body>
</html>
)=====";

#endif // INDEX_H
