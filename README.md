# ABG3D - Klipper Screen Interface

Lightweight, low-RAM Klipper touchscreen UI for Raspberry Pi and BTT single-board computers.
Python 3 + GTK 3 (PyGObject) + Cairo, talking to Moonraker (`127.0.0.1:7125`) with Mainsail
database integration (temperature presets, cooldown G-code, macro visibility).

## Supported hardware

Any listed board works with any listed display.

**Supported Boards**

- Raspberry Pi 3B
- Raspberry Pi 4B
- BigTreeTech CB1
- BigTreeTech CB2
- BigTreeTech Pi 1
- BigTreeTech Pi 2

**Supported Displays**

- 4.3" (480x272 / 800x480)
- 5" (800x480)
- 7" (800x480 / 1024x600)

The active resolution and DPI are read from `Gdk.Monitor` at startup. Fonts, padding, icons and
grid density scale from that, with touch targets of at least 48 px on 5"/7" panels and 40 px on
4.3" panels. If your panel reports a wrong physical size, set `diagonal` in the config.

## Screenshots

These were rendered headless (Xvfb) from the real GTK 3 UI against Moonraker mock data. They show
the responsive scaling and the honeycomb backdrop at each supported size. A 4.3" 800x480 panel and
a 7" 800x480 panel use the same layout as the 5" screenshots; text and touch targets are scaled
from the detected DPI.

### 4.3" — 480x272

Compact profile: icon-only bottom navigation and 40 px minimum touch targets.

![4.3" — 480x272 home](images/4_3in_480x272_home.png)

| | |
| --- | --- |
| **Control › Movement**<br>![4.3" — 480x272 Control › Movement](images/4_3in_480x272_control_move.png) | **Control › Temperature**<br>![4.3" — 480x272 Control › Temperature](images/4_3in_480x272_control_temp.png) |
| **Files**<br>![4.3" — 480x272 Files](images/4_3in_480x272_files.png) | **Console**<br>![4.3" — 480x272 Console](images/4_3in_480x272_console.png) |
| **MMU (BoxTurtle AFC)**<br>![4.3" — 480x272 MMU (BoxTurtle AFC)](images/4_3in_480x272_mmu.png) | **System**<br>![4.3" — 480x272 System](images/4_3in_480x272_system.png) |
| **Settings**<br>![4.3" — 480x272 Settings](images/4_3in_480x272_settings.png) | **Keypad**<br>![4.3" — 480x272 Keypad](images/4_3in_480x272_keypad.png) |
| **Standby (Moonraker / MCU offline)**<br>![4.3" — 480x272 Standby (Moonraker / MCU offline)](images/4_3in_480x272_standby.png) | |

### 5" — 800x480

Side navigation rail with 48 px touch targets, tuned to fit 480 px of height exactly.

![5" — 800x480 home](images/5in_800x480_home.png)

| | |
| --- | --- |
| **Control › Movement**<br>![5" — 800x480 Control › Movement](images/5in_800x480_control_move.png) | **Control › Temperature**<br>![5" — 800x480 Control › Temperature](images/5in_800x480_control_temp.png) |
| **Files**<br>![5" — 800x480 Files](images/5in_800x480_files.png) | **Console**<br>![5" — 800x480 Console](images/5in_800x480_console.png) |
| **MMU (BoxTurtle AFC)**<br>![5" — 800x480 MMU (BoxTurtle AFC)](images/5in_800x480_mmu.png) | **System**<br>![5" — 800x480 System](images/5in_800x480_system.png) |
| **Settings**<br>![5" — 800x480 Settings](images/5in_800x480_settings.png) | **Keypad**<br>![5" — 800x480 Keypad](images/5in_800x480_keypad.png) |
| **Standby (Moonraker / MCU offline)**<br>![5" — 800x480 Standby (Moonraker / MCU offline)](images/5in_800x480_standby.png) | |

### 7" — 1024x600

Scaled-up fonts, icons and spacing for 1024x600 panels.

![7" — 1024x600 home](images/7in_1024x600_home.png)

| | |
| --- | --- |
| **Control › Movement**<br>![7" — 1024x600 Control › Movement](images/7in_1024x600_control_move.png) | **Control › Temperature**<br>![7" — 1024x600 Control › Temperature](images/7in_1024x600_control_temp.png) |
| **Files**<br>![7" — 1024x600 Files](images/7in_1024x600_files.png) | **Console**<br>![7" — 1024x600 Console](images/7in_1024x600_console.png) |
| **MMU (BoxTurtle AFC)**<br>![7" — 1024x600 MMU (BoxTurtle AFC)](images/7in_1024x600_mmu.png) | **System**<br>![7" — 1024x600 System](images/7in_1024x600_system.png) |
| **Settings**<br>![7" — 1024x600 Settings](images/7in_1024x600_settings.png) | **Keypad**<br>![7" — 1024x600 Keypad](images/7in_1024x600_keypad.png) |
| **Standby (Moonraker / MCU offline)**<br>![7" — 1024x600 Standby (Moonraker / MCU offline)](images/7in_1024x600_standby.png) | |

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
