#!/usr/bin/env bash
# install_all.sh — Complete SentryBOT dependency installer
# Run on Raspberry Pi 5 as sentrybot user (not root for pip parts)
# Usage: bash install_all.sh [--insecure] [--skip-system] [--skip-models]

set -euo pipefail

INSECURE="${1:-}"
SKIP_SYSTEM="${2:-}"
SKIP_MODELS="${3:-}"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

echo "======================================"
echo "  SentryBOT Full Dependency Installer"
echo "======================================"
echo "Repo: $REPO_ROOT"
echo "User: $(whoami)"
echo "Date: $(date)"
echo ""

# -------------------------------------------------------------------
# 1. SYSTEM PACKAGES (apt) — run once, needs sudo
# -------------------------------------------------------------------
install_system_packages() {
    if [[ "$SKIP_SYSTEM" == "--skip-system" ]]; then
        echo "[SKIP] System packages (--skip-system)"
        return
    fi

    echo "[1/6] Installing system packages (apt)..."
    sudo apt-get update -y

    # Core build tools & Python
    sudo apt-get install -y \
        python3 python3-pip camera-devices \
        python3-venv python3-dev \
        build-essential cmake pkg-config \
        libopenblas-dev libatlas-base-dev \
        libjpeg-dev libpng-dev libtiff-dev \
        libavcodec-dev libavformat-dev libswscale-dev \
        libv4l-dev libxvidcore-dev libx264-dev \
        libgtk-3-dev libcanberra-gtk3-module \
        libatlas-base-dev gfortran \
        libhdf5-dev libhdf5-serial-dev \
        libqtgui4 libqtwebkit4 libqt4-test \
        python3-pyqt5 \
        v4l-utils \
        i2c-tools \
        git curl wget unzip \
        certifi ca-certificates

    # IMX500 firmware & picamera2 deps
    sudo apt-get install -y \
        libcamera-dev libcamera-apps \
        imx500-firmware \
        rpicam-apps \
        || echo "Warning: Some camera packages may not be available on this OS version"

    # Audio
    sudo apt-get install -y \
        alsa-utils pulseaudio \
        libasound2-dev portaudio19-dev \
        libsndfile1

    echo "✓ System packages done"
}

# -------------------------------------------------------------------
# 2. PYTHON VENV & PIP DEPENDENCIES
# -------------------------------------------------------------------
setup_venv_and_pip() {
    echo "[2/6] Setting up Python venv & pip deps..."

    # Create venv if not exists
    if [[ ! -d ".venv" ]]; then
        python3 -m venv .venv
    fi

    # Activate
    source .venv/bin/activate

    # Upgrade pip/setuptools/wheel
    pip install --upgrade pip setuptools wheel

    # Core requirements files (if they exist)
    for req in requirements.txt requirements-pi.txt requirements-cpu.txt; do
        if [[ -f "$req" ]]; then
            echo "Installing $req..."
            pip install -r "$req"
        fi
    done

    # Core ML / Vision deps
    pip install --no-cache-dir \
        numpy==1.26.4 \
        opencv-python-headless==4.10.0.84 \
        Pillow==10.4.0 \
        pyyaml==6.0.1 \
        requests==2.32.3 \
        fastapi==0.112.0 \
        uvicorn[standard]==0.30.5 \
        pydantic==2.8.2 \
        pydantic-settings==2.4.1 \
        ollama==0.4.2 \
        onnxruntime==1.19.2 \
        onnx==1.16.1 \
        torch==2.4.0 --index-url https://download.pytorch.org/whl/cpu \
        torchvision==0.19.0 --index-url https://download.pytorch.org/whl/cpu \
        ultralytics==8.2.100 \
        supervision==0.21.0 \
        filterpy==1.4.5 \
        scipy==1.13.1 \
        scikit-learn==1.5.1 \
        transformers==4.44.0 \
        huggingface-hub==0.24.5 \
        tokenizers==0.19.1 \
        accelerate==0.33.0 \
        safetensors==0.4.4

    # Audio / Speech
    pip install --no-cache-dir \
        vosk==0.3.45 \
        pyaudio==0.2.14 \
        webrtcvad==2.0.10 \
        soundfile==0.12.1 \
        librosa==0.10.2 \
        openwakeword==0.4.1 \
        piper-tts==1.2.0 \
        piper-phonemize==1.0.1 \
        faster-whisper==1.0.3

    # Hardware / Serial / GPIO
    pip install --no-cache-dir \
        pyserial==3.5 \
        pigpio==1.78 \
        smbus2==0.4.3 \
        adafruit-blinka==9.4.5 \
        adafruit-circuitpython-pca9685==3.3.10 \
        adafruit-circuitpython-motor==3.3.10 \
        RPi.GPIO==0.7.1

    # Config / Utils
    pip install --no-cache-dir \
        python-dotenv==1.0.1 \
        watchdog==4.0.1 \
        psutil==5.9.8 \
        colorlog==6.8.2 \
        tqdm==4.66.5 \
        rich==13.7.1 \
        click==8.1.7

    echo "✓ Python dependencies done"
}

# -------------------------------------------------------------------
# 3. VOSK MODELS
# -------------------------------------------------------------------
install_vosk_models() {
    if [[ "$SKIP_MODELS" == "--skip-models" ]]; then
        echo "[SKIP] Vosk models (--skip-models)"
        return
    fi

    echo "[3/6] Installing Vosk models..."

    source .venv/bin/activate
    python scripts/setup/install_vosk_tr.py ${INSECURE:+"--insecure"}
    python scripts/setup/install_vosk_en.py ${INSECURE:+"--insecure"} 2>/dev/null || true

    echo "✓ Vosk models done"
}

# -------------------------------------------------------------------
# 4. PIPER TTS MODELS
# -------------------------------------------------------------------
install_piper_models() {
    if [[ "$SKIP_MODELS" == "--skip-models" ]]; then
        echo "[SKIP] Piper models (--skip-models)"
        return
    fi

    echo "[4/6] Installing Piper TTS models..."

    source .venv/bin/activate
    python scripts/setup/install_piper_models.py --turkish ${INSECURE:+"--insecure"}
    python scripts/setup/install_piper_models.py --glados ${INSECURE:+"--insecure"} 2>/dev/null || true

    echo "✓ Piper models done"
}

# -------------------------------------------------------------------
# 5. CAMERA / IMX500 FIRMWARE
# -------------------------------------------------------------------
install_camera_firmware() {
    echo "[5/6] Setting up Camera / IMX500..."

    # Check if IMX500 firmware exists
    if [[ ! -f /usr/share/imx500-models/imx500_network_ssd_mobilenetv2_fpnlite_320x320_pp.rpk ]]; then
        echo "IMX500 firmware not found, attempting to install..."
        sudo apt-get install -y imx500-firmware 2>/dev/null || {
            echo "Could not install via apt, downloading manually..."
            sudo mkdir -p /usr/share/imx500-models
            cd /tmp
            wget -q "https://github.com/raspberrypi/imx500-firmware/raw/main/imx500_network_ssd_mobilenetv2_fpnlite_320x320_pp.rpk" \
                -O imx500_network_ssd_mobilenetv2_fpnlite_320x320_pp.rpk || true
            if [[ -f imx500_network_ssd_mobilenetv2_fpnlite_320x320_pp.rpk ]]; then
                sudo cp imx500_network_ssd_mobilenetv2_fpnlite_320x320_pp.rpk /usr/share/imx500-models/
                echo "✓ IMX500 firmware installed"
            else
                echo "⚠ Could not download IMX500 firmware"
            fi
        }
    else
        echo "✓ IMX500 firmware already present"
    fi

    # Test picamera2
    source .venv/bin/activate
    python -c "import picamera2; print('✓ picamera2 OK')" 2>/dev/null || {
        echo "Installing picamera2..."
        pip install picamera2==0.3.24
    }

    echo "✓ Camera setup done"
}

# -------------------------------------------------------------------
# 6. AUDIO / PERMISSIONS / FINISH
# -------------------------------------------------------------------
setup_audio_permissions() {
    echo "[6/6] Configuring audio & permissions..."

    # Add user to audio/gpio/video groups
    sudo usermod -a -G audio,gpio,video,i2c,spi $(whoami) 2>/dev/null || true

    # ALSA config for plughw:0,0
    if [[ ! -f ~/.asoundrc ]]; then
        cat > ~/.asoundrc <<'EOF'
pcm.!default {
    type asym
    playback.pcm "plughw:0,0"
    capture.pcm "plughw:0,0"
}
ctl.!default {
    type hw
    card 0
}
EOF
        echo "✓ Created ~/.asoundrc"
    fi

    # Test audio devices
    echo "Audio devices:"
    arecord -l 2>/dev/null | head -10 || echo "No capture devices found"
    aplay -l 2>/dev/null | head -10 || echo "No playback devices found"

    echo ""
    echo "======================================"
    echo "  INSTALLATION COMPLETE"
    echo "======================================"
    echo ""
    echo "Next steps:"
    echo "  1. Reboot (for group changes): sudo reboot"
    echo "  2. Test: source .venv/bin/activate && python -m sentrybot"
    echo "  3. Check config: cat config/agent.yaml | grep -A5 'esp_base_url'"
    echo ""
}

# -------------------------------------------------------------------
# MAIN
# -------------------------------------------------------------------
main() {
    echo "Starting full SentryBOT installation..."
    echo "Args: INSECURE=${INSECURE} SKIP_SYSTEM=${SKIP_SYSTEM} SKIP_MODELS=${SKIP_MODELS}"
    echo ""

    install_system_packages
    setup_venv_and_pip
    install_vosk_models
    install_piper_models
    install_camera_firmware
    setup_audio_permissions

    echo "All done! ✓"
}

main "$@"