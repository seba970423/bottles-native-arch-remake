#!/usr/bin/env bash
set -euo pipefail

package_name=bottles-native-arch
system76_unit=com.system76.Scheduler.service
script_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
system76_backup=/etc/system76-scheduler/config.kdl.bottles-native-arch.backup

confirm() {
  local prompt=$1
  local reply
  if [[ ! -t 0 ]]; then
    printf '%s\n' 'The uninstaller requires an interactive terminal.' >&2
    return 1
  fi
  read -r -p "${prompt} [y/N] " reply
  [[ ${reply} == [Yy] || ${reply} == [Yy][Ee][Ss] ]]
}

if [[ ${EUID} -eq 0 ]]; then
  printf '%s\n' 'Do not run this script as root; it requests sudo only when needed.' >&2
  exit 1
fi

for command_name in pacman sudo; do
  if ! command -v "${command_name}" >/dev/null 2>&1; then
    printf 'Missing required command: %s\n' "${command_name}" >&2
    exit 1
  fi
done

if ! installed=$(pacman -Q "${package_name}" 2>/dev/null); then
  printf '%s\n' 'Bottles Native is not installed.'
  exit 0
fi

printf 'Installed package: %s\n' "${installed}"
printf '%s\n' 'This removes the application package only.'
printf '%s\n' 'Bottle data, UMU prefixes, game files, settings, and rollback checkpoints will be preserved.'
if ! confirm 'Remove Bottles Native?'; then
  printf '%s\n' 'Uninstall cancelled.'
  exit 0
fi

if pgrep -x bottles >/dev/null 2>&1; then
  printf '%s\n' 'Close Bottles completely, then run the uninstaller again.' >&2
  exit 1
fi

sudo pacman -R "${package_name}"
printf '%s\n' 'Bottles Native was removed. User data was preserved.'

if pacman -Q system76-scheduler >/dev/null 2>&1 \
  && command -v systemctl >/dev/null 2>&1 \
  && systemctl is-enabled --quiet "${system76_unit}" 2>/dev/null; then
  printf '%s\n' 'System76 Scheduler remains an enabled system-wide service.'
  if confirm 'Disable and stop System76 Scheduler?'; then
    sudo systemctl disable --now "${system76_unit}"
  fi
fi

if [[ -f ${system76_backup} ]]; then
  printf '%s\n' 'A pre-workaround System76 Scheduler configuration backup exists.'
  printf '%s\n' 'Restoring it may re-enable the PipeWire monitor and replace later edits to that config.'
  if confirm 'Restore the pre-workaround System76 configuration?'; then
    sudo "${script_root}/system76-pipewire-workaround.sh" restore
  fi
fi

for backend in gamemode system76-scheduler; do
  if pacman -Q "${backend}" >/dev/null 2>&1; then
    printf '%s\n' "${backend} may be used by applications other than Bottles."
    if confirm "Remove ${backend} too?"; then
      sudo pacman -Rns "${backend}"
    fi
  fi
done

printf '%s\n' 'Uninstall complete. Preserved user data can be removed manually if it is no longer needed.'
