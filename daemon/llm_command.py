#!/usr/bin/env python3
import json
import os
import re
import subprocess
import sys
import urllib.request

CONFIG_PATH = os.path.expanduser("~/.config/whisper-ptt/config.json")

def get_config():
    defaults = {
        "ollama_url": "http://localhost:11434/api/generate",
        "llm_model": "qwen3:14b",
        "auto_execute": False,
        "terminal_auto_command": False
    }
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r") as f:
                defaults.update(json.load(f))
        except Exception:
            pass
    return defaults

def get_active_window_info():
    try:
        out = subprocess.check_output(["hyprctl", "activewindow", "-j"], text=True)
        data = json.loads(out)
        return data.get("class", ""), data.get("title", "")
    except Exception:
        return "", ""

def convert_nl_to_command(nl_text, config=None):
    if config is None:
        config = get_config()

    win_class, win_title = get_active_window_info()
    cwd = "~"
    if win_class.lower() in ("kitty", "terminal", "foot", "alacritty", "wezterm") and win_title:
        cwd = win_title

    system_prompt = f"""You are the AI brain of a voice-controlled Linux operating system (Ubuntu 26.04 with Hyprland).
Current working directory: {cwd}
Active window: {win_class} ({win_title})

Available desktop controls:
- Window & Workspace: `hyprctl dispatch workspace <N>`, `hyprctl dispatch movetoworkspace <N>`, `hyprctl dispatch killactive`, `hyprctl dispatch fullscreen`, `hyprctl dispatch togglefloating`, `hyprctl dispatch focuswindow <query>`
- Media controls: `playerctl play-pause`, `playerctl next`, `playerctl previous`
- Audio volume: `wpctl set-volume @DEFAULT_AUDIO_SINK@ <N>%`, `wpctl set-volume @DEFAULT_AUDIO_SINK@ 5%+`, `wpctl set-volume @DEFAULT_AUDIO_SINK@ 5%-`, `wpctl set-mute @DEFAULT_AUDIO_SINK@ toggle`
- System tools: `hyprlock`, `~/.config/hypr/scripts/screenshot.sh area`, `~/.config/hypr/scripts/screenshot.sh output`
- Desktop apps: `google-chrome <url> &`, `zen &`, `obsidian &`, `discord &`, `zed &`, `kitty &`, `nautilus &`, `xdg-open <url> &`
- Multiple sequential desktop actions (e.g. switch workspace then open app): wrap in subshell or sequence with sleep, e.g. `(hyprctl dispatch workspace 5; sleep 0.2; google-chrome https://www.youtube.com) &`
- Package managers: flatpak (preferred for apps: `flatpak install --user -y flathub <id>`), apt (system).
- Standard bash CLI commands.

Task: Convert the user voice intent into the single exact command to execute.
Rules:
1. Output ONLY the raw executable command.
2. NO markdown code blocks, NO quotes around the whole line, NO explanations.
3. If the command requires root/system privileges, include sudo.
4. Keep the command concise and production-ready."""

    prompt = f"<|im_start|>system\n{system_prompt}<|im_end|>\n<|im_start|>user\n{nl_text}<|im_end|>\n<|im_start|>assistant\n<think>\n</think>\n"

    payload = json.dumps({
        "model": config.get("llm_model", "qwen3:14b"),
        "prompt": prompt,
        "raw": True,
        "stream": False,
        "options": {
            "temperature": 0.1,
            "num_predict": 80
        }
    }).encode("utf-8")

    try:
        url = config.get("ollama_url", "http://localhost:11434/api/generate")
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            res = json.loads(resp.read().decode("utf-8"))
            cmd = res.get("response", "").strip()

            cmd = re.sub(r"^```[a-zA-Z]*\n?", "", cmd)
            cmd = re.sub(r"\n?```$", "", cmd).strip()

            if cmd.startswith("$ ") or cmd.startswith("# "):
                cmd = cmd[2:].strip()

            if "flatpak install" in cmd and "io.obsidian.Obsidian" in cmd:
                cmd = cmd.replace("io.obsidian.Obsidian", "md.obsidian.Obsidian")
            if "flatpak run com.discord.Discord" in cmd:
                cmd = cmd.replace("com.discord.Discord", "com.discordapp.Discord")

            return cmd
    except Exception as e:
        print(f"LLM conversion error: {e}", file=sys.stderr)
        return ""

def is_system_action(cmd):
    """Detect if command is an OS action that should be executed directly rather than typed into a terminal line."""
    patterns = [
        r"^hyprctl\s+",
        r"^wpctl\s+",
        r"^playerctl\s+",
        r"^hyprlock$",
        r"^\~/\.config/hypr/",
        r"^flatpak\s+run\s+",
        r"^(zed|kitty|nautilus|fuzzel)\s*",
        r"^xdg-open\s+",
        r"&\s*$"
    ]
    for p in patterns:
        if re.search(p, cmd):
            return True
    return False

def main():
    if len(sys.argv) < 2:
        print("Usage: llm_command.py <natural language prompt>", file=sys.stderr)
        sys.exit(1)

    prompt = " ".join(sys.argv[1:])
    cmd = convert_nl_to_command(prompt)
    if cmd:
        print(cmd)
    else:
        sys.exit(1)

if __name__ == "__main__":
    main()
