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
    """Returns (win_class, win_title, win_pid)."""
    try:
        out = subprocess.check_output(
            ["hyprctl", "activewindow", "-j"], text=True, timeout=0.3
        )
        data = json.loads(out)
        return data.get("class", ""), data.get("title", ""), data.get("pid")
    except Exception:
        return "", "", None


def get_terminal_cwd(parent_pid):
    """Resolves real shell CWD under the focused terminal process via /proc."""
    if not parent_pid:
        return os.path.expanduser("~")
    try:
        # Check child processes (e.g., kitty -> bash / zsh / bun)
        pids = (
            subprocess.check_output(
                ["pgrep", "-P", str(parent_pid)], text=True, timeout=0.2
            )
            .strip()
            .split()
        )
        target_pid = pids[-1] if pids else str(parent_pid)
        try:
            sub = (
                subprocess.check_output(
                    ["pgrep", "-P", target_pid], text=True, timeout=0.1
                )
                .strip()
                .split()
            )
            if sub:
                target_pid = sub[-1]
        except Exception:
            pass
        return os.readlink(f"/proc/{target_pid}/cwd")
    except Exception:
        return os.path.expanduser("~")


def detect_dev_context(cwd):
    """Detects Git status, container tooling, cloud runtimes, and task runners (<25ms)."""
    context_lines = []

    # Git repository & branch
    git_dir = os.path.join(cwd, ".git")
    if os.path.isdir(git_dir) or os.path.isfile(git_dir):
        try:
            branch = subprocess.check_output(
                ["git", "-C", cwd, "branch", "--show-current"],
                text=True,
                timeout=0.2,
            ).strip()
            status = subprocess.check_output(
                ["git", "-C", cwd, "status", "--porcelain"],
                text=True,
                timeout=0.2,
            ).strip()
            mod_count = len(status.splitlines()) if status else 0
            context_lines.append(
                f"Git repo: branch '{branch}', {mod_count} modified/untracked files"
            )
        except Exception:
            pass

    # Containers & Cloud
    has_compose = os.path.isfile(
        os.path.join(cwd, "docker-compose.yml")
    ) or os.path.isfile(os.path.join(cwd, "compose.yaml"))
    has_dockerfile = os.path.isfile(os.path.join(cwd, "Dockerfile"))
    if has_compose:
        context_lines.append("Docker Compose project")
    elif has_dockerfile:
        context_lines.append("Docker container project (Dockerfile present)")

    # Supabase BaaS
    if os.path.isdir(os.path.join(cwd, "supabase")) or os.path.isfile(
        os.path.join(cwd, "supabase", "config.toml")
    ):
        context_lines.append(
            "Supabase project (local BaaS dev available via `supabase`)"
        )

    # Kubernetes manifests
    if os.path.isdir(os.path.join(cwd, "k8s")) or any(
        f.endswith((".k8s.yaml", ".k8s.yml"))
        for f in os.listdir(cwd)
        if os.path.isfile(os.path.join(cwd, f))
    ):
        context_lines.append("Kubernetes manifests present")

    # Terraform
    if any(
        f.endswith(".tf")
        for f in os.listdir(cwd)
        if os.path.isfile(os.path.join(cwd, f))
    ):
        context_lines.append("Terraform infrastructure present")

    # Runtimes & package managers
    has_bun = os.path.isfile(os.path.join(cwd, "bun.lockb")) or os.path.isfile(
        os.path.join(cwd, "bun.lock")
    )
    has_pkg = os.path.isfile(os.path.join(cwd, "package.json"))
    if has_pkg:
        try:
            with open(os.path.join(cwd, "package.json"), "r") as f:
                pkg_data = json.load(f)
                pname = pkg_data.get("name", "app")
                scripts = list(pkg_data.get("scripts", {}).keys())[:5]
                runtime_pref = "bun" if has_bun else "npm/node"
                context_lines.append(
                    f"JS/TS project '{pname}' ({runtime_pref}, scripts: {scripts})"
                )
        except Exception:
            pass
    elif has_bun:
        context_lines.append("Bun runtime project")

    # Justfile task runner
    if os.path.isfile(os.path.join(cwd, "Justfile")) or os.path.isfile(
        os.path.join(cwd, "justfile")
    ):
        try:
            recipes = subprocess.check_output(
                ["just", "--summary"], cwd=cwd, text=True, timeout=0.2
            ).strip()
            context_lines.append(f"Justfile recipes: {recipes}")
        except Exception:
            pass

    # Rust / Cargo
    if os.path.isfile(os.path.join(cwd, "Cargo.toml")):
        context_lines.append("Rust Cargo project")

    # Python
    if os.path.isfile(os.path.join(cwd, "pyproject.toml")) or os.path.isfile(
        os.path.join(cwd, "requirements.txt")
    ):
        context_lines.append("Python project")

    return "; ".join(context_lines) if context_lines else "Standard directory"


def get_clipboard_snippet(nl_text):
    """If user asks to fix/debug/inspect or references clipboard, extract recent text."""
    trigger_words = {
        "error",
        "bug",
        "trace",
        "fix",
        "debug",
        "this",
        "here",
        "why",
        "fail",
        "failed",
        "failing",
        "curl",
        "test",
        "issue",
        "paste",
        "log",
        "logs",
        "stack",
        "exception",
        "what",
    }
    words = set(re.findall(r"\b\w+\b", nl_text.lower()))
    if not (words & trigger_words):
        return ""
    try:
        clip = subprocess.check_output(
            ["wl-paste", "-t", "text"], text=True, timeout=0.15
        ).strip()
        if clip:
            first_lines = clip.splitlines()[:15]
            snippet = "\n".join(first_lines)[:400].strip()
            return snippet
    except Exception:
        pass
    return ""


def convert_nl_to_command(nl_text, config=None):
    if config is None:
        config = get_config()

    win_class, win_title, win_pid = get_active_window_info()
    is_terminal = win_class.lower() in (
        "kitty",
        "terminal",
        "foot",
        "alacritty",
        "wezterm",
        "ghostty",
    )

    if is_terminal and win_pid:
        cwd = get_terminal_cwd(win_pid)
    else:
        cwd = os.path.expanduser("~")
        win_title = ""  # Outside terminals keep title untrusted

    dev_context = detect_dev_context(cwd)
    clipboard_snippet = get_clipboard_snippet(nl_text)
    clipboard_section = (
        f"\nClipboard content:\n```\n{clipboard_snippet}\n```"
        if clipboard_snippet
        else ""
    )

    system_prompt = f"""You are the AI brain of a voice-controlled Linux operating system (Ubuntu 26.04 with Hyprland).
The user is a Cloud Engineer & DevOps Developer.
Current working directory: {cwd}
Project dev context: {dev_context}
Active window: {win_class} {('(' + win_title + ')') if win_title else ''}{clipboard_section}

Desktop controls:
- Window & Workspace: `hyprctl dispatch workspace <N>`, `hyprctl dispatch movetoworkspace <N>`, `hyprctl dispatch killactive`, `hyprctl dispatch fullscreen`, `hyprctl dispatch togglefloating`, `hyprctl dispatch focuswindow <query>`
- Media controls: `playerctl play-pause`, `playerctl next`, `playerctl previous`
- Audio volume: `wpctl set-volume @DEFAULT_AUDIO_SINK@ <N>%`, `wpctl set-volume @DEFAULT_AUDIO_SINK@ 5%+`, `wpctl set-volume @DEFAULT_AUDIO_SINK@ 5%-`, `wpctl set-mute @DEFAULT_AUDIO_SINK@ toggle`
- Brightness: `brightnessctl set 5%+`, `brightnessctl set 5%-`
- System tools: `hyprlock`, `~/.config/hypr/scripts/screenshot.sh area`, `~/.config/hypr/scripts/screenshot.sh output`
- Desktop apps: `google-chrome --new-window <url> &`, `zen &`, `obsidian &`, `discord &`, `zed &`, `kitty &`, `nautilus &`, `xdg-open <url> &`, `pavucontrol &`

Cloud Code, Containers & DevOps expertise:
- Docker: `docker compose up -d`, `docker compose down`, `docker compose logs -f <service>`, `docker compose restart <service>`, `docker ps`, `docker system prune` (use `sudo docker` if root needed).
- Supabase: `supabase start`, `supabase stop`, `supabase status`, `supabase db diff`, `supabase db push`, `supabase migration up`, `supabase functions serve`.
- Bun / Node: If Bun is detected in dev context, use `bun run dev`, `bun test`, `bun add <pkg>`. Otherwise use `npm run <script>`, `npm install <pkg>`.
- Justfile: `just <recipe>`.
- Git: `git status`, `git diff`, `git add -A && git commit -m "<msg>"`, `git push`, `git pull`, `git checkout -b <branch>`, `git stash`, `git stash pop`.
- Ports & Processes: `fuser -k <port>/tcp` or `kill -9 $(lsof -t -i:<port>)` to kill ports. `lsof -i :<port>` to inspect.
- Hardware & Stats: `nvidia-smi` for GPU, `free -h` for memory, `df -h /` for disk.

Workflow Rules:
- Compound desktop workflows (e.g. switch workspace then open app): wrap in subshell or sequence with `&&` or `;`, e.g. `(hyprctl dispatch workspace 5; sleep 0.2; google-chrome --new-window https://www.youtube.com) &`
- Diagnostics outside terminal: use `notify-send "<Title>" "$(<command>)"` to display quick status.
- Workspaces: Workspaces 1-10 are numbers (e.g. `hyprctl dispatch workspace 3`). For non-numeric names, use `hyprctl dispatch workspace name:<name>`.
- Syntax rule: Never output `&;` or `;&`. In a subshell `(...) &`, separate sequential commands with `;` and do not put `&` inside the parentheses.
- Package managers: flatpak (preferred for apps: `flatpak install --user -y flathub <id>`), apt (system).

Task: Convert the user voice intent into the single exact command to execute.
Rules:
1. Output ONLY the raw executable command.
2. NO markdown code blocks, NO quotes around the whole line, NO explanations.
3. If the command requires root/system privileges, include sudo.
4. Keep the command concise, robust, and production-ready."""

    prompt = f"<|im_start|>system\n{system_prompt}<|im_end|>\n<|im_start|>user\n{nl_text}<|im_end|>\n<|im_start|>assistant\n<think>\n</think>\n"

    payload = json.dumps(
        {
            "model": config.get("llm_model", "qwen3:14b"),
            "prompt": prompt,
            "raw": True,
            "stream": False,
            "keep_alive": -1,
            "options": {"temperature": 0.1, "num_predict": 100},
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
APP_LAUNCHERS = {
    "google-chrome",
    "zen",
    "obsidian",
    "discord",
    "zed",
    "nautilus",
    "pavucontrol",
    "nm-connection-editor",
    "blueman-manager",
}
SAFE_FLAGS = {"--new-window", "--incognito", "-n"}


def is_allowed_step(argv):
    name, args = argv[0], argv[1:]
    if name == "hyprctl":
        return (
            len(args) >= 2
            and args[0] == "dispatch"
            and args[1] in HYPR_DISPATCHERS
        )
    if name == "wpctl":
        return bool(args) and args[0] in ("set-volume", "set-mute")
    if name == "playerctl":
        return True
    if name == "sleep":
        return len(args) == 1 and re.fullmatch(r"[0-9.]+", args[0]) is not None
    if name == "brightnessctl":
        return (
            len(args) == 2
            and args[0] == "set"
            and re.fullmatch(r"[0-9]+%[+-]?", args[1]) is not None
        )
    if name == "notify-send":
        return not any(
            a.startswith("-") and a not in ("-t", "-u", "-a", "-i")
            for a in args
        )
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
