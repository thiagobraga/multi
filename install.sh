#!/usr/bin/env sh
# Symlink multi into ~/.local/bin and check runtime dependencies.
set -eu

here=$(cd "$(dirname "$0")" && pwd)
mkdir -p "$HOME/.local/bin"
chmod +x "$here/multi"
ln -sf "$here/multi" "$HOME/.local/bin/multi"

for cmd in python3 google-chrome xdotool xrandr xprop; do
    command -v "$cmd" >/dev/null 2>&1 || echo "missing: $cmd (sudo apt install xdotool x11-xserver-utils x11-utils python3)"
done

case ":$PATH:" in
    *":$HOME/.local/bin:"*) ;;
    *) echo "add ~/.local/bin to your PATH" ;;
esac
echo "installed: $HOME/.local/bin/multi"
