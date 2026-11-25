# ABG3D-Screen

A touchscreen interface for Klipper and Moonraker, built for a Raspberry Pi 4B (1 GB) with a touchscreen. It runs as a systemd service that starts on every boot and replaces KlipperScreen or HelixScreen.

## Requirements

- Raspberry Pi 4B, 1 GB RAM, with a touchscreen
- Raspberry Pi OS, Debian 12 or 13, or Mainsail OS (64-bit recommended)
- Klipper and Moonraker installed and running
- A regular user with sudo (usually `pi`)
- Swap of 512 MB or more is recommended on 1 GB

### Packages installed automatically by install.sh

| Package | Purpose |
|---|---|
| `python3` | interpreter |
| `python3-venv` | isolated environment for the app |
| `python3-tk` | Tkinter GUI binding (prebuilt, nothing is compiled) |
| `fonts-dejavu-core` | UI font |
| `xinit` | starts a minimal X session on tty7 |
| `xserver-xorg-core` | X server |
| `xserver-xorg-input-libinput` | touchscreen and mouse input |
| `x11-xserver-utils` | `xset`, used to keep the screen awake |

Python dependencies are listed in `requirements.txt`. The app needs none at runtime. pip runs with `--no-cache-dir`, so nothing large is cached on the Pi.

## Repository layout

```
abg3d-screen/
├── abg3d_screen/        application package
├── tools/make_assets.py developer script that regenerates artwork
├── install.sh           installer
├── uninstall.sh         removes the service and restores the previous touchscreen
├── requirements.txt     Python dependencies
├── run-dev.sh           run in a window for development
├── version
└── readme.md
```

All paths are lowercase. install.sh refuses to run if any path contains an uppercase letter, and a CI workflow checks this on every push.

## Install

1. Clone the repository on the Pi:
   ```bash
   cd ~
   git clone https://github.com/<your-account>/abg3d-screen.git
   cd abg3d-screen
   ```
2. Make the scripts executable and run the installer as your normal user, not with sudo:
   ```bash
   chmod +x install.sh uninstall.sh
   ./install.sh
   ```
3. The installer:
   - checks the OS, RAM and swap
   - installs the packages listed above from apt
   - finds KlipperScreen or HelixScreen, records its state in `/var/lib/abg3d-screen/state.txt`, then stops and disables it
   - copies the app to `/opt/abg3d-screen` and creates a virtual environment there
   - allows restarts and host control without a password for exact commands only
   - installs and enables `abg3d-screen.service`, then starts it

The service starts automatically at every boot.

## Service management

| Task | Command |
|---|---|
| Status | `systemctl status abg3d-screen` |
| Start | `sudo systemctl start abg3d-screen` |
| Stop | `sudo systemctl stop abg3d-screen` |
| Restart | `sudo systemctl restart abg3d-screen` |
| Disable autostart | `sudo systemctl disable abg3d-screen` |
| Enable autostart | `sudo systemctl enable abg3d-screen` |
| Live logs | `journalctl -u abg3d-screen -f` |
| Last 100 lines | `journalctl -u abg3d-screen -n 100` |

Settings are stored in `~/.config/abg3d-screen/settings.json` and survive restarts and reboots.

The unit limits memory with `MemoryHigh=350M` and `MemoryMax=450M`, which protects Klipper and Moonraker on a 1 GB board.

## Uninstall and revert

```bash
cd ~/abg3d-screen
./uninstall.sh            # keep saved settings
./uninstall.sh --purge    # also delete ~/.config/abg3d-screen
```

The uninstaller:

1. stops, disables and removes `abg3d-screen.service`
2. removes the sudoers rule
3. removes `/opt/abg3d-screen`, including the virtual environment and launcher scripts
4. reads `/var/lib/abg3d-screen/state.txt` and re-enables and starts the touchscreen service that was active or enabled before install (KlipperScreen or HelixScreen)
5. removes the state file

apt packages are not removed, since other software may use them. To remove the ones that are no longer needed:

```bash
sudo apt-get remove --purge xinit xserver-xorg-core xserver-xorg-input-libinput x11-xserver-utils
sudo apt-get autoremove --purge
```

## Troubleshooting

| Symptom | Check |
|---|---|
| Service fails | `journalctl -u abg3d-screen -n 100` |
| Blank screen | `systemctl status abg3d-screen`, then `bin/run.sh` run from a terminal |
| Demo mode shown | Moonraker is not reachable: `curl http://127.0.0.1:7125/server/info` |
| install.sh reports uppercase paths | rename the reported paths to lowercase and run it again |
| Out of memory during install | add swap, for example 1 GB, then run install.sh again |

## Development

```bash
./run-dev.sh        # 800x480 window; Esc quits
```

Install `python3-tk` first if it is missing.

## License

Choose a license before publishing.
