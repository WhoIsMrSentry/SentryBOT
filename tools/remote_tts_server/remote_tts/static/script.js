let piperData = [];
let xttsData = [];
let selectedFile = null;

// Initialization
document.addEventListener('DOMContentLoaded', async () => {
    setupDragAndDrop();
    await fetchCatalogs();
    handleEngineChange();
});

function showToast(msg, isError = false) {
    const toast = document.getElementById('toast');
    toast.textContent = msg;
    if (isError) toast.classList.add('error');
    else toast.classList.remove('error');

    toast.classList.add('show');
    setTimeout(() => {
        toast.classList.remove('show');
    }, 3000);
}

async function fetchCatalogs() {
    try {
        const pRes = await fetch('/tts/voices/piper');
        const pJson = await pRes.json();
        piperData = pJson.voices || [];

        const xRes = await fetch('/tts/voices/xtts');
        const xJson = await xRes.json();
        xttsData = xJson.voices || [];
    } catch (err) {
        showToast("Failed to fetch catalogs", true);
        console.error(err);
    }
}

async function refreshCatalogs() {
    try {
        await fetch('/tts/refresh', { method: 'POST' });
        await fetchCatalogs();
        handleEngineChange();
        showToast("Catalog refreshed");
    } catch (err) {
        showToast("Failed to refresh catalog", true);
    }
}

function handleEngineChange() {
    const engine = document.getElementById('engine-select').value;
    const langSelect = document.getElementById('language-select');
    const data = engine === 'piper' ? piperData : xttsData;

    // Extract unique languages
    const langs = [...new Set(data.map(v => v.language))].sort();

    langSelect.innerHTML = '';
    if (langs.length === 0) {
        langSelect.innerHTML = '<option value="">No languages found</option>';
    } else {
        langs.forEach(l => {
            const opt = document.createElement('option');
            opt.value = l;
            opt.textContent = l;
            langSelect.appendChild(opt);
        });
    }

    handleLanguageChange();
}

function handleLanguageChange() {
    const engine = document.getElementById('engine-select').value;
    const lang = document.getElementById('language-select').value;
    const modelSelect = document.getElementById('model-select');
    const data = engine === 'piper' ? piperData : xttsData;

    const filtered = data.filter(v => v.language === lang);

    modelSelect.innerHTML = '';
    if (filtered.length === 0) {
        modelSelect.innerHTML = '<option value="">No models found</option>';
    } else {
        filtered.forEach(v => {
            const opt = document.createElement('option');
            if (engine === 'piper') {
                opt.value = v.model;
                opt.textContent = `${v.model} (${v.quality || 'N/A'}) - spks: ${v.num_speakers || 1}`;
            } else {
                opt.value = v.filename;
                opt.textContent = v.filename;
            }
            modelSelect.appendChild(opt);
        });
    }
}

// File Upload Handling
function setupDragAndDrop() {
    const dropArea = document.getElementById('upload-area');
    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        dropArea.addEventListener(eventName, preventDefaults, false);
    });

    function preventDefaults(e) {
        e.preventDefault();
        e.stopPropagation();
    }

    ['dragenter', 'dragover'].forEach(eventName => {
        dropArea.addEventListener(eventName, () => {
            dropArea.style.borderColor = 'var(--primary)';
            dropArea.style.background = 'rgba(74, 222, 128, 0.05)';
        }, false);
    });

    ['dragleave', 'drop'].forEach(eventName => {
        dropArea.addEventListener(eventName, () => {
            dropArea.style.borderColor = 'var(--glass-border)';
            dropArea.style.background = 'transparent';
        }, false);
    });

    dropArea.addEventListener('drop', (e) => {
        const dt = e.dataTransfer;
        const files = dt.files;
        if (files.length) {
            processFile(files[0]);
        }
    }, false);
}

function handleFileSelect(e) {
    if (e.target.files.length) {
        processFile(e.target.files[0]);
    }
}

function processFile(file) {
    if (!file.name.toLowerCase().endsWith('.wav')) {
        showToast("Only .wav files are supported", true);
        return;
    }
    selectedFile = file;
    document.getElementById('upload-text').innerHTML = `Selected: <span>${file.name}</span>`;
    const btn = document.getElementById('upload-btn');
    btn.disabled = false;
    btn.style.opacity = '1';
}

async function uploadVoice() {
    if (!selectedFile) return;

    const btn = document.getElementById('upload-btn');
    const spinner = document.getElementById('upload-spinner');

    btn.disabled = true;
    spinner.style.display = 'block';

    const formData = new FormData();
    formData.append("file", selectedFile);

    try {
        const res = await fetch('/tts/voices/xtts/upload', {
            method: 'POST',
            body: formData
        });

        if (!res.ok) throw new Error(await res.text());

        showToast(`Successfully uploaded ${selectedFile.name}`);

        // Reset upload area
        selectedFile = null;
        document.getElementById('upload-text').innerHTML = `Drag & drop or <span>browse</span> for a .wav file`;
        document.getElementById('file-input').value = '';
        btn.style.opacity = '0.5';

        // Refresh data
        await fetchCatalogs();
        handleEngineChange();

        // Select the freshly uploaded voice if currently in XTTS
        if (document.getElementById('engine-select').value === 'xtts') {
            // Try to wait for the UI to update options, then select it.
            setTimeout(() => {
                const sel = document.getElementById('model-select');
                for (let i = 0; i < sel.options.length; i++) {
                    if (sel.options[i].text === res.filename) { // wait, I returned filename from server. Actually, let's just select by index.
                        sel.selectedIndex = i;
                        break;
                    }
                }
            }, 50);
        }

    } catch (err) {
        showToast(`Upload failed: ${err.message}`, true);
    } finally {
        spinner.style.display = 'none';
    }
}

async function synthesize() {
    const engine = document.getElementById('engine-select').value;
    const language = document.getElementById('language-select').value;
    const modelVal = document.getElementById('model-select').value;
    const text = document.getElementById('tts-text').value.trim();

    if (!text) {
        showToast("Please enter some text to synthesize", true);
        document.getElementById('tts-text').focus();
        return;
    }

    if (!modelVal) {
        showToast("Please select a voice model/source", true);
        return;
    }

    const payload = {
        engine: engine,
        text: text,
        language: language,
        response_format: "wav"
    };

    if (engine === 'piper') {
        payload.piper = { model: modelVal };
    } else {
        payload.speaker_wav = modelVal;
        payload.xtts = {};
    }

    const btn = document.querySelector('.full-width .btn-primary');
    const spinner = document.getElementById('synth-spinner');
    btn.disabled = true;
    spinner.style.display = 'block';

    try {
        const res = await fetch('/tts/synthesize', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        if (!res.ok) {
            throw new Error(await res.text());
        }

        const blob = await res.blob();
        const url = URL.createObjectURL(blob);

        const aud = document.getElementById('audio-player');
        const audContainer = document.getElementById('audio-container');
        aud.src = url;
        audContainer.style.display = 'block';
        aud.play();

        showToast("Synthesis complete!");
    } catch (err) {
        showToast(`Synthesis failed: ${err.message}`, true);
        console.error(err);
    } finally {
        btn.disabled = false;
        spinner.style.display = 'none';
    }
}