#!/usr/bin/env bash
# abg3d-screen uninstaller
#   ./uninstall.sh          remove abg3d-screen.service and /opt/abg3d-screen.
#                           KlipperScreen / HelixScreen stay masked and /var/lib/abg3d-screen/state.txt
#                           is kept, so they do NOT retake the display.
#   ./uninstall.sh --purge  additionally delete ~/.config/abg3d-screen (and abg3d-screen.conf), then
#                           unmask, enable and start the touchscreen UI recorded in state.txt
#                           (plus restore display-manager / X11 hooks) and remove /var/lib/abg3d-screen.
set -euo pipefail

SERVICE="abg3d-screen"
APP_DIR="/opt/abg3d-screen"
STATE_DIR="/var/lib/abg3d-screen"
STATE_FILE="$STATE_DIR/state.txt"
BACKUP_DIR="$STATE_DIR/backup"
USER_NAME="${SUDO_USER:-$(id -un)}"
USER_HOME="$(getent passwd "$USER_NAME" | cut -d: -f6)"
USER_UID="$(id -u "$USER_NAME")"
USER_UNIT_DIR="$USER_HOME/.config/systemd/user"
PRINTER_DATA="${PRINTER_DATA:-$USER_HOME/printer_data}"
PURGE=0

for arg in "$@"; do
  case "$arg" in
    --purge) PURGE=1 ;;
    -h|--help) sed -n '2,8p' "$0"; exit 0 ;;
    *) echo "unknown option: $arg" >&2; exit 2 ;;
  esac
done

ok()   { printf '\033[1;32m[ OK ]\033[0m %s\n' "$*"; }
info() { printf '\033[1;34m[....]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[WARN]\033[0m %s\n' "$*"; }

SUDO="sudo"
[ "$(id -u)" -eq 0 ] && SUDO=""

as_user() {
  if [ "$(id -u)" -eq 0 ]; then runuser -u "$USER_NAME" -- "$@"; else sudo -u "$USER_NAME" "$@"; fi
}
user_bus_ok() { [ -S "/run/user/$USER_UID/bus" ]; }
usysctl() {
  as_user env XDG_RUNTIME_DIR="/run/user/$USER_UID" \
    DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$USER_UID/bus" systemctl --user "$@"
}
field() { echo "$1" | tr ' ' '\n' | sed -n "s/^$2=//p"; }

# read the saved state before anything is touched
STATE=""
[ -f "$STATE_FILE" ] && STATE="$($SUDO cat "$STATE_FILE")"

# ------------------------------------------------------------ remove abg3d-screen
info "Stopping and removing $SERVICE.service"
$SUDO systemctl stop "$SERVICE.service" 2>/dev/null || true
$SUDO systemctl disable "$SERVICE.service" 2>/dev/null || true
$SUDO rm -f "/etc/systemd/system/$SERVICE.service"
$SUDO systemctl daemon-reload
$SUDO systemctl reset-failed "$SERVICE.service" 2>/dev/null || true

info "Removing $APP_DIR and system integration files"
$SUDO rm -rf "$APP_DIR"
$SUDO rm -f /etc/udev/rules.d/99-abg3d-screen-backlight.rules \
            /etc/polkit-1/rules.d/50-abg3d-screen-nm.rules \
            /etc/polkit-1/localauthority/50-local.d/50-abg3d-screen-nm.pkla
$SUDO udevadm control --reload-rules 2>/dev/null || true
ASVC="$PRINTER_DATA/moonraker.asvc"
if [ -f "$ASVC" ] && grep -qx "$SERVICE" "$ASVC"; then
  sed -i "/^${SERVICE}\$/d" "$ASVC"
  ok "Removed $SERVICE from moonraker.asvc"
fi

if [ "$PURGE" -ne 1 ]; then
  if [ -n "$STATE" ]; then
    ok "Previous touchscreen units stay masked: $(echo "$STATE" | awk '$1=="system"||$1=="user"{print $2}' | xargs echo)"
    ok "State kept in $STATE_FILE - run '$0 --purge' to hand the display back to them"
  fi
  ok "abg3d-screen removed (display precedence still locked)"
  exit 0
fi

# ------------------------------------------------------------------ --purge
rm -rf "$USER_HOME/.config/abg3d-screen"
rm -f "$PRINTER_DATA/config/abg3d-screen.conf"
ok "Deleted ~/.config/abg3d-screen and abg3d-screen.conf"

if [ -f "$BACKUP_DIR/Xwrapper.config" ]; then
  $SUDO cp "$BACKUP_DIR/Xwrapper.config" /etc/X11/Xwrapper.config
  ok "Restored original /etc/X11/Xwrapper.config"
fi

# restore X11 / display-manager / autostart hooks
while read -r kind tag path _rest; do
  case "$kind" in
    hook)
      if [ -f "$BACKUP_DIR/$tag" ]; then
        $SUDO cp -p "$BACKUP_DIR/$tag" "$path" && ok "Restored $path"
      fi ;;
    autostart)
      if [ -f "$BACKUP_DIR/$tag" ]; then
        $SUDO mkdir -p "$(dirname "$path")"
        $SUDO mv "$BACKUP_DIR/$tag" "$path" && ok "Restored autostart entry $path"
        [[ "$path" == "$USER_HOME"/* ]] && $SUDO chown "$USER_NAME": "$path"
      fi ;;
  esac
done <<<"$STATE"

# unmask every recorded unit and put its unit file back
WANT=()
while read -r kind unit rest; do
  [ "$kind" = "system" ] || [ "$kind" = "user" ] || continue
  file="$(field "$rest" file)"
  en="$(field "$rest" enabled)"
  act="$(field "$rest" active)"
  if [ "$kind" = "system" ]; then
    $SUDO systemctl unmask "$unit" >/dev/null 2>&1 || true
    [ -L "/etc/systemd/system/$unit" ] && [ "$(readlink "/etc/systemd/system/$unit")" = "/dev/null" ] && \
      $SUDO rm -f "/etc/systemd/system/$unit"
    if [ "$file" != "-" ] && [ -f "$BACKUP_DIR/system-$unit" ]; then
      $SUDO mv "$BACKUP_DIR/system-$unit" "$file"
    fi
  else
    [ -L "$USER_UNIT_DIR/$unit" ] && $SUDO rm -f "$USER_UNIT_DIR/$unit"
    if [ "$file" != "-" ] && [ -f "$BACKUP_DIR/user-$unit" ]; then
      $SUDO mv "$BACKUP_DIR/user-$unit" "$file"
      $SUDO chown "$USER_NAME": "$file"
    fi
  fi
  ok "Unmasked $kind unit $unit"
  if [ "$en" = "yes" ] || [ "$act" = "yes" ]; then
    WANT+=("$kind:$unit")
  fi
done <<<"$STATE"
$SUDO systemctl daemon-reload
user_bus_ok && usysctl daemon-reload 2>/dev/null || true

# with nothing recorded as enabled/active, hand the display to the first recorded touchscreen UI
if [ "${#WANT[@]}" -eq 0 ]; then
  first="$(echo "$STATE" | awk '($1=="system"||$1=="user") && tolower($2) ~ /klipperscreen|helix/ {print $1":"$2; exit}')"
  [ -n "$first" ] && WANT+=("$first")
fi

for item in "${WANT[@]}"; do
  kind="${item%%:*}"; unit="${item#*:}"
  if [ "$kind" = "system" ]; then
    $SUDO systemctl enable "$unit" && $SUDO systemctl start "$unit" && ok "Enabled and started $unit" || \
      warn "Could not start $unit"
  elif user_bus_ok; then
    usysctl enable "$unit" && usysctl start "$unit" && ok "Enabled and started user unit $unit" || \
      warn "Could not start user unit $unit"
  else
    as_user mkdir -p "$USER_UNIT_DIR/default.target.wants"
    src="$USER_UNIT_DIR/$unit"
    [ -f "$src" ] || src="$(ls /etc/systemd/user/"$unit" /usr/lib/systemd/user/"$unit" 2>/dev/null | head -n1)"
    [ -n "$src" ] && as_user ln -sfn "$src" "$USER_UNIT_DIR/default.target.wants/$unit"
    ok "Enabled user unit $unit (starts at next login of $USER_NAME)"
  fi
done
[ "${#WANT[@]}" -eq 0 ] && info "No previous touchscreen service recorded - nothing to restore"

$SUDO rm -rf "$STATE_DIR"
ok "abg3d-screen purged; display precedence returned to the previous touchscreen UI"
