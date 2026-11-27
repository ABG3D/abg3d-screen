# abg3d-screen

Lightweight, low-RAM Klipper touchscreen UI for Raspberry Pi and BTT single-board computers.
Python 3 + GTK 3 (PyGObject) + Cairo, talking to Moonraker (`127.0.0.1:7125`) with Mainsail
database integration (temperature presets, cooldown G-code, macro visibility).

## Supported hardware

| Boards | Displays |
| --- | --- |
| Raspberry Pi 3B / 4B | 4.3" 480x272 or 800x480 |
| BTT CB1, BTT CB2 | 5" 800x480 |
| BTT Pi 1, BTT Pi 2 | 7" 800x480 or 1024x600 |

The active resolution and DPI are read from `Gdk.Monitor` at startup. Fonts, padding, icons and
grid density scale from that, with touch targets of at least 48 px on 5"/7" panels and 40 px on
4.3" panels. If your panel reports a wrong physical size, set `diagonal` in the config.

## Required packages

`install.sh` installs these automatically with `apt`:

```
python3 python3-venv python3-gi python3-gi-cairo gir1.2-gtk-3.0 gir1.2-gdkpixbuf-2.0
xinit xserver-xorg-core xserver-xorg-legacy xserver-xorg-input-libinput
xserver-xorg-video-fbdev x11-xserver-utils librsvg2-common fonts-dejavu-core
```

It also creates a venv at `/opt/abg3d-screen/venv` (with system site-packages for PyGObject)
and installs `websockets` from `requirements.txt`. If pip has no network access, abg3d-screen
uses its built-in WebSocket client instead. Wi-Fi control uses `nmcli` when NetworkManager is
present; it is not installed by the script.

## Install

```bash
cd ~
git clone https://github.com/ABG3D/abg3d-screen.git
cd abg3d-screen
./install.sh
```

Run it as the printer user (for example `pi` or `biqu`), not as root. The installer:

1. Checks for a supported board (`--force` skips this check).
2. Installs the apt packages listed above.
3. **Locks display precedence.** It detects `KlipperScreen`, `klipperscreen`, `helixscreen` and
   `HelixScreen` as system units (`systemctl`) and user units (`systemctl --user`). It also checks
   the active display manager (for example LightDM) and the X11 hooks in `~/.xinitrc`,
   `~/.xsession`, `/etc/rc.local`, LightDM configs and XDG autostart entries. Everything it finds
   is recorded in `/var/lib/abg3d-screen/state.txt` (original files are backed up next to it).
   Each unit is then stopped, disabled and **masked**, and each hook is commented out, so no
   reboot, power cycle, display manager or Moonraker service restart can launch them again.
4. Copies the app to `/opt/abg3d-screen` and builds the venv.
5. Configures the Xorg wrapper, backlight udev rule, NetworkManager polkit rule and user groups.
6. Creates `~/printer_data/config/abg3d-screen.conf` (editable from Mainsail) and adds the
   service to `moonraker.asvc`.
7. Installs `abg3d-screen.service` with
   `Conflicts=KlipperScreen.service klipperscreen.service helixscreen.service HelixScreen.service`,
   `After=systemd-user-sessions.service moonraker.service` and `WantedBy=multi-user.target`. X runs
   on the dedicated `vt7`, which avoids getty on `vt1` and LightDM collisions on the BTT CB2. The
   installer then runs `systemctl daemon-reload && systemctl enable --now abg3d-screen.service`.
   On 1 GB boards, systemd memory limits are `MemoryHigh=200M` and `MemoryMax=256M`.

To update, run `git pull && ./install.sh` in your clone. Saved state and your config are kept.

## Service management

```bash
sudo systemctl status abg3d-screen
sudo systemctl restart abg3d-screen
sudo systemctl stop abg3d-screen
sudo systemctl disable abg3d-screen
journalctl -u abg3d-screen -f
```

You can also restart the service from Mainsail's service menu. The service restarts after a
crash. Quitting from the UI (Settings › System › Allow to quit) leaves it stopped until the next
boot or manual start.

## Configuration

`~/printer_data/config/abg3d-screen.conf`:

| Key | Default | Meaning |
| --- | --- | --- |
| `host` / `port` | `127.0.0.1` / `7125` | Moonraker address |
| `api_key` | empty | Only if Moonraker does not trust localhost |
| `fullscreen` | `true` | Kiosk mode on the active monitor |
| `width` / `height` | `800` / `480` | Window size when `fullscreen = false` |
| `diagonal` | `0` | Panel size in inches; `0` detects it automatically |
| `font_size` | `0` | Base font in px; `0` scales automatically |
| `log_level` | `INFO` | Python logging level |

UI preferences (theme, screen timeout, pointer, pin configs, MMU tab, macro visibility) are
stored in `~/.config/abg3d-screen/settings.json`.

## MMU support

The MMU tab is always available in the navigation, even when Moonraker or the MCU is offline.
Enable MMU support in Settings › MMU. When an MMU is detected through Moonraker, the tab hosts
its native panel:

- **BoxTurtle AFC** is detected from the `AFC` / `AFC_stepper` objects. The native panel is
  loaded from `~/AFC-Klipper-Screen-Add-On/AFC.py`.
- **Happy Hare** is detected from the `mmu` object. The native panel is loaded from
  `~/KlipperScreen/happy_hare`.

The native panels run through a built-in KlipperScreen-compatible GTK shim. If the add-on is
missing or fails to load, a built-in lane/gate view is used instead.

## Offline / standby behaviour

Every navigation tab, sub-tab and control stays enabled whatever the Moonraker, MCU or
`printer.cfg` state. Commands that cannot be delivered report the reason in a toast. System
service and host power actions use Moonraker's REST endpoints (`/printer/restart`,
`/printer/firmware_restart`, `/machine/services/restart?service=...`, `/machine/reboot`,
`/machine/shutdown`), so they work while Klipper has no MCU.

## Pin configs

Settings › System › Pin Configs enables two controls:

- `BedFans` presets (0/20/50/80/100 %) in Control › Fans, which send
  `SET_FAN_SPEED FAN=BedFans SPEED=<val>`.
- The `caselight` toggle in Control › LEDs, which sends `SET_PIN PIN=caselight VALUE=1.00|0.00`.

These require `[fan_generic BedFans]` and `[output_pin caselight]` in your Klipper config.

## Uninstall / revert

```bash
/opt/abg3d-screen/uninstall.sh          # or ./uninstall.sh from your clone
/opt/abg3d-screen/uninstall.sh --purge
```

| Command | What it does |
| --- | --- |
| `uninstall.sh` | Stops, disables and removes `abg3d-screen.service` and `/opt/abg3d-screen`. KlipperScreen / HelixScreen **stay masked** and `/var/lib/abg3d-screen/state.txt` is kept, so they do **not** retake the display. |
| `uninstall.sh --purge` | Additionally deletes `~/.config/abg3d-screen` and `abg3d-screen.conf`. It reads `state.txt`, puts back the original unit files and X11/autostart hooks, and runs `systemctl unmask`, `enable` and `start` on the previous touchscreen service. It then removes `/var/lib/abg3d-screen`. |

Only `--purge` hands the display back to KlipperScreen or HelixScreen.
