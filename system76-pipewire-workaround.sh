#!/usr/bin/env bash
set -euo pipefail

config=/etc/system76-scheduler/config.kdl
backup=/etc/system76-scheduler/config.kdl.bottles-native-arch.backup
unit=com.system76.Scheduler.service
pipewire_pattern='^[[:space:]]*pipewire([[:space:]]|$)'

case ${1:-} in
  status)
    [[ -f ${config} ]] && grep -Eq "${pipewire_pattern}" "${config}"
    ;;
  disable)
    if [[ ${EUID} -ne 0 ]]; then
      printf '%s\n' 'Disabling the monitor requires sudo or Polkit.' >&2
      exit 1
    fi
    if [[ ! -f ${config} ]]; then
      printf 'System76 Scheduler config was not found: %s\n' "${config}" >&2
      exit 1
    fi
    if ! grep -Eq "${pipewire_pattern}" "${config}"; then
      printf '%s\n' 'System76 Scheduler PipeWire monitoring is already disabled.'
      exit 0
    fi
    if [[ ! -e ${backup} ]]; then
      cp --archive -- "${config}" "${backup}"
    fi
    sed -E -i "/${pipewire_pattern}/d" "${config}"
    if grep -Eq "${pipewire_pattern}" "${config}"; then
      printf '%s\n' 'Could not disable the PipeWire monitor assignment.' >&2
      exit 1
    fi
    if systemctl is-active --quiet "${unit}"; then
      systemctl restart "${unit}"
    fi
    printf 'Disabled System76 PipeWire monitoring. Backup: %s\n' "${backup}"
    ;;
  restore)
    if [[ ${EUID} -ne 0 ]]; then
      printf '%s\n' 'Restoring the config requires sudo or Polkit.' >&2
      exit 1
    fi
    if [[ ! -f ${backup} ]]; then
      printf '%s\n' 'No Bottles Native System76 configuration backup exists.' >&2
      exit 1
    fi
    cp --archive -- "${backup}" "${config}"
    if systemctl is-active --quiet "${unit}"; then
      systemctl restart "${unit}"
    fi
    printf '%s\n' 'Restored the pre-workaround System76 Scheduler configuration.'
    ;;
  *)
    printf 'Usage: %s {status|disable|restore}\n' "${0##*/}" >&2
    exit 2
    ;;
esac
