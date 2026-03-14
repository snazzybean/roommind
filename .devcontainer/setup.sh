#!/bin/bash

# RoomMind Devcontainer Setup Script

set -e

WORKSPACE="/workspaces/roommind"

echo "Setting up RoomMind development environment..."

# ---------------------------------------------------------------------------
# System packages
# ---------------------------------------------------------------------------
echo "Updating system packages..."
# Remove Yarn repo if present — its GPG key frequently expires and blocks apt-get update
sudo rm -f /etc/apt/sources.list.d/yarn.list
sudo apt-get update
sudo apt-get install -y \
    build-essential \
    pkg-config \
    libffi-dev \
    libssl-dev \
    libjpeg-dev \
    zlib1g-dev \
    autoconf \
    automake \
    libtool \
    ffmpeg \
    libavformat-dev \
    libavcodec-dev \
    libavdevice-dev \
    libavutil-dev \
    libswscale-dev \
    libswresample-dev \
    libavfilter-dev \
    libtiff5-dev \
    libjpeg62-turbo-dev \
    libopenjp2-7-dev \
    libfreetype6-dev \
    liblcms2-dev \
    libwebp-dev \
    tcl8.6-dev \
    tk8.6-dev \
    python3-tk \
    libharfbuzz-dev \
    libfribidi-dev \
    libxcb1-dev \
    libpcap-dev \
    libpcap0.8

# ---------------------------------------------------------------------------
# Python dependencies
# ---------------------------------------------------------------------------
echo "Installing Python dependencies..."
pip install --upgrade pip setuptools wheel

echo "Installing Home Assistant..."
pip install homeassistant

echo "Installing development dependencies..."
pip install pytest-homeassistant-custom-component

pip install \
    pytest \
    pytest-asyncio \
    pytest-cov \
    voluptuous \
    ruff \
    mypy \
    pre-commit

# Performance libraries to suppress HA warnings
echo "Installing performance libraries..."
pip install zlib-ng isal

# ---------------------------------------------------------------------------
# Home Assistant config directory (set up BEFORE ensure_config)
# ---------------------------------------------------------------------------
echo "Setting up Home Assistant config directory..."
sudo mkdir -p /config/custom_components
sudo mkdir -p /config/logs
sudo mkdir -p /config/blueprints/automation
sudo mkdir -p /config/blueprints/script

echo "Setting up permissions..."
sudo chown -R vscode:vscode /config

echo "Setting up configuration..."
cp "${WORKSPACE}/.devcontainer/configuration.yaml" /config/configuration.yaml
cp "${WORKSPACE}/.devcontainer/automations.yaml"   /config/automations.yaml
cp "${WORKSPACE}/.devcontainer/scripts.yaml"       /config/scripts.yaml
cp "${WORKSPACE}/.devcontainer/scenes.yaml"        /config/scenes.yaml

# Symlink the custom component into HA
echo "Linking custom component..."
ln -sf "${WORKSPACE}/custom_components/roommind" /config/custom_components/roommind

# ---------------------------------------------------------------------------
# Pre-install HA component dependencies
# ---------------------------------------------------------------------------
# pip install homeassistant only installs the base package; built-in
# components lazily pip-install their deps at runtime, which causes
# transient ModuleNotFoundErrors on first boot. Pre-install the known
# packages so HA starts cleanly on every boot.
echo "Pre-installing HA component dependencies..."
pip install hassil mutagen home-assistant-intents home-assistant-frontend

# ---------------------------------------------------------------------------
# Frontend dependencies
# ---------------------------------------------------------------------------
echo "Installing frontend dependencies..."
cd "${WORKSPACE}/frontend"
npm ci
cd "${WORKSPACE}"

# ---------------------------------------------------------------------------
# Helper scripts
# ---------------------------------------------------------------------------
cat > /config/start_ha.sh << 'EOF'
#!/bin/bash
pkill -f "hass --config" 2>/dev/null; sleep 1
echo "Starting Home Assistant..."
hass --config /config --log-file /config/logs/home-assistant.log
EOF
chmod +x /config/start_ha.sh

cat > /config/restart_ha.sh << 'EOF'
#!/bin/bash
echo "Restarting Home Assistant..."
pkill -f "hass --config" 2>/dev/null || true
sleep 2
/config/start_ha.sh
echo "Home Assistant restarted"
EOF
chmod +x /config/restart_ha.sh

cat > /config/logs.sh << 'EOF'
#!/bin/bash
tail -f /config/logs/home-assistant.log
EOF
chmod +x /config/logs.sh

cat > /config/check_setup.sh << 'EOF'
#!/bin/bash
echo "Checking development environment..."

echo ""
echo "Custom components directory:"
ls -la /config/custom_components/

echo ""
echo "RoomMind integration link:"
ls -la /config/custom_components/roommind

echo ""
echo "Configuration file:"
head -10 /config/configuration.yaml

echo ""
echo "Python packages:"
pip list 2>/dev/null | grep -iE "(homeassistant|voluptuous|pytest)"

echo ""
echo "Testing Home Assistant imports:"
python3 -c "
from homeassistant.const import __version__
print(f'  homeassistant {__version__}')

import voluptuous
print('  voluptuous OK')

from custom_components.roommind import DOMAIN
print(f'  roommind integration OK (domain={DOMAIN})')
" || echo "Import check failed"

echo ""
echo "Node / frontend:"
node --version 2>/dev/null | xargs -I{} echo "  node {}"
npx tsc --version 2>/dev/null | xargs -I{} echo "  tsc {}"

echo ""
echo "Environment check complete!"
EOF
chmod +x /config/check_setup.sh

# ---------------------------------------------------------------------------
# Pre-commit hooks
# ---------------------------------------------------------------------------
echo "Installing pre-commit hooks..."
cd "${WORKSPACE}"
pre-commit install

# ---------------------------------------------------------------------------
# Build frontend once so HA can load the panel
# ---------------------------------------------------------------------------
echo "Building frontend..."
cd "${WORKSPACE}/frontend"
npm run build
cd "${WORKSPACE}"

# ---------------------------------------------------------------------------
# Verify
# ---------------------------------------------------------------------------
echo ""
echo "Verifying environment..."
python -c "from homeassistant.const import __version__; print('  homeassistant', __version__)"
python -c "import voluptuous; print('  voluptuous OK')"
python -c "import pytest; print('  pytest', pytest.__version__)"
node --version | xargs -I{} echo "  node {}"
npx --prefix "${WORKSPACE}/frontend" tsc --version | xargs -I{} echo "  tsc {}"
echo ""
echo "Development environment ready!"
echo ""
echo "Home Assistant will start automatically on every container start."
echo ""
echo "  Home Assistant: http://localhost:8123"
echo "  Integration:    symlinked at /config/custom_components/roommind"
echo ""
echo "  /config/restart_ha.sh   - restart HA"
echo "  /config/logs.sh         - tail HA logs"
echo "  /config/check_setup.sh  - verify environment"
echo "  npm run build           - rebuild frontend (in frontend/)"
echo "  pytest tests/ -x        - run backend tests"
