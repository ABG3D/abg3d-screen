#!/usr/bin/env bash
# abg3d-screen installer
#   ./install.sh           install or update
#   ./install.sh --force   skip the supported-board check
# Run as the printer user (e.g. pi / biqu); sudo is used where needed.
set -euo pipefail

SERVICE="abg3d-screen"
APP_DIR="/opt/abg3d-screen"
STATE_DIR="/var/lib/abg3d-screen"
STATE_FILE="$STATE_DIR/state.txt"
BACKUP_DIR="$STATE_DIR/backup"
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
USER_NAME="${SUDO_USER:-$(id -un)}"
USER_HOME="$(getent passwd "$USER_NAME" | cut -d: -f6)"
PRINTER_DATA="${PRINTER_DATA:-$USER_HOME/printer_data}"
UNIT="/etc/systemd/system/${SERVICE}.service"
FORCE=0
OTHER_SCREENS=(KlipperScreen klipperscreen helixscreen HelixScreen helix-screen)
CONFLICTS="KlipperScreen.service klipperscreen.service helixscreen.service HelixScreen.service"
VT="vt7"
APT_PKGS=(python3 python3-venv python3-gi python3-gi-cairo gir1.2-gtk-3.0 gir1.2-gdkpixbuf-2.0
          xinit xserver-xorg-core xserver-xorg-legacy xserver-xorg-input-libinput
          xserver-xorg-video-fbdev x11-xserver-utils librsvg2-common fonts-dejavu-core)

for arg in "$@"; do
  case "$arg" in
    --force) FORCE=1 ;;
    -h|--help) sed -n '2,5p' "$0"; exit 0 ;;
    *) echo "unknown option: $arg" >&2; exit 2 ;;
  esac
done

ok()   { printf '\033[1;32m[ OK ]\033[0m %s\n' "$*"; }
info() { printf '\033[1;34m[....]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[WARN]\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31m[FAIL]\033[0m %s\n' "$*" >&2; exit 1; }

if [ "$(id -u)" -eq 0 ] && [ -z "${SUDO_USER:-}" ]; then
  die "Run as the printer user, not root (sudo is used where needed)."
fi
SUDO="sudo"
[ "$(id -u)" -eq 0 ] && SUDO=""


# ------------------------------------------------------------ board check
detect_board() {
  local model="" board=""
  [ -r /proc/device-tree/model ] && model="$(tr -d '\0' </proc/device-tree/model)"
  [ -r /etc/armbian-release ] && board="$(. /etc/armbian-release 2>/dev/null; echo "${BOARD:-}")"
  local s
  s="$(echo "$model $board" | tr '[:upper:]' '[:lower:]')"
  case "$s" in
    *"raspberry pi 3 model b"*) echo "Raspberry Pi 3B" ;;
    *"raspberry pi 4 model b"*) echo "Raspberry Pi 4B" ;;
    *cb1*) echo "BTT CB1" ;;
    *cb2*) echo "BTT CB2" ;;
    *"btt"*"pi"*"2"*|*"bigtreetech"*"pi"*"2"*|*"btt-pi2"*|*"bttpi2"*) echo "BTT Pi 2" ;;
    *"btt"*"pi"*|*"bigtreetech"*"pi"*|*"btt-pi"*|*"bttpi"*) echo "BTT Pi 1" ;;
    *) echo "unsupported:${model:-unknown}${board:+ ($board)}" ;;
  esac
}

BOARD="$(detect_board)"
if [[ "$BOARD" == unsupported:* ]]; then
  warn "Board '${BOARD#unsupported:}' is not in the supported list (RPi 3B/4B, BTT CB1/CB2/Pi 1/Pi 2)."
  if [ "$FORCE" -ne 1 ]; then
    if [ -t 0 ]; then
      read -r -p "Continue anyway? [y/N] " ans
      [[ "$ans" =~ ^[Yy]$ ]] || exit 1
    else
      die "Re-run with --force to install on an unsupported board."
    fi
  fi
else
  ok "Detected board: $BOARD"
fi

MEM_KB="$(awk '/MemTotal/ {print $2}' /proc/meminfo)"
if [ "${MEM_KB:-0}" -le 1200000 ]; then
  MEM_HIGH="200M"; MEM_MAX="256M"; ok "1GB-class board: systemd MemoryHigh=$MEM_HIGH MemoryMax=$MEM_MAX"
else
  MEM_HIGH="300M"; MEM_MAX="384M"; ok "RAM $((MEM_KB / 1024)) MB: systemd MemoryHigh=$MEM_HIGH MemoryMax=$MEM_MAX"
fi

# ----------------------------------------------------------------- packages
info "Installing system packages (apt)"
$SUDO apt-get update -qq
$SUDO env DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends "${APT_PKGS[@]}"
ok "System packages installed"

# ------------------------------------------- lock display precedence
# Every other touchscreen UI (system + user units), the display manager and X11 autostart hooks are
# recorded in $STATE_FILE, then stopped, disabled and masked so nothing (systemd, a display manager,
# Moonraker service restarts or update_manager) can bring them back after a reboot or power cycle.
# Only `uninstall.sh --purge` reverses this.
$SUDO mkdir -p "$STATE_DIR" "$BACKUP_DIR"
$SUDO chmod 755 "$STATE_DIR"
$SUDO touch "$STATE_FILE"
if [ -f /etc/abg3d-screen/Xwrapper.config.bak ] && [ ! -f "$BACKUP_DIR/Xwrapper.config" ]; then
  $SUDO cp /etc/abg3d-screen/Xwrapper.config.bak "$BACKUP_DIR/Xwrapper.config"   # migrate pre-2.1 layout
fi
$SUDO rm -rf /etc/abg3d-screen

USER_UID="$(id -u "$USER_NAME")"
USER_UNIT_DIR="$USER_HOME/.config/systemd/user"

recorded() { $SUDO grep -qF -- "$1" "$STATE_FILE" 2>/dev/null; }
record()   { recorded "$1" || echo "$1" | $SUDO tee -a "$STATE_FILE" >/dev/null; }

as_user() {
  if [ "$(id -u)" -eq 0 ]; then runuser -u "$USER_NAME" -- "$@"; else sudo -u "$USER_NAME" "$@"; fi
}
user_bus_ok() { [ -S "/run/user/$USER_UID/bus" ]; }
usysctl() {
  # systemctl --user as the printer user (works from sudo/ssh as long as the user manager runs)
  as_user env XDG_RUNTIME_DIR="/run/user/$USER_UID" \
    DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$USER_UID/bus" systemctl --user "$@"
}

lock_system_unit() {
  local unit="$1" frag en act file=""
  frag="$(systemctl show -p FragmentPath --value "$unit" 2>/dev/null || true)"
  if [ "$frag" = "/dev/null" ] || [ "$(systemctl is-enabled "$unit" 2>/dev/null || true)" = "masked" ]; then
    ok "$unit already masked"
    return
  fi
  en="no"; act="no"
  systemctl is-enabled --quiet "$unit" 2>/dev/null && en="yes"
  systemctl is-active --quiet "$unit" 2>/dev/null && act="yes"
  $SUDO systemctl stop "$unit" 2>/dev/null || true
  $SUDO systemctl disable "$unit" 2>/dev/null || true
  # `systemctl mask` refuses when the real unit file lives in /etc/systemd/system: move it aside first
  if [ -n "$frag" ] && [ -f "$frag" ] && [[ "$frag" == /etc/systemd/system/* ]]; then
    file="$frag"
    $SUDO mv "$frag" "$BACKUP_DIR/system-$unit"
    $SUDO systemctl daemon-reload
  fi
  $SUDO systemctl mask "$unit" >/dev/null 2>&1 || $SUDO ln -sf /dev/null "/etc/systemd/system/$unit"
  record "system $unit enabled=$en active=$act file=${file:--}"
  ok "Locked out $unit (stopped, disabled, masked)"
}

lock_user_unit() {
  local unit="$1" en="no" act="no" file="" src=""
  for d in "$USER_UNIT_DIR" /etc/systemd/user /usr/lib/systemd/user /lib/systemd/user; do
    if [ -e "$d/$unit" ]; then src="$d/$unit"; break; fi
  done
  [ -z "$src" ] && return
  if [ "$(readlink -f "$src")" = "/dev/null" ]; then
    ok "user $unit already masked"
    return
  fi
  if user_bus_ok; then
    usysctl is-enabled --quiet "$unit" 2>/dev/null && en="yes"
    usysctl is-active --quiet "$unit" 2>/dev/null && act="yes"
    usysctl stop "$unit" 2>/dev/null || true
    usysctl disable "$unit" 2>/dev/null || true
  else
    ls "$USER_UNIT_DIR"/*.wants/"$unit" >/dev/null 2>&1 && en="yes"
    $SUDO pkill -u "$USER_NAME" -f -i "klipperscreen|helixscreen" 2>/dev/null || true
    $SUDO rm -f "$USER_UNIT_DIR"/*.wants/"$unit" /etc/systemd/user/*.wants/"$unit"
  fi
  if [ "$src" = "$USER_UNIT_DIR/$unit" ] && [ -f "$src" ]; then
    file="$src"
    $SUDO mv "$src" "$BACKUP_DIR/user-$unit"
  fi
  as_user mkdir -p "$USER_UNIT_DIR"
  as_user ln -sfn /dev/null "$USER_UNIT_DIR/$unit"
  user_bus_ok && usysctl daemon-reload 2>/dev/null || true
  record "user $unit enabled=$en active=$act file=${file:--}"
  ok "Locked out user unit $unit (stopped, disabled, masked)"
}

info "Locking display precedence for $SERVICE"
for name in "${OTHER_SCREENS[@]}"; do
  unit="$name.service"
  if systemctl list-unit-files --no-legend "$unit" 2>/dev/null | grep -q "^$unit" || \
     [ -f "$BACKUP_DIR/system-$unit" ]; then
    lock_system_unit "$unit"
  fi
  lock_user_unit "$unit"
done

# display manager (LightDM etc.) owns :0 and a VT and may autostart a touchscreen UI
DM_UNIT=""
if [ -L /etc/systemd/system/display-manager.service ]; then
  DM_LINK="$(readlink -f /etc/systemd/system/display-manager.service)"
  [ -e "$DM_LINK" ] && [ "$DM_LINK" != "/dev/null" ] && DM_UNIT="$(basename "$DM_LINK")"
fi
if [ -z "$DM_UNIT" ] && systemctl list-unit-files --no-legend lightdm.service 2>/dev/null | grep -q enabled; then
  DM_UNIT="lightdm.service"
fi
if [ -n "$DM_UNIT" ]; then
  warn "Display manager $DM_UNIT would compete for the display - locking it out"
  lock_system_unit "$DM_UNIT"
fi

# X11 / autostart hooks that launch another touchscreen UI
neutralize_file() {
  local f="$1" tag="$2"
  [ -f "$f" ] || return 0
  grep -qiE "$HOOK_RE" "$f" || return 0
  grep -q "abg3d-screen-disabled" "$f" && return 0
  $SUDO cp -p "$f" "$BACKUP_DIR/$tag"
  $SUDO sed -i -E "/$HOOK_RE/I s/^/# abg3d-screen-disabled: /" "$f"
  record "hook $tag $f"
  ok "Disabled touchscreen launch lines in $f"
}
HOOK_RE="[Kk]lipper[Ss]creen|[Hh]elix-?[Ss]creen"
neutralize_file "$USER_HOME/.xinitrc" "xinitrc"
neutralize_file "$USER_HOME/.xsession" "xsession"
neutralize_file /etc/rc.local "rc.local"
for f in /etc/lightdm/lightdm.conf /etc/lightdm/lightdm.conf.d/*.conf; do
  [ -f "$f" ] && neutralize_file "$f" "lightdm-$(basename "$f")"
done
for f in "$USER_HOME"/.config/autostart/*.desktop /etc/xdg/autostart/*.desktop; do
  [ -f "$f" ] || continue
  if grep -qiE "$HOOK_RE" "$f"; then
    tag="autostart-$(basename "$f")"
    $SUDO mv "$f" "$BACKUP_DIR/$tag"
    record "autostart $tag $f"
    ok "Removed autostart entry $f"
  fi
done
$SUDO systemctl daemon-reload
ok "Previous touchscreen state saved to $STATE_FILE"

# ------------------------------------------------------------ application
info "Installing application to $APP_DIR"
$SUDO mkdir -p "$APP_DIR"
$SUDO rm -rf "$APP_DIR/abg3d_screen" "$APP_DIR/scripts"
tar -C "$SRC_DIR" --exclude=./venv --exclude=./.git --exclude='__pycache__' -cf - . | $SUDO tar -C "$APP_DIR" -xf -
$SUDO chown -R "$USER_NAME": "$APP_DIR"
chmod +x "$APP_DIR/scripts/launch.sh" "$APP_DIR/install.sh" "$APP_DIR/uninstall.sh" 2>/dev/null || true

info "Creating Python venv (system site-packages for PyGObject)"
if [ ! -x "$APP_DIR/venv/bin/python3" ]; then
  python3 -m venv --system-site-packages "$APP_DIR/venv"
fi
if "$APP_DIR/venv/bin/python3" -m pip install --disable-pip-version-check -q -r "$APP_DIR/requirements.txt"; then
  ok "venv ready ($("$APP_DIR/venv/bin/python3" -c 'import websockets; print("websockets", websockets.__version__)'))"
else
  warn "pip install failed (offline?) - using the built-in WebSocket client"
fi
"$APP_DIR/venv/bin/python3" - <<'PY'
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: F401
import cairo  # noqa: F401
PY
ok "PyGObject / GTK 3 / Cairo import check passed"

# ------------------------------------------------------- X + permissions
if [ -f /etc/X11/Xwrapper.config ] && [ ! -f "$BACKUP_DIR/Xwrapper.config" ]; then
  $SUDO cp /etc/X11/Xwrapper.config "$BACKUP_DIR/Xwrapper.config"
fi
$SUDO tee /etc/X11/Xwrapper.config >/dev/null <<'EOF'
allowed_users=anybody
needs_root_rights=yes
EOF
for g in tty video input render netdev; do
  getent group "$g" >/dev/null && $SUDO usermod -aG "$g" "$USER_NAME"
done

$SUDO tee /etc/udev/rules.d/99-abg3d-screen-backlight.rules >/dev/null <<'EOF'
SUBSYSTEM=="backlight", ACTION=="add", RUN+="/bin/chgrp video /sys/class/backlight/%k/bl_power /sys/class/backlight/%k/brightness", RUN+="/bin/chmod g+w /sys/class/backlight/%k/bl_power /sys/class/backlight/%k/brightness"
EOF
$SUDO udevadm control --reload-rules 2>/dev/null || true
$SUDO udevadm trigger --subsystem-match=backlight 2>/dev/null || true

if command -v nmcli >/dev/null 2>&1; then
  if [ -d /etc/polkit-1/rules.d ]; then
    $SUDO tee /etc/polkit-1/rules.d/50-abg3d-screen-nm.rules >/dev/null <<EOF
polkit.addRule(function(action, subject) {
  if (action.id.indexOf("org.freedesktop.NetworkManager.") == 0 && subject.user == "$USER_NAME") {
    return polkit.Result.YES;
  }
});
EOF
  fi
  if [ -d /etc/polkit-1/localauthority ]; then
    $SUDO mkdir -p /etc/polkit-1/localauthority/50-local.d
    $SUDO tee /etc/polkit-1/localauthority/50-local.d/50-abg3d-screen-nm.pkla >/dev/null <<EOF
[abg3d-screen NetworkManager]
Identity=unix-user:$USER_NAME
Action=org.freedesktop.NetworkManager.*
ResultAny=yes
ResultInactive=yes
ResultActive=yes
EOF
  fi
  ok "NetworkManager (nmcli) access granted to $USER_NAME"
else
  warn "nmcli not found - the Network tab will show IP status only"
fi
ok "Display, backlight and network permissions configured"

# ----------------------------------------------------------------- config
CONF_DIR="$PRINTER_DATA/config"
CONF="$CONF_DIR/abg3d-screen.conf"
if [ -d "$CONF_DIR" ]; then
  if [ ! -f "$CONF" ]; then
    cp "$SRC_DIR/abg3d-screen.conf" "$CONF"
    chown "$USER_NAME": "$CONF" 2>/dev/null || true
    ok "Config created: $CONF"
  else
    ok "Keeping existing config: $CONF"
  fi
else
  CONF="$APP_DIR/abg3d-screen.conf"
  warn "$CONF_DIR not found - using $CONF"
fi
ASVC="$PRINTER_DATA/moonraker.asvc"
if [ -f "$ASVC" ] && ! grep -qx "$SERVICE" "$ASVC"; then
  echo "$SERVICE" >> "$ASVC"
  ok "Added $SERVICE to moonraker.asvc (service control from Mainsail)"
fi

# ---------------------------------------------------------------- systemd
info "Installing $UNIT"
$SUDO tee "$UNIT" >/dev/null <<EOF
[Unit]
Description=abg3d-screen - Klipper touchscreen UI
Documentation=https://github.com/ABG3D/abg3d-screen
After=systemd-user-sessions.service moonraker.service
Wants=moonraker.service
Conflicts=$CONFLICTS
Conflicts=getty@tty7.service
StartLimitIntervalSec=0

[Service]
Type=simple
User=$USER_NAME
SupplementaryGroups=tty video input render
WorkingDirectory=$APP_DIR
Environment=PYTHONUNBUFFERED=1
Environment=PYTHONDONTWRITEBYTECODE=1
Environment=ABG3D_CONFIG=$CONF
# dedicated clean VT ($VT): no getty (tty1) or LightDM (BTT CB2) collisions
ExecStart=/usr/bin/xinit $APP_DIR/scripts/launch.sh -- :0 $VT -nolisten tcp -s 0
Restart=on-failure
RestartSec=3
MemoryAccounting=yes
MemoryHigh=$MEM_HIGH
MemoryMax=$MEM_MAX
Nice=-2
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF
$SUDO systemctl unmask "$SERVICE.service" >/dev/null 2>&1 || true
$SUDO systemctl daemon-reload && $SUDO systemctl enable --now "$SERVICE.service"
$SUDO systemctl restart "$SERVICE.service"   # pick up updated code when re-running the installer
sleep 3
if systemctl is-active --quiet "$SERVICE.service"; then
  ok "$SERVICE is running"
else
  die "$SERVICE failed to start - check: journalctl -u $SERVICE -n 80"
fi
ok "$SERVICE holds display precedence on every boot ($VT). Locked-out units: $(awk '{print $2}' "$STATE_FILE" | xargs echo)"
ok "Done. Logs: journalctl -u $SERVICE -f   Uninstall: $APP_DIR/uninstall.sh [--purge]"
