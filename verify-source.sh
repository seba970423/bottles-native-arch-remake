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
umu_display="${source_root}/bottles/backend/umu/display_backend.py"
umu_gamescope="${source_root}/bottles/backend/umu/gamescope.py"
umu_graphics="${source_root}/bottles/backend/umu/graphics.py"
library_blueprint="${source_root}/bottles/frontend/ui/library-entry.blp"
library_widget="${source_root}/bottles/frontend/widgets/library.py"
library_view="${source_root}/bottles/frontend/views/library.py"
library_style="${source_root}/bottles/frontend/ui/style.css"

if [[ ! -f ${preferences} ]]; then
  printf 'Source verification failed: %s is missing.\n' "${preferences}" >&2
  exit 1
fi

for feature in \
  "${manager}:def set_umu_data_path" \
  "${umu_dialog}:Choose the UMU Game Location" \
  "${umu_blueprint}:Managed Prefix Location" \
  "${umu_game_blueprint}:combo_dxvk_override" \
  "${umu_game_blueprint}:combo_d7vk_override" \
  "${umu_game_blueprint}:combo_vkd3d_override" \
  "${umu_game_blueprint}:row_graphics_activity" \
  "${umu_game_blueprint}:row_graphics_versions" \
  "${umu_dialog}:def __update_graphics_activity" \
  "${umu_executor}:def graphics_activity" \
  "${umu_graphics}:def graphics_report_from_output" \
  "${umu_dialog}:def __graphics_rows" \
  "${umu_dialog}:def __update_graphics" \
  "${umu_graphics}:class UmuD7vkOverride" \
  "${umu_graphics}:def configure_graphics_environment" \
  "${umu_graphics}:def _private_runner" \
  "${umu_meson}:'graphics.py'" \
  "${umu_game_blueprint}:combo_sync_backend" \
  "${umu_game_blueprint}:combo_display_backend" \
  "${umu_game_blueprint}:switch_gamescope" \
  "${umu_game_blueprint}:entry_gamescope_game_resolution" \
  "${umu_game_blueprint}:entry_gamescope_output_resolution" \
  "${umu_game_blueprint}:combo_gamescope_game_resolution" \
  "${umu_game_blueprint}:combo_gamescope_output_resolution" \
  "${umu_dialog}:def __gamescope_resolution_changed" \
  "${umu_game_blueprint}:combo_gamescope_filter" \
  "${umu_game_blueprint}:combo_gamescope_scaling_mode" \
  "${umu_game_blueprint}:spin_gamescope_fps" \
  "${umu_dialog}:def __gamescope_settings" \
  "${umu_dialog}:\"gamescope\": self.__gamescope_settings().to_dict()" \
  "${umu_dialog}:SYNC_BACKEND_IDS" \
  "${umu_dialog}:DISPLAY_BACKEND_IDS" \
  "${umu_dialog}:def __update_display_backend" \
  "${umu_dialog}:\"display_backend\": _selected_id(" \
  "${umu_dxvk}:class UmuDxvkOverride" \
  "${umu_dxvk}:def restore" \
  "${umu_meson}:'dxvk_override.py'" \
  "${umu_meson}:'display_backend.py'" \
  "${umu_meson}:'gamescope.py'" \
  "${umu_gamescope}:class GamescopeSettings" \
  "${umu_gamescope}:def resolve_gamescope" \
  "${umu_gamescope}:def wrap_gamescope" \
  "${umu_display}:def configure_display_environment" \
  "${umu_display}:def resolve_display_backend" \
  "${umu_executor}:def _configure_sync_environment" \
  "${umu_executor}:display = configure_display_environment(" \
  "${umu_executor}:nested_x11=gamescope.active" \
  "${umu_executor}:argv, overlay_reason = wrap_gamescope(" \
  "${umu_executor}:argv = (mangohud, \"--dlsym\", *argv)" \
  "${library_blueprint}:label: _(\"Launch\");" \
  "${library_blueprint}:label: _(\"Launch with Steam\");" \
  "${library_view}:self.items_per_line = max(entry_count + 1, 1)" \
  "${library_blueprint}:halign: fill;" \
  "${library_blueprint}:valign: fill;" \
  "${library_blueprint}:"library-entry-launch-pill"" \
  "${library_style}:.library-entry-launch-pill {" \
  "${library_style}:background-color: alpha(#000000, .48);" \
  "${library_style}:padding: 10px 28px;"; do
  feature_file=${feature%%:*}
  feature_text=${feature#*:}
  if ! grep -Fq "${feature_text}" "${feature_file}"; then
    printf 'Source verification failed: a native UMU feature is incomplete (%s).\n' \
      "${feature_text}" >&2
    exit 1
  fi
done

if grep -Fq 'tooltip-text: _("Launch");' "${library_blueprint}"; then
  printf '%s\n' 'Source verification failed: the invisible Launch tooltip regression is present.' >&2
  exit 1
fi

if grep -Fq '.library-entry-launch-label {' "${library_style}"; then
  printf '%s\n' 'Source verification failed: the floating Launch-label regression is present.' >&2
  exit 1
fi

# Bottles 67.4 adds a third UMU action.  It must not live in the bottom
# title/action row, where it steals width and causes GTK to ellipsize the
# already-shortened title a second time.  It also must not be placed inside a
# full-card details overlay, because that intercepts hover/clicks and prevents
# the Launch pill from appearing.  Keep it in its own small top-right revealer.
if grep -Fq '"library-entry-actions"' "${library_blueprint}" ||
   grep -Fq '.library-entry-actions >' "${library_style}"; then
  printf '%s\n' 'Source verification failed: the cramped library-card toolbar regression is present.' >&2
  exit 1
fi

if sed -n '/Revealer revealer_details {/,/Revealer revealer_umu_actions {/p' "${library_blueprint}" | grep -Fq 'Overlay {'; then
  printf '%s\n' 'Source verification failed: the full-card details overlay blocks the Launch button.' >&2
  exit 1
fi

if ! sed -n '/Revealer revealer_details {/,/^[[:space:]]*}/p' "${library_blueprint}" | grep -Fq 'valign: end;'; then
  printf '%s\n' 'Source verification failed: the details revealer no longer stays at the card bottom.' >&2
  exit 1
fi

if ! grep -Fq 'Revealer revealer_umu_actions {' "${library_blueprint}" ||
   ! sed -n '/Revealer revealer_umu_actions {/,/MenuButton btn_umu_actions {/p' "${library_blueprint}" | grep -Fq 'halign: end;' ||
   ! sed -n '/Revealer revealer_umu_actions {/,/MenuButton btn_umu_actions {/p' "${library_blueprint}" | grep -Fq 'valign: start;' ||
   ! sed -n '/MenuButton btn_umu_actions {/,/^[[:space:]]*}/p' "${library_blueprint}" | grep -Fq '"circular"'; then
  printf '%s\n' 'Source verification failed: the non-intrusive UMU More Actions overlay is missing.' >&2
  exit 1
fi

if ! grep -Fq 'revealer_umu_actions = Gtk.Template.Child()' "${library_widget}" ||
   ! grep -Fq 'self.revealer_umu_actions.set_reveal_child(reveal)' "${library_widget}"; then
  printf '%s\n' 'Source verification failed: the UMU More Actions revealer is not synced with card hover state.' >&2
  exit 1
fi

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

script_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
python3 "${script_root}/test-display-backend.py" "${source_root}"

printf '%s\n' 'Source verification passed: native initialization and UMU safety guards look sane.'
