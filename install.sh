#!/usr/bin/env bash
# =============================================================================
# Whisper Voice OS - 1-Line Installer & Setup Script
# Works on any Linux machine with an NVIDIA GPU, PipeWire, and Wayland.
# =============================================================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}=== Installing Local Whisper Voice OS ===${NC}"

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="$HOME/.local/bin"
SHARE_DIR="$HOME/.local/share/whisper-ptt"
CONFIG_DIR="$HOME/.config/whisper-ptt"
SYSTEMD_USER_DIR="$HOME/.config/systemd/user"

mkdir -p "$BIN_DIR" "$SHARE_DIR" "$CONFIG_DIR" "$SYSTEMD_USER_DIR"

# 1. Check for required system tools
echo -e "\n${YELLOW}[1/6] Checking system tools...${NC}"
MISSING_TOOLS=()
for tool in pw-record ffmpeg wtype wl-copy notify-send; do
    if ! command -v "$tool" >/dev/null 2>&1; then
        MISSING_TOOLS+=("$tool")
    fi
done

if [ ${#MISSING_TOOLS[@]} -ne 0 ]; then
    echo -e "${YELLOW}Missing recommended packages: ${MISSING_TOOLS[*]}${NC}"
    echo "You can install them on Ubuntu/Debian with:"
    echo "  sudo apt install -y pipewire-bin ffmpeg wtype wl-clipboard libnotify-bin"
fi

# 2. Check for UV (Python package manager)
echo -e "\n${YELLOW}[2/6] Checking Python & uv...${NC}"
if ! command -v uv >/dev/null 2>&1; then
    echo "Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi

# 3. Setup Python Virtual Environment with CUDA acceleration
echo -e "\n${YELLOW}[3/6] Setting up Whisper virtual environment (CUDA)...${NC}"
VENV_DIR="$SHARE_DIR/venv"
uv venv "$VENV_DIR" --python 3.12 --allow-existing

PKGS=(faster-whisper "av<14")
HAS_CUDA=0
if command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi >/dev/null 2>&1; then
    HAS_CUDA=1
    PKGS+=(nvidia-cublas-cu12 nvidia-cudnn-cu12)
    echo "Installing faster-whisper and CUDA 12 runtimes..."
else
    echo "No NVIDIA GPU found, installing CPU-only faster-whisper..."
fi
uv pip install --python "$VENV_DIR" "${PKGS[@]}"

# 4. Copy daemon and scripts
echo -e "\n${YELLOW}[4/6] Installing scripts and daemon...${NC}"
cp -f "$REPO_DIR/daemon/daemon.py" "$SHARE_DIR/"
cp -f "$REPO_DIR/daemon/start-daemon.sh" "$SHARE_DIR/"
cp -f "$REPO_DIR/daemon/client.py" "$SHARE_DIR/"
cp -f "$REPO_DIR/daemon/llm_command.py" "$SHARE_DIR/"
chmod +x "$SHARE_DIR/start-daemon.sh" "$SHARE_DIR/daemon.py" "$SHARE_DIR/client.py" "$SHARE_DIR/llm_command.py"

cp -f "$REPO_DIR/bin/whisper-ptt" "$REPO_DIR/bin/ask" "$BIN_DIR/"
chmod +x "$BIN_DIR/whisper-ptt" "$BIN_DIR/ask"
# Flatpak launcher shims: never clobber an existing binary of the same name
for f in "$REPO_DIR/bin/"{discord,google-chrome,obsidian,zen}; do
    [ -e "$BIN_DIR/$(basename "$f")" ] || install -m 755 "$f" "$BIN_DIR/"
done

# Copy config if not already present
if [ ! -f "$CONFIG_DIR/config.json" ]; then
    cp "$REPO_DIR/config/config.json" "$CONFIG_DIR/config.json"
    if [ "$HAS_CUDA" -eq 0 ]; then
        sed -i 's/"cuda"/"cpu"/; s/"float16"/"int8"/; s/"large-v3-turbo"/"small.en"/' "$CONFIG_DIR/config.json"
    fi
fi

# 5. Setup Systemd User Service
echo -e "\n${YELLOW}[5/6] Enabling Whisper systemd user service...${NC}"
cp -f "$REPO_DIR/config/whisper-ptt.service" "$SYSTEMD_USER_DIR/"
systemctl --user daemon-reload
systemctl --user enable --now whisper-ptt.service

# 6. Hyprland Keybindings check
echo -e "\n${YELLOW}[6/6] Hyprland keybindings check...${NC}"
HYPR_CONF="$HOME/.config/hypr/hyprland.conf"
if [ -f "$HYPR_CONF" ]; then
    if ! grep -q "whisper-ptt" "$HYPR_CONF"; then
        echo "Appending keybindings to $HYPR_CONF..."
        echo "" >> "$HYPR_CONF"
        cat "$REPO_DIR/config/hyprland-bindings.conf" >> "$HYPR_CONF"
        if command -v hyprctl >/dev/null 2>&1; then
            hyprctl reload >/dev/null 2>&1 || true
        fi
        echo -e "${GREEN}✓ Keybindings added and Hyprland reloaded!${NC}"
    else
        echo -e "${GREEN}✓ Keybindings already present in $HYPR_CONF.${NC}"
    fi
else
    echo "Hyprland config not found at $HYPR_CONF. See config/hyprland-bindings.conf for keybinding examples."
fi

echo -e "\n${GREEN}======================================================${NC}"
echo -e "${GREEN}✓ Local Whisper Voice OS successfully installed!${NC}"
echo -e "${GREEN}======================================================${NC}"
echo "Keybindings:"
echo "  - Super + Space       : Voice Dictation (Speech to text)"
echo "  - Super + C           : Voice OS / Shell Command via local Ollama"
echo "  - Super + Shift + Space: Voice OS / Shell Command"
echo ""
echo "CLI tools:"
echo "  - ask <prompt>        : Natural language to shell command"
echo "  - whisper-ptt toggle  : Start/stop dictation"
echo ""
echo "Service status:"
echo "  systemctl --user status whisper-ptt.service"
