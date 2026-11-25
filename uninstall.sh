#!/usr/bin/env bash
# Removes abg3d-screen and restores the touchscreen service recorded by install.sh.
# Usage: ./uninstall.sh           keep saved settings
#        ./uninstall.sh --purge   also delete ~/.config/abg3d-screen
set -uo pipefail

APP="abg3d-screen"
SERVICE="${APP}.service"
INSTALL_DIR="/opt/${APP}"
STATE_DIR="/var/lib/${APP}"
STATE_FILE="${STATE_DIR}/state.txt"
SUDOERS_FILE="/etc/sudoers.d/${APP}"
UNIT_FILE="/etc/systemd/system/${SERVICE}"
PURGE=0
[[ "${1:-}" == "--purge" ]] && PURGE=1

info() { printf '==> %s\n' "$*"; }
warn() { printf 'WARNING: %s\n' "$*" >&2; }

[[ $EUID -ne 0 ]] || { warn "Run as your normal user, not root."; exit 1; }
command -v sudo >/dev/null || { warn "sudo is required."; exit 1; }

info "Stopping and disabling ${SERVICE}"
sudo systemctl disable --now "$SERVICE" 2>/dev/null || true
sudo rm -f "$UNIT_FILE"
sudo systemctl daemon-reload 2>/dev/null || true
sudo systemctl reset-failed "$SERVICE" 2>/dev/null || true

info "Removing sudoers rule"
sudo rm -f "$SUDOERS_FILE"

info "Removing application, virtual environment and launcher (${INSTALL_DIR})"
sudo rm -rf "$INSTALL_DIR"

if [[ -f "$STATE_FILE" ]]; then
  info "Restoring the previous touchscreen service"
  while IFS='|' read -r unit enabled active; do
    [[ -z "${unit:-}" || "$unit" == \#* ]] && continue
    if [[ "$enabled" == "enabled" ]]; then
      sudo systemctl enable "$unit" || warn "Could not enable ${unit}."
    fi
    if [[ "$active" == "active" ]]; then
      sudo systemctl start "$unit" || warn "Could not start ${unit}."
    fi
    info "Restored ${unit} (enabled: ${enabled}, active: ${active})"
  done < "$STATE_FILE"
  sudo rm -f "$STATE_FILE"
else
  warn "No state file found. No touchscreen service was restored. Enable KlipperScreen or HelixScreen manually if needed."
fi
sudo rmdir "$STATE_DIR" 2>/dev/null || true

if [[ $PURGE -eq 1 ]]; then
  info "Removing saved settings (~/.config/${APP})"
  rm -rf "${HOME}/.config/${APP}"
else
  info "Saved settings kept in ~/.config/${APP} (run with --purge to delete)."
fi

info "Done. apt packages were left installed."
