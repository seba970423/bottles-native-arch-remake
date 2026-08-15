#!/usr/bin/env bash
set -euo pipefail

source_root=${1:-.}
preferences="${source_root}/bottles/frontend/views/bottle_preferences.py"
manager="${source_root}/bottles/backend/managers/manager.py"
umu_dialog="${source_root}/bottles/frontend/windows/umu.py"
umu_blueprint="${source_root}/bottles/frontend/ui/dialog-umu-install.blp"

if [[ ! -f ${preferences} ]]; then
  printf 'Source verification failed: %s is missing.\n' "${preferences}" >&2
  exit 1
fi

for feature in \
  "${manager}:def set_umu_data_path" \
  "${umu_dialog}:Choose the UMU Game Location" \
  "${umu_blueprint}:Managed Prefix Location"; do
  feature_file=${feature%%:*}
  feature_text=${feature#*:}
  if ! grep -Fq "${feature_text}" "${feature_file}"; then
    printf 'Source verification failed: UMU storage chooser is incomplete (%s).\n' \
      "${feature_text}" >&2
    exit 1
  fi
done

if grep -Eq '^[[:space:]]*if not gamemode_available:[[:space:]]*$' "${preferences}" &&
   sed -n '/if not gamemode_available:/,+2p' "${preferences}" | grep -Eq '^[[:space:]]*return[[:space:]]*$'; then
  printf '%s\n' 'Source verification failed: the GameMode early-return regression is present.' >&2
  exit 1
fi

if grep -Eq 'running_under_sandbox\(\).*return|\.flatpak-info' \
  "${source_root}/bottles/frontend/meson.build" \
  "${source_root}/bottles/frontend/views/bottle_preferences.py"; then
  printf '%s\n' 'Source verification failed: native-execution blockers remain after patching.' >&2
  exit 1
fi

printf '%s\n' 'Source verification passed: native initialization and GameMode guards look sane.'
