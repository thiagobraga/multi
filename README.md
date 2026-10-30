# multi

Open N isolated Chrome windows of the same site, tiled on screen. Use it to run several accounts of one site side by side (Instagram, Oracle Cloud, AWS...).

Each window is its own Chrome instance with its own profile directory, so cookies, localStorage and logins are fully separate and persist between runs.

## Install

Requires Linux with GNOME, Google Chrome, Python 3, `xdotool`, `xrandr` and `xprop`.

```sh
sudo apt install xdotool x11-xserver-utils x11-utils
./install.sh
```

This symlinks `multi` to `~/.local/bin/multi`.

## Usage

```sh
multi instagram              # https://instagram.com, 2 windows side by side
multi oracle -x3             # 3 columns
multi aws.amazon.com -x4     # 4 columns
multi instagram -x6          # 5 or more: cascade
multi cloud.oracle.com       # a name with a dot is used as the domain
multi https://example.com/a  # full URLs are used as given
```

| Flag | Meaning |
|------|---------|
| `-x N` | window count (default 2). 1-4 are columns, 5+ cascade |
| `-d`, `--default` | first window uses your default Chrome profile (extensions, logins) |
| `--bitwarden` | also open the Bitwarden web vault in a small window on the right, using your default profile |
| `-c`, `-w`, `--close` | close windows opened by `multi`; add a target to close only that site |
| `-v`, `--version` | print version |

```sh
multi -c               # close everything multi opened
multi instagram -w     # close only instagram windows
```

## Tests

```sh
python3 -m unittest discover -s tests
```

Chrome, xdotool and the screen are mocked, so tests run anywhere with Python 3.

## How it works

- Profiles live in `~/.local/share/multi/<site>/<n>`. Delete a folder to forget that account.
- Chrome runs through XWayland (`--ozone-platform=x11`) because Wayland ignores window position requests. Windows are tiled on the primary monitor, below the GNOME top bar.
- `--close` sends SIGTERM to Chrome instances started with a `multi` profile path, so a normal Chrome session is never touched.

## Limits

- **Default profile placement**: `-d` and `--bitwarden` join your already running Chrome. If that Chrome runs on Wayland, the windows open but cannot be positioned (tile them with Super+Left/Right). Quit Chrome and start it once with `--ozone-platform=x11` to fix this.
- **Default profile close**: `--close` does not close default profile windows.
- **Extensions**: isolated profiles start with no extensions.
- **Minimum width**: Chrome windows are at least about 544px wide, so 3 columns plus `--bitwarden` overlap slightly.
- **Rerun**: opening a slot that is already open adds a window to the old instance and does not re-tile.
