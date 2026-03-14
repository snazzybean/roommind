#!/bin/bash

# RoomMind Devcontainer Setup Script

set -e

echo "Setting up RoomMind development environment..."

# ---------------------------------------------------------------------------
# System packages
# ---------------------------------------------------------------------------
echo "Installing system packages..."
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

echo "Installing development & test dependencies..."
pip install \
    pytest \
    pytest-asyncio \
    pytest-cov \
    voluptuous \
    ruff \
    mypy \
    pre-commit

# Performance libraries to suppress HA warnings
pip install zlib-ng isal

# ---------------------------------------------------------------------------
# Frontend dependencies
# ---------------------------------------------------------------------------
WORKSPACE="/workspaces/roommind"

echo "Installing frontend dependencies..."
cd "${WORKSPACE}/frontend"
npm ci
cd "${WORKSPACE}"

# ---------------------------------------------------------------------------
# Home Assistant config directory
# ---------------------------------------------------------------------------
echo "Setting up Home Assistant config directory..."
sudo mkdir -p /config/custom_components
sudo mkdir -p /config/logs
sudo mkdir -p /config/blueprints/automation
sudo mkdir -p /config/blueprints/script
sudo chown -R vscode:vscode /config

# Copy HA config files
cp "${WORKSPACE}/.devcontainer/configuration.yaml" /config/configuration.yaml
cp "${WORKSPACE}/.devcontainer/automations.yaml"   /config/automations.yaml
cp "${WORKSPACE}/.devcontainer/scripts.yaml"       /config/scripts.yaml
cp "${WORKSPACE}/.devcontainer/scenes.yaml"        /config/scenes.yaml

# Symlink the custom component into HA
ln -sf "${WORKSPACE}/custom_components/roommind" /config/custom_components/roommind

# ---------------------------------------------------------------------------
# Helper scripts
# ---------------------------------------------------------------------------
cat > /config/start_ha.sh << 'SCRIPT'
#!/bin/bash
echo "Starting Home Assistant..."
cd /config
hass --config /config --log-file /config/logs/home-assistant.log &
disown
SCRIPT
chmod +x /config/start_ha.sh

cat > /config/restart_ha.sh << 'SCRIPT'
#!/bin/bash
echo "Restarting Home Assistant..."
pkill -f "hass --config" || true
sleep 2
/config/start_ha.sh
echo "Home Assistant restarted"
SCRIPT
chmod +x /config/restart_ha.sh

cat > /config/logs.sh << 'SCRIPT'
#!/bin/bash
tail -f /config/logs/home-assistant.log
SCRIPT
chmod +x /config/logs.sh

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
npx --yes tsc --version | xargs -I{} echo "  tsc {}"
echo ""
echo "Development environment ready!"
echo ""
echo "  Home Assistant: http://localhost:8123"
echo "  Integration:    symlinked at /config/custom_components/roommind"
echo ""
echo "  /config/restart_ha.sh   - restart HA"
echo "  /config/logs.sh         - tail HA logs"
echo "  npm run build           - rebuild frontend (in frontend/)"
echo "  pytest tests/ -x        - run backend tests"
