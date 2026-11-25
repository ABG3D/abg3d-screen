#!/usr/bin/env bash
# abg3d-screen installer for Raspberry Pi 4B (1 GB) with a touchscreen.
# Run as the normal user that runs Klipper (for example "pi"). Do not run as root.
set -euo pipefail

APP="abg3d-screen"
SERVICE="${APP}.service"
INSTALL_DIR="/opt/${APP}"
VENV_DIR="${INSTALL_DIR}/venv"
STATE_DIR="/var/lib/${APP}"
STATE_FILE="${STATE_DIR}/state.txt"
SUDOERS_FILE="/etc/sudoers.d/${APP}"
UNIT_FILE="/etc/systemd/system/${SERVICE}"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_USER="$(id -un)"
TOUCH_UNITS=("klipperscreen.service" "helixscreen.service")

# Prebuilt apt packages only (python3-tk is the GUI binding), so nothing is compiled on the Pi.
APT_PACKAGES=(python3 python3-venv python3-tk fonts-dejavu-core xinit
              xserver-xorg-core xserver-xorg-input-libinput x11-xserver-utils)

info() { printf '==> %s\n' "$*"; }
warn() { printf 'WARNING: %s\n' "$*" >&2; }
die()  { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

# ---------------------------------------------------------------- 0. preflight
[[ $EUID -ne 0 ]] || die "Run as your normal user (for example 'pi'), not root."
command -v sudo >/dev/null || die "sudo is required."
[[ -d "$REPO_DIR/abg3d_screen" ]] || die "abg3d_screen/ not found next to install.sh."

info "Checking that all repository paths are lowercase"
bad="$(cd "$REPO_DIR" && find . -path ./.git -prune -o -print | sed 's|^\./||' | grep -E '[A-Z]' | grep -v -x -E '(README\.md|LICENSE)' || true)"
if [[ -n "$bad" ]]; then
  printf '%s\n' "$bad" >&2
  die "Uppercase paths found. Rename them to lowercase before installing."
fi

. /etc/os-release || die "Cannot read /etc/os-release."
case "${ID:-}" in
  debian) [[ "${VERSION_ID%%.*}" -ge 12 ]] || die "Debian 12 or newer is required." ;;
  raspbian) ;;
  *) warn "Untested distribution: ${ID:-unknown}." ;;
esac

MODEL="$(tr -d '\0' < /proc/device-tree/model 2>/dev/null || echo unknown)"
case "$MODEL" in
  *"Raspberry Pi 4"*) ;;
  *) warn "Target is Raspberry Pi 4B. Detected: ${MODEL}." ;;
esac
MEM_MB="$(awk '/MemTotal/ {print int($2/1024)}' /proc/meminfo)"
SWAP_MB="$(awk '/SwapTotal/ {print int($2/1024)}' /proc/meminfo)"
[[ "$MEM_MB" -ge 900 ]] || warn "Only ${MEM_MB} MB RAM detected. 1 GB is the minimum target."
if [[ "$SWAP_MB" -lt 512 ]]; then
  warn "Swap is ${SWAP_MB} MB. Use 512 MB or more on a 1 GB Pi to avoid out-of-memory during install."
fi
[[ "$(uname -m)" == "aarch64" ]] || warn "64-bit OS recommended (detected $(uname -m))."

# ---------------------------------------------------------------- 1. system packages
info "Installing system packages (prebuilt only, no compilation)"
sudo apt-get update -qq
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends "${APT_PACKAGES[@]}"
sudo apt-get clean

# ---------------------------------------------------------------- 2. touchscreen services
info "Checking for KlipperScreen or HelixScreen"
UNIT_LIST="$(systemctl list-unit-files --type=service --no-legend --no-pager | awk '{print $1}')"
sudo mkdir -p "$STATE_DIR"
TMP_STATE="$(mktemp)"
echo "# abg3d-screen: previous touchscreen units, one per line as unit|enabled|active" > "$TMP_STATE"
for want in "${TOUCH_UNITS[@]}"; do
  unit="$(printf '%s\n' "$UNIT_LIST" | grep -i -x -m1 -- "$want" || true)"
  [[ -n "$unit" ]] || continue
  enabled="$(systemctl is-enabled "$unit" 2>/dev/null || true)"
  active="$(systemctl is-active "$unit" 2>/dev/null || true)"
  echo "${unit}|${enabled}|${active}" >> "$TMP_STATE"
  info "Found ${unit} (enabled: ${enabled:-no}, active: ${active:-no}). Stopping and disabling."
  sudo systemctl stop "$unit" || warn "Could not stop ${unit}."
  sudo systemctl disable "$unit" || warn "Could not disable ${unit}."
done
# Keep the first record so a re-run never overwrites what uninstall should restore.
if [[ -f "$STATE_FILE" ]]; then
  info "Existing state kept: ${STATE_FILE}"
else
  sudo install -m 0644 "$TMP_STATE" "$STATE_FILE"
fi
rm -f "$TMP_STATE"

# ---------------------------------------------------------------- 3. application files
info "Installing application to ${INSTALL_DIR}"
sudo mkdir -p "$INSTALL_DIR/bin"
sudo rm -rf "$INSTALL_DIR/abg3d_screen"
sudo cp -r "$REPO_DIR/abg3d_screen" "$REPO_DIR/requirements.txt" "$INSTALL_DIR/"
[[ -f "$REPO_DIR/version" ]] && sudo cp "$REPO_DIR/version" "$INSTALL_DIR/"
sudo find "$INSTALL_DIR" -name __pycache__ -type d -prune -exec rm -rf {} +
sudo chown -R "$RUN_USER:$RUN_USER" "$INSTALL_DIR"

# ---------------------------------------------------------------- 4. python environment
info "Creating Python environment (pip without cache, nothing compiled)"
if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  python3 -m venv "$VENV_DIR"
fi
"$VENV_DIR/bin/pip" install --no-cache-dir --quiet -r "$INSTALL_DIR/requirements.txt"
"$VENV_DIR/bin/python" -c "import tkinter" || die "Tkinter is missing. Check python3-tk."

# ---------------------------------------------------------------- 5. launcher
info "Writing launcher scripts"
cat > "$INSTALL_DIR/bin/run.sh" <<LAUNCH
#!/bin/sh
# Starts abg3d-screen. Uses the current display if there is one, otherwise a minimal X on VT7.
APP_DIR="$INSTALL_DIR"
cd "\$APP_DIR" || exit 1
if [ -n "\$DISPLAY" ]; then
    exec "\$APP_DIR/venv/bin/python" -m abg3d_screen "\$@"
fi
exec /usr/bin/xinit "\$APP_DIR/bin/session.sh" -- :0 vt7 -nolisten tcp
LAUNCH

cat > "$INSTALL_DIR/bin/session.sh" <<SESSION
#!/bin/sh
# Runs inside the minimal X session. Keeps the screen awake.
xset s off 2>/dev/null
xset -dpms 2>/dev/null
xset s noblank 2>/dev/null
APP_DIR="$INSTALL_DIR"
cd "\$APP_DIR" || exit 1
exec "\$APP_DIR/venv/bin/python" -m abg3d_screen
SESSION
chmod +x "$INSTALL_DIR/bin/run.sh" "$INSTALL_DIR/bin/session.sh"

# ---------------------------------------------------------------- 6. permissions
info "Allowing restart and host control without a password (exact commands only)"
TMP_SUDO="$(mktemp)"
cat > "$TMP_SUDO" <<SUDOERS
# abg3d-screen: exact service commands only.
${RUN_USER} ALL=(root) NOPASSWD: /usr/bin/systemctl restart klipper, /usr/bin/systemctl restart moonraker, /usr/bin/systemctl reboot, /usr/bin/systemctl poweroff
SUDOERS
sudo install -m 0440 "$TMP_SUDO" "$SUDOERS_FILE"
rm -f "$TMP_SUDO"
sudo visudo -cf "$SUDOERS_FILE" >/dev/null || { sudo rm -f "$SUDOERS_FILE"; die "sudoers validation failed."; }
if [[ -d /etc/X11 ]]; then
  printf 'allowed_users=anybody\nneeds_root_rights=yes\n' | sudo tee /etc/X11/Xwrapper.config >/dev/null
fi

# ---------------------------------------------------------------- 7. systemd service
info "Installing ${SERVICE}"
TMP_UNIT="$(mktemp)"
cat > "$TMP_UNIT" <<UNIT
[Unit]
Description=abg3d-screen touchscreen interface for Klipper
After=network-online.target moonraker.service klipper.service
Wants=network-online.target moonraker.service
Conflicts=getty@tty7.service

[Service]
Type=simple
User=${RUN_USER}
WorkingDirectory=${INSTALL_DIR}
ExecStart=${INSTALL_DIR}/bin/run.sh
Restart=on-failure
RestartSec=5
StandardInput=tty
StandardOutput=journal
StandardError=journal
TTYPath=/dev/tty7
TTYReset=yes
TTYVHangup=yes
TTYVTDisallocate=yes
MemoryHigh=350M
MemoryMax=450M

[Install]
WantedBy=multi-user.target
UNIT
sudo install -m 0644 "$TMP_UNIT" "$UNIT_FILE"
rm -f "$TMP_UNIT"
sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE"
sudo systemctl restart "$SERVICE"
mkdir -p "$HOME/.config/abg3d-screen"

sleep 3
if systemctl is-active --quiet "$SERVICE"; then
  info "${SERVICE} is running and enabled for every boot."
else
  warn "${SERVICE} is not active yet. Check: journalctl -u ${SERVICE} -n 50"
fi
