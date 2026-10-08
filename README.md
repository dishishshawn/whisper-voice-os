# 🎙️ Whisper Voice OS

> A 100% private, offline, sub-500ms voice-controlled Linux operating system and speech dictation engine powered by local **Whisper** and local **Ollama** on GPU.

---

## ⚡ Features

- **100% Local & Private**: Zero cloud, zero telemetry, zero API keys or token costs. Operates completely offline.
- **Ultra-Low Latency**:
  - **Speech-to-Text**: `large-v3-turbo` running via `faster-whisper` on CUDA in **~120ms**.
  - **Intent-to-Command**: Local Ollama (`qwen3:14b`) with zero-latency prefill in **~250ms**.
  - **Total Pipeline**: Under **0.5 seconds** from voice end to executed command.
- **Pre-warmed GPU Daemon**: Runs in background via a `systemd --user` service. Keeps model in VRAM (~1.5GB) with CUDA kernels warmed up so there is zero cold-start delay.
- **Live Top Bar Feedback (Waybar)**: Integrated status pill in the top bar showing live state (`Idle`, `Dictating`, `Thinking`, `Running`) with interactive left/right click toggles.
- **Context-Aware Dev & Cloud Code Intelligence**:
  - Automatically identifies current working directory of the active terminal shell via `/proc`.
  - Detects active tech stack: Git branch & uncommitted status, Docker & Docker Compose, local Supabase, Bun vs Node/npm, Justfile recipes, Rust, Python.
  - Clipboard error inspection: automatically reads compiler errors, traces, and snippets from clipboard when asking to fix or debug.
- **Agentic Multi-Step Desktop Execution**: Generates safe compound workflows (`&&`, subshells `(...) &`), process management, and diagnostic notifications.

- **Silero VAD Built-in**: Discards ambient noise and prevents hallucinations.
- **Subtle Feedback**: Gentle, non-intrusive audio cues (25% volume) and desktop notifications via `notify-send` / SwayNC.

---

## 🎛️ Default Keybindings

| Keybinding | Mode | Description |
| :--- | :--- | :--- |
| <kbd>Super</kbd> + <kbd>Space</kbd> | **Voice Dictation** | Tap to speak, tap again to type anywhere (virtual keyboard + clipboard). |
| <kbd>Super</kbd> + <kbd>C</kbd> | **Voice OS Command** | Tap to speak natural language intent (e.g. *"mute audio"*, *"go to workspace 5 and open YouTube in Chrome"*, *"install obsidian"*). |
| <kbd>Super</kbd> + <kbd>Shift</kbd> + <kbd>Space</kbd> | **Voice OS Command** | Alternative hotkey for Voice OS command generation. |

> **Natural Voice Prefixes:** You can also use your regular dictation key (<kbd>Super</kbd> + <kbd>Space</kbd>) and say *"command ..."* or *"run ..."* to automatically route to the LLM!

---

## 💻 CLI Helper: `ask`

You can also trigger the natural language assistant directly from your terminal:

```bash
ask install obsidian
# ⚡ Command: flatpak install --user -y flathub md.obsidian.Obsidian
# Execute this command? [Y/n]
```

Or run `ask` by itself to dictate via microphone.

---

## 🚀 Quick Install (On Any Computer)

Clone this repository and run the installer:

```bash
git clone https://github.com/dishishshawn/whisper-voice-os.git
cd whisper-voice-os
./install.sh
```

The installer will:
1. Check for required system tools (`pw-record`, `ffmpeg`, `wtype`, `wl-clipboard`).
2. Set up a Python virtual environment with `uv` and CUDA runtime libraries (`nvidia-cublas-cu12`, `nvidia-cudnn-cu12`).
3. Install and pre-warm the Whisper daemon as a `systemd --user` service.
4. Install all CLI helpers to `~/.local/bin/`.
6. Install the Waybar status module (`whisper-waybar`) to `~/.local/bin/`.

### 📊 Waybar Top Bar Setup

Add `"custom/whisper"` to your `~/.config/waybar/config.jsonc`:

```jsonc
"custom/whisper": {
  "format": "{}",
  "return-type": "json",
  "exec": "/home/<user>/.local/bin/whisper-waybar",
  "on-click": "/home/<user>/.local/bin/whisper-ptt toggle",
  "on-click-right": "/home/<user>/.local/bin/whisper-ptt command-toggle",
  "signal": 8,
  "tooltip": true
}
```

And add the styling to `~/.config/waybar/style.css`:

```css
#custom-whisper {
  background: rgba(255, 255, 255, 0.08);
  border-radius: 9999px;
  padding: 0 10px;
}
#custom-whisper.recording { background: rgba(237, 135, 150, 0.25); color: #ed8796; }
#custom-whisper.thinking  { background: rgba(238, 212, 159, 0.25); color: #eed49f; }
#custom-whisper.executing { background: rgba(166, 218, 149, 0.25); color: #a6da95; }
```

---

## ⚙️ Configuration

Custom settings live in `~/.config/whisper-ptt/config.json`:

```json
{
  "model": "large-v3-turbo",
  "device": "cuda",
  "compute_type": "float16",
  "language": "en",
  "beam_size": 1,
  "vad_filter": true,
  "sound_enabled": true,
  "sound_volume": 0.25,
  "ollama_url": "http://localhost:11434/api/generate",
  "llm_model": "qwen3:14b",
  "auto_execute": false,
  "terminal_auto_command": false
}
```

- **Safety:** known desktop actions (workspaces, volume, media, app launches, URLs, lock, screenshots; allowlist in `daemon/llm_command.py`) run instantly, chains included. Any other command is typed into the terminal if one is focused, otherwise it waits for you to click **Run** on a notification. Test the allowlist with `python3 daemon/test_llm_command.py`.
- `"auto_execute": true` — Automatically hits <kbd>Enter</kbd> on terminal commands instead of just typing them.
- `"sound_volume": 0.15` — Lower audio cue volume (or `false` to disable sound).
- `"terminal_auto_command": true` — Always convert dictation to commands whenever a terminal is focused.

---

## 🔧 Service Management

```bash
# Check daemon status
systemctl --user status whisper-ptt.service

# View live transcription logs & timing
journalctl --user -u whisper-ptt.service -f

# Restart daemon
systemctl --user restart whisper-ptt.service
```
