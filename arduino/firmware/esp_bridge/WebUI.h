#ifndef WEB_UI_H
#define WEB_UI_H

const char INDEX_HTML[] PROGMEM = R"=====(
<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SentryBOT Command Center</title>
    <style>
        :root {
            --crimson: #dc143c;
            --crimson-glow: #ff2d55;
            --bg-dark: #0a0a0b;
            --card-bg: rgba(25, 25, 27, 0.9);
            --text: #e0e0e0;
            --text-muted: #a0a0a0;
            --glass: rgba(255, 255, 255, 0.03);
        }

        * { box-sizing: border-box; }
        body {
            background-color: var(--bg-dark);
            background-image: 
                radial-gradient(circle at 0% 0%, #1a0505 0%, transparent 50%),
                radial-gradient(circle at 100% 100%, #050505 0%, transparent 50%);
            color: var(--text);
            font-family: 'Segoe UI', system-ui, sans-serif;
            margin: 0;
            padding: 20px;
            display: flex;
            flex-direction: column;
            align-items: center;
            min-height: 100vh;
            overflow-x: hidden;
        }

        .container {
            width: 100%;
            max-width: 1200px;
            display: grid;
            grid-template-columns: 1fr 380px;
            gap: 25px;
        }

        @media (max-width: 950px) {
            .container { grid-template-columns: 1fr; }
        }

        .card {
            background: var(--card-bg);
            backdrop-filter: blur(15px);
            border: 1px solid rgba(220, 20, 60, 0.1);
            border-radius: 20px;
            padding: 25px;
            box-shadow: 0 15px 45px rgba(0, 0, 0, 0.6);
        }

        h1 {
            color: var(--crimson);
            margin: 0 0 20px 0;
            font-size: 1.2rem;
            text-transform: uppercase;
            letter-spacing: 3px;
            text-align: left;
            border-bottom: 1px solid rgba(220, 20, 60, 0.2);
            padding-bottom: 10px;
        }

        /* Interactive Sensor Buttons */
        .sensor-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
            gap: 12px;
            margin-bottom: 20px;
        }

        .sensor-btn {
            background: var(--glass);
            border: 1px solid rgba(255, 255, 255, 0.05);
            border-radius: 12px;
            padding: 15px;
            cursor: pointer;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            text-align: center;
            position: relative;
            overflow: hidden;
        }

        .sensor-btn:hover {
            background: rgba(220, 20, 60, 0.1);
            border-color: var(--crimson);
            transform: translateY(-2px);
        }

        .sensor-btn.active {
            background: rgba(220, 20, 60, 0.15);
            border-color: var(--crimson);
            box-shadow: 0 0 15px rgba(220, 20, 60, 0.2);
        }

        .sensor-label {
            font-size: 0.7rem;
            color: var(--text-muted);
            text-transform: uppercase;
            display: block;
            margin-bottom: 5px;
        }

        .sensor-icon {
            font-size: 1.5rem;
            margin-bottom: 5px;
            display: block;
        }

        .sensor-data {
            max-height: 0;
            overflow: hidden;
            transition: max-height 0.4s ease-out;
            background: rgba(0, 0, 0, 0.2);
            border-radius: 12px;
            margin-top: 5px;
        }

        .sensor-data.show {
            max-height: 500px;
            margin-top: 15px;
            padding: 15px;
            border: 1px solid rgba(255, 255, 255, 0.05);
        }

        .stat-val { font-size: 1.8rem; font-weight: bold; color: #fff; }
        .stat-unit { font-size: 0.9rem; color: var(--crimson); margin-left: 5px; }

        /* Action Panels */
        .action-group {
            margin-top: 25px;
        }

        .btn-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(100px, 1fr));
            gap: 10px;
        }

        .btn {
            background: #1f1f21;
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 10px;
            color: white;
            padding: 12px;
            font-size: 0.85rem;
            cursor: pointer;
            transition: all 0.2s;
            text-transform: uppercase;
            font-weight: 600;
        }

        .btn:hover { background: #2a2a2d; border-color: var(--crimson); }
        .btn:active { transform: scale(0.95); }
        .btn-crimson { background: var(--crimson); border: none; }
        .btn-crimson:hover { background: var(--crimson-glow); box-shadow: 0 0 15px rgba(220, 20, 60, 0.4); }

        /* Sound Palette */
        .sound-palette {
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 8px;
        }

        @media (max-width: 500px) {
            .sound-palette { grid-template-columns: repeat(2, 1fr); }
        }

        .sound-btn {
            padding: 8px;
            font-size: 0.7rem;
            border-radius: 8px;
        }

        /* Remote Control */
        .remote {
            display: flex;
            flex-direction: column;
            gap: 20px;
            align-items: center;
        }

        .d-pad {
            display: grid;
            grid-template-columns: repeat(3, 70px);
            grid-template-rows: repeat(3, 70px);
            gap: 12px;
        }

        .num-pad {
            display: grid;
            grid-template-columns: repeat(3, 70px);
            gap: 12px;
        }

        .r-btn {
            width: 70px;
            height: 70px;
            background: #161618;
            border: 1px solid rgba(255, 255, 255, 0.05);
            border-radius: 15px;
            color: white;
            font-size: 1.3rem;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: all 0.2s;
            box-shadow: 0 5px 15px rgba(0,0,0,0.3);
        }

        .r-btn:hover { background: #202022; border-color: var(--crimson); }
        .r-btn:active { transform: translateY(2px); box-shadow: 0 2px 5px rgba(0,0,0,0.3); }
        .r-btn-ok { background: var(--crimson); box-shadow: 0 5px 15px rgba(220, 20, 60, 0.3); }

        .status-header {
            width: 100%;
            max-width: 1200px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 25px;
            padding: 0 10px;
        }

        .badge {
            padding: 6px 15px;
            border-radius: 30px;
            font-size: 0.75rem;
            font-weight: 700;
            letter-spacing: 1px;
        }

        .badge-online { background: rgba(46, 204, 113, 0.1); color: #2ecc71; border: 1px solid #2ecc71; }
        .badge-offline { background: rgba(231, 76, 60, 0.1); color: #e74c3c; border: 1px solid #e74c3c; }

        .temp-grid {
            display: grid; grid-template-columns: 1fr 1fr; gap: 10px;
        }
        .temp-box {
            background: rgba(220, 20, 60, 0.05); padding: 10px; border-radius: 10px;
            display: flex; justify-content: space-between; font-size: 0.85rem;
        }
    </style>
</head>
<body>
    <div class="status-header">
        <div style="display: flex; align-items: center; gap: 12px;">
            <div style="width: 14px; height: 14px; border-radius: 50%; background: var(--crimson); box-shadow: 0 0 15px var(--crimson);"></div>
            <span style="font-weight: 800; letter-spacing: 2px; font-size: 1.1rem;">SENTRY<span style="color:var(--crimson)">BOT</span></span>
        </div>
        <div id="status-badge" class="badge badge-offline">SİSTEM ÇEVRİMDIŞI</div>
    </div>

    <div class="container">
        <!-- Left Column: Sensors & Actions -->
        <div style="display: flex; flex-direction: column; gap: 25px;">
            <div class="card">
                <h1>Sensör Paneli</h1>
                <div class="sensor-grid">
                    <div class="sensor-btn" onclick="toggleSensor('ultra')">
                        <span class="sensor-icon">📏</span>
                        <span class="sensor-label">Ultrasonik</span>
                        <span id="label-ultra" style="font-weight:bold">-- cm</span>
                    </div>
                    <div class="sensor-btn" onclick="toggleSensor('imu')">
                        <span class="sensor-icon">📐</span>
                        <span class="sensor-label">Yönelim</span>
                        <span id="label-imu" style="font-weight:bold">-- / --</span>
                    </div>
                    <div class="sensor-btn" onclick="toggleSensor('rfid')">
                        <span class="sensor-icon">💳</span>
                        <span class="sensor-label">RFID</span>
                        <span id="label-rfid" style="font-weight:bold; font-size:0.6rem">Yok</span>
                    </div>
                    <div class="sensor-btn" onclick="toggleSensor('temps')">
                        <span class="sensor-icon">🌡️</span>
                        <span class="sensor-label">Sıcaklıklar</span>
                        <span id="label-temp-avg" style="font-weight:bold">-- °C</span>
                    </div>
                </div>

                <!-- Collapsible Data Areas -->
                <div id="data-ultra" class="sensor-data">
                    <div style="text-align:center">
                        <div class="stat-val" id="val-ultra">--</div>
                        <div class="stat-unit">Santimetre Mesafe</div>
                    </div>
                </div>

                <div id="data-imu" class="sensor-data">
                    <div style="display:flex; justify-content: space-around; text-align:center">
                        <div>
                            <div class="stat-val" id="val-pitch">--</div>
                            <div class="stat-unit">Pitch (Yunuslama)</div>
                        </div>
                        <div>
                            <div class="stat-val" id="val-roll">--</div>
                            <div class="stat-unit">Roll (Yatış)</div>
                        </div>
                    </div>
                </div>

                <div id="data-rfid" class="sensor-data">
                    <div style="text-align:center">
                        <span class="sensor-label">Okunan Son Kart UID</span>
                        <div class="stat-val" id="val-rfid" style="color:#f1c40f; font-family:monospace; font-size:1.4rem">Yok</div>
                    </div>
                </div>

                <div id="data-temps" class="sensor-data">
                    <div class="temp-grid" id="temps-container"></div>
                </div>
            </div>

            <div class="card">
                <h1>Hızlı Kontroller</h1>
                
                <div class="action-group">
                    <span class="sensor-label">Lazer Pointer</span>
                    <div class="btn-grid" style="margin-top:8px">
                        <button class="btn" onclick="sendLaser(1, true)">L1 AÇ</button>
                        <button class="btn" onclick="sendLaser(2, true)">L2 AÇ</button>
                        <button class="btn" onclick="sendLaser(0, true)">İKİSİ AÇ</button>
                        <button class="btn" style="color:var(--crimson)" onclick="sendLaser(0, false)">KAPAT</button>
                    </div>
                </div>

                <div class="action-group">
                    <span class="sensor-label">Buzzer / Ses Paleti</span>
                    <div class="sound-palette" style="margin-top:8px">
                        <button class="btn sound-btn" onclick="sendCute('happy')">Mutlu</button>
                        <button class="btn sound-btn" onclick="sendCute('super_happy')">S-Mutlu</button>
                        <button class="btn sound-btn" onclick="sendCute('sad')">Üzgün</button>
                        <button class="btn sound-btn" onclick="sendCute('surprise')">Sürpriz</button>
                        <button class="btn sound-btn" onclick="sendCute('confused')">Şaşkın</button>
                        <button class="btn sound-btn" onclick="sendCute('cuddly')">Tatlı</button>
                        <button class="btn sound-btn" onclick="sendCute('sleeping')">Uyku</button>
                        <button class="btn sound-btn" onclick="sendCute('jump')">Zıpla</button>
                        <button class="btn sound-btn" onclick="sendCute('mode1')">Mod 1</button>
                        <button class="btn sound-btn" onclick="sendCute('mode2')">Mod 2</button>
                        <button class="btn sound-btn" onclick="sendCute('mode3')">Mod 3</button>
                        <button class="btn sound-btn" onclick="sendCute('ohooh')">Ohooh</button>
                        <button class="btn sound-btn" onclick="sendSoundPlay('walle')">Wall-E</button>
                        <button class="btn sound-btn" onclick="sendSoundPlay('bb8')">BB-8</button>
                        <button class="btn sound-btn" onclick="sendCute('fart1')">Pırt 1</button>
                        <button class="btn sound-btn" onclick="sendCute('fart2')">Pırt 2</button>
                        <button class="btn sound-btn" onclick="sendCute('fart3')">Pırt 3</button>
                        <button class="btn sound-btn" style="grid-column: span 1; border-color:var(--crimson)" onclick="sendRaw('{\"cmd\":\"buzzer\",\"freq\":0,\"ms\":1}')">DUR</button>
                    </div>
                </div>
            </div>
        </div>

        <!-- Right Column: Remote Control -->
        <div class="card remote">
            <h1>IR Uzaktan Kumanda</h1>
            <div class="d-pad">
                <div></div>
                <button class="r-btn" onclick="sendRemote('UP')">▲</button>
                <div></div>
                <button class="r-btn" onclick="sendRemote('LEFT')">◀</button>
                <button class="r-btn r-btn-ok" onclick="sendRemote('OK')">OK</button>
                <button class="r-btn" onclick="sendRemote('RIGHT')">▶</button>
                <div></div>
                <button class="r-btn" onclick="sendRemote('DOWN')">▼</button>
                <div></div>
            </div>

            <div class="num-pad">
                <button class="r-btn" onclick="sendRemote('1')">1</button>
                <button class="r-btn" onclick="sendRemote('2')">2</button>
                <button class="r-btn" onclick="sendRemote('3')">3</button>
                <button class="r-btn" onclick="sendRemote('4')">4</button>
                <button class="r-btn" onclick="sendRemote('5')">5</button>
                <button class="r-btn" onclick="sendRemote('6')">6</button>
                <button class="r-btn" onclick="sendRemote('7')">7</button>
                <button class="r-btn" onclick="sendRemote('8')">8</button>
                <button class="r-btn" onclick="sendRemote('9')">9</button>
                <button class="r-btn" style="color:var(--crimson)" onclick="sendRemote('*')">*</button>
                <button class="r-btn" onclick="sendRemote('0')">0</button>
                <button class="r-btn" style="color:var(--crimson)" onclick="sendRemote('#')">#</button>
            </div>

            <button class="btn btn-crimson" style="width:100%; padding:20px; font-size:1.2rem" onclick="sendRaw('{\"cmd\":\"estop\"}')">ACİL DURDUR (E-STOP)</button>
        </div>
    </div>

    <script>
        let activeSensor = null;

        function toggleSensor(type) {
            const dataArea = document.getElementById(`data-${type}`);
            const btn = event.currentTarget;
            
            if (activeSensor && activeSensor !== type) {
                document.getElementById(`data-${activeSensor}`).classList.remove('show');
                document.querySelectorAll('.sensor-btn').forEach(b => b.classList.remove('active'));
            }

            if (dataArea.classList.contains('show')) {
                dataArea.classList.remove('show');
                btn.classList.remove('active');
                activeSensor = null;
            } else {
                // Send menu_goto to Mega to display sensor on LCD
                const menuMap = { ultra: "ultra", imu: "imu", rfid: "rfid", temps: "temps" };
                const menuName = menuMap[type] || type;
                sendAndRefresh({ cmd: "menu_goto", menu: menuName });
                
                dataArea.classList.add('show');
                btn.classList.add('active');
                activeSensor = type;
            }
        }

        function sendRemote(key) {
            fetch('/raw', { method: 'POST', body: key });
        }

        function sendRaw(json) {
            fetch('/send', { method: 'POST', body: json });
        }

        function sendAndRefresh(cmd) {
            fetch('/send', { method: 'POST', body: JSON.stringify(cmd) });
            setTimeout(() => updateStats(), 50);
        }

        function sendLaser(id, on) {
            const body = { cmd: "laser", on: on };
            if (id === 0) body.both = true;
            else body.id = id;
            sendAndRefresh(body);
        }

        function sendCute(name) {
            sendAndRefresh({ cmd: "cute", name: name });
        }

        function sendSoundPlay(name) {
            sendAndRefresh({ cmd: "sound_play", name: name });
        }

        function updateStats() {
            fetch('/api/state')
                .then(r => r.json())
                .then(data => {
                    const badge = document.getElementById('status-badge');
                    badge.className = data.link_alive ? 'badge badge-online' : 'badge badge-offline';
                    badge.innerText = data.link_alive ? 'SİSTEM ÇEVRİMİÇİ' : 'SİSTEM ÇEVRİMDIŞI';
                    
                    if (data.link_alive) {
                        // Labels (Always updated)
                        document.getElementById('label-ultra').innerText = `${data.ultra_cm.toFixed(0)} cm`;
                        document.getElementById('label-imu').innerText = `${data.pitch.toFixed(0)}° / ${data.roll.toFixed(0)}°`;
                        document.getElementById('label-rfid').innerText = data.last_rfid ? data.last_rfid.slice(-8) : 'Yok';

                        // Full Data (Updated if visible)
                        document.getElementById('val-ultra').innerText = data.ultra_cm.toFixed(1);
                        document.getElementById('val-pitch').innerText = data.pitch.toFixed(1);
                        document.getElementById('val-roll').innerText = data.roll.toFixed(1);
                        document.getElementById('val-rfid').innerText = data.last_rfid || 'Yok';

                        // Temps
                        let sum = 0, count = 0;
                        const tCont = document.getElementById('temps-container');
                        let tHtml = '';
                        data.temps.forEach((t, i) => {
                            if (!isNaN(t) && t !== null) {
                                tHtml += `<div class="temp-box"><span>Sensör ${i+1}</span> <b>${t.toFixed(1)}°C</b></div>`;
                                sum += t; count++;
                            }
                        });
                        tCont.innerHTML = tHtml;
                        if (count > 0) document.getElementById('label-temp-avg').innerText = `${(sum/count).toFixed(1)} °C`;
                    }
                })
                .catch(e => console.error("Poll error", e));
        }

        setInterval(updateStats, 200);
        updateStats();
    </script>
</body>
</html>
)=====";

#endif
