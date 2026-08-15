#!/usr/bin/env bash
set -euo pipefail

source_root=${1:-.}
preferences="${source_root}/bottles/frontend/views/bottle_preferences.py"
manager="${source_root}/bottles/backend/managers/manager.py"
umu_dialog="${source_root}/bottles/frontend/windows/umu.py"
umu_blueprint="${source_root}/bottles/frontend/ui/dialog-umu-install.blp"
umu_game_blueprint="${source_root}/bottles/frontend/ui/dialog-umu-game.blp"
umu_dxvk="${source_root}/bottles/backend/umu/dxvk_override.py"
umu_meson="${source_root}/bottles/backend/umu/meson.build"
umu_executor="${source_root}/bottles/backend/umu/executor.py"

if [[ ! -f ${preferences} ]]; then
  printf 'Source verification failed: %s is missing.\n' "${preferences}" >&2
  exit 1
fi

for feature in \
  "${manager}:def set_umu_data_path" \
  "${umu_dialog}:Choose the UMU Game Location" \
  "${umu_blueprint}:Managed Prefix Location" \
  "${umu_game_blueprint}:combo_dxvk_override" \
  "${umu_dxvk}:class UmuDxvkOverride" \
  "${umu_dxvk}:def restore" \
  "${umu_meson}:'dxvk_override.py'" \
  "${umu_executor}:argv = (mangohud, \"--dlsym\", *argv)"; do
  feature_file=${feature%%:*}
  feature_text=${feature#*:}
  if ! grep -Fq "${feature_text}" "${feature_file}"; then
    printf 'Source verification failed: a native UMU feature is incomplete (%s).\n' \
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

printf '%s\n' 'Source verification passed: native initialization and UMU safety guards look sane.'
