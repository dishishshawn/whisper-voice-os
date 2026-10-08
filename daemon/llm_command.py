#!/usr/bin/env python3
import json
import os
import re
import shlex
import subprocess
import sys
import urllib.request

CONFIG_PATH = os.path.expanduser("~/.config/whisper-ptt/config.json")


def get_config():
    defaults = {
        "ollama_url": "http://localhost:11434/api/generate",
        "llm_model": "qwen3:14b",
        "auto_execute": False,
        "terminal_auto_command": False,
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
    if (
        win_class.lower() in ("kitty", "terminal", "foot", "alacritty", "wezterm")
        and win_title
    ):
        cwd = win_title
    else:
        # Outside terminals the title is untrusted (e.g. a web page title), keep it out of the prompt
        win_title = ""

    system_prompt = f"""You are the AI brain of a voice-controlled Linux operating system (Ubuntu 26.04 with Hyprland).
Current working directory: {cwd}
Active window: {win_class} ({win_title})

Available desktop controls:
- Window & Workspace: `hyprctl dispatch workspace <N>`, `hyprctl dispatch movetoworkspace <N>`, `hyprctl dispatch killactive`, `hyprctl dispatch fullscreen`, `hyprctl dispatch togglefloating`, `hyprctl dispatch focuswindow <query>`
- Media controls: `playerctl play-pause`, `playerctl next`, `playerctl previous`
- Audio volume: `wpctl set-volume @DEFAULT_AUDIO_SINK@ <N>%`, `wpctl set-volume @DEFAULT_AUDIO_SINK@ 5%+`, `wpctl set-volume @DEFAULT_AUDIO_SINK@ 5%-`, `wpctl set-mute @DEFAULT_AUDIO_SINK@ toggle`
- System tools: `hyprlock`, `~/.config/hypr/scripts/screenshot.sh area`, `~/.config/hypr/scripts/screenshot.sh output`
- Desktop apps: `google-chrome --new-window <url> &`, `zen &`, `obsidian &`, `discord &`, `zed &`, `kitty &`, `nautilus &`, `xdg-open <url> &`
- Multiple sequential desktop actions (e.g. switch workspace then open app): wrap in subshell or sequence with sleep, e.g. `(hyprctl dispatch workspace 5; sleep 0.2; google-chrome --new-window https://www.youtube.com) &`
- Workspaces: Workspaces 1-10 are numbers (e.g. `hyprctl dispatch workspace 3`). For non-numeric names, use `hyprctl dispatch workspace name:<name>`.
- Syntax rule: Never output `&;` or `;&`. In a subshell `(...) &`, separate sequential commands with `;` and do not put `&` inside the parentheses.
- Package managers: flatpak (preferred for apps: `flatpak install --user -y flathub <id>`), apt (system).
- Standard bash CLI commands.

Task: Convert the user voice intent into the single exact command to execute.
Rules:
1. Output ONLY the raw executable command.
2. NO markdown code blocks, NO quotes around the whole line, NO explanations.
3. If the command requires root/system privileges, include sudo.
4. Keep the command concise and production-ready."""

    prompt = f"<|im_start|>system\n{system_prompt}<|im_end|>\n<|im_start|>user\n{nl_text}<|im_end|>\n<|im_start|>assistant\n<think>\n</think>\n"

    payload = json.dumps(
        {
            "model": config.get("llm_model", "qwen3:14b"),
            "prompt": prompt,
            "raw": True,
            "stream": False,
            "options": {"temperature": 0.1, "num_predict": 80},
        }
    ).encode("utf-8")

    try:
        url = config.get("ollama_url", "http://localhost:11434/api/generate")
        req = urllib.request.Request(
            url, data=payload, headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            res = json.loads(resp.read().decode("utf-8"))
            cmd = res.get("response", "").strip()

            cmd = re.sub(r"^```[a-zA-Z]*\n?", "", cmd)
            cmd = re.sub(r"\n?```$", "", cmd).strip()

            if cmd.startswith("$ ") or cmd.startswith("# "):
                cmd = cmd[2:].strip()

            # Prevent fatal bash syntax errors like `&;` or `;&`
            cmd = re.sub(r"&\s*;", ";", cmd)
            cmd = re.sub(r";\s*&", ";", cmd)

            if "flatpak install" in cmd and "io.obsidian.Obsidian" in cmd:
                cmd = cmd.replace("io.obsidian.Obsidian", "md.obsidian.Obsidian")
            if "flatpak run com.discord.Discord" in cmd:
                cmd = cmd.replace("com.discord.Discord", "com.discordapp.Discord")

            return cmd
    except Exception as e:
        print(f"LLM conversion error: {e}", file=sys.stderr)
        return ""


HYPR_DISPATCHERS = {
    "workspace",
    "movetoworkspace",
    "movetoworkspacesilent",
    "killactive",
    "fullscreen",
    "togglefloating",
    "focuswindow",
}
# Launchers that may take positional args (URLs, paths) and safe UI flags:
# Chrome's --renderer-cmd-prefix / --gpu-launcher run arbitrary programs, but --new-window / --incognito are safe.
APP_LAUNCHERS = {"google-chrome", "zen", "obsidian", "discord", "zed", "nautilus"}
SAFE_FLAGS = {"--new-window", "--incognito", "-n"}


def is_allowed_step(argv):
    name, args = argv[0], argv[1:]
    if name == "hyprctl":
        return len(args) >= 2 and args[0] == "dispatch" and args[1] in HYPR_DISPATCHERS
    if name == "wpctl":
        return bool(args) and args[0] in ("set-volume", "set-mute")
    if name == "playerctl":
        return True
    if name == "sleep":
        return len(args) == 1 and re.fullmatch(r"[0-9.]+", args[0]) is not None
    if name in ("hyprlock", "kitty"):  # kitty's positional args are a program to run
        return not args
    if name == "~/.config/hypr/scripts/screenshot.sh":
        return args in (["area"], ["output"])
    if name == "xdg-open":
        return len(args) == 1 and re.match(r"https?://", args[0]) is not None
    if name == "flatpak":
        return len(args) == 2 and args[0] == "run" and not args[1].startswith("-")
    if name in APP_LAUNCHERS:
        return all(not a.startswith("-") or a in SAFE_FLAGS for a in args)
    return False


def is_allowed_action(cmd):
    """True if cmd is only known desktop actions, safe to run without asking.

    Accepts the chained form the prompt asks for, e.g.
    `(hyprctl dispatch workspace 5; sleep 0.2; google-chrome https://youtube.com) &`.
    """
    # substitution, pipes, redirects, escapes, brace expansion (`{--flag,x}` becomes a flag)
    if re.search(r"[`$|<>\n\\{}]", cmd):
        return False
    s = cmd.strip().removesuffix("&").strip()
    if s.startswith("(") and s.endswith(")"):
        s = s[1:-1]
    steps = [p.strip() for p in re.split(r"&&|[;&]", s)]
    try:
        argvs = [shlex.split(p) for p in steps]
    except ValueError:
        return False
    # A word starting with a glob char can expand to a filename starting with "-"
    if any(t.startswith(("*", "?", "[")) for a in argvs for t in a):
        return False
    return all(argvs) and all(is_allowed_step(a) for a in argvs)


def confirm(cmd, timeout_ms=15000):
    """Show a notification with a Run button; True if it was clicked.

    notify-send -A reports "actions not supported" against swaync 0.12, so use libnotify directly.
    """
    import gi

    gi.require_version("Notify", "0.7")
    from gi.repository import GLib, Notify

    Notify.init("Voice OS")
    loop = GLib.MainLoop()
    clicked = []
    n = Notify.Notification.new("Run this command?", GLib.markup_escape_text(cmd))
    n.set_hint("x-canonical-private-synchronous", GLib.Variant("s", "whisper-ptt"))
    n.set_timeout(timeout_ms)
    n.add_action("run", "Run", lambda *_: (clicked.append(True), loop.quit()))
    n.connect("closed", lambda *_: loop.quit())
    n.show()
    GLib.timeout_add(timeout_ms + 1000, loop.quit)
    loop.run()
    return bool(clicked)


def main():
    if len(sys.argv) < 2:
        print(
            "Usage: llm_command.py <natural language prompt> | --check|--confirm <command>",
            file=sys.stderr,
        )
        sys.exit(1)

    if sys.argv[1] == "--check":
        sys.exit(0 if len(sys.argv) == 3 and is_allowed_action(sys.argv[2]) else 1)
    if sys.argv[1] == "--confirm":
        sys.exit(0 if len(sys.argv) == 3 and confirm(sys.argv[2]) else 1)

    prompt = " ".join(sys.argv[1:])
    cmd = convert_nl_to_command(prompt)
    if cmd:
        print(cmd)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
