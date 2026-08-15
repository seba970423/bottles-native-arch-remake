#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
pkgbuild="${repo_root}/PKGBUILD"

confirm_install() {
  local prompt=$1
  local reply

  if [[ ! -t 0 ]]; then
    printf '%s\n' 'Dependency installation needs an interactive terminal.' >&2
    return 1
  fi

  read -r -p "${prompt} [Y/n] " reply
  [[ -z ${reply} || ${reply} == [Yy] || ${reply} == [Yy][Ee][Ss] ]]
}

confirm_install_default_no() {
  local prompt=$1
  local reply

  if [[ ! -t 0 ]]; then
    return 1
  fi

  read -r -p "${prompt} [y/N] " reply
  [[ ${reply} == [Yy] || ${reply} == [Yy][Ee][Ss] ]]
}

dependency_name() {
  local dependency=$1
  dependency=${dependency%%:*}
  dependency=${dependency%%[\<\>\=]*}
  printf '%s\n' "${dependency}"
}

for command_name in bash pacman sudo; do
  if ! command -v "${command_name}" >/dev/null 2>&1; then
    printf 'Missing required command: %s\n' "${command_name}" >&2
    exit 1
  fi
done

mapfile -t required_dependencies < <(
  bash -c '
    source "$1"
    printf "%s\n" "${depends[@]}" "${makedepends[@]}"
  ' _ "${pkgbuild}"
)

missing_output=$(pacman -T "${required_dependencies[@]}" 2>/dev/null || true)
if [[ -z ${missing_output} ]]; then
  printf '%s\n' 'All required build and runtime dependencies are already installed.'
fi

repo_packages=()
aur_packages=()
while IFS= read -r dependency; do
  [[ -n ${dependency} ]] || continue
  package=$(dependency_name "${dependency}")
  if pacman -Si "${package}" >/dev/null 2>&1; then
    repo_packages+=("${package}")
  else
    aur_packages+=("${package}")
  fi
done <<< "${missing_output}"

if (( ${#repo_packages[@]} )); then
  printf '\nMissing repository packages:\n'
  printf '  %s\n' "${repo_packages[@]}"
  if ! confirm_install 'Install these packages with pacman?'; then
    printf '%s\n' 'Dependency installation cancelled.' >&2
    exit 1
  fi
  sudo pacman -S --needed "${repo_packages[@]}"
fi

if (( ${#aur_packages[@]} )); then
  aur_helper=
  for candidate in paru yay; do
    if command -v "${candidate}" >/dev/null 2>&1; then
      aur_helper=${candidate}
      break
    fi
  done

  printf '\nMissing AUR packages:\n'
  printf '  %s\n' "${aur_packages[@]}"

  if [[ -z ${aur_helper} ]]; then
    printf '%s\n' 'Neither paru nor yay is installed, so the AUR dependencies cannot be installed automatically.' >&2
    exit 1
  fi

  if ! confirm_install "Install these packages with ${aur_helper}?"; then
    printf '%s\n' 'Dependency installation cancelled.' >&2
    exit 1
  fi
  "${aur_helper}" -S --needed "${aur_packages[@]}"
fi

remaining=$(pacman -T "${required_dependencies[@]}" 2>/dev/null || true)
if [[ -n ${remaining} ]]; then
  printf '\nThese dependencies are still unresolved:\n' >&2
  while IFS= read -r dependency; do
    [[ -n ${dependency} ]] && printf '  %s\n' "${dependency}" >&2
  done <<< "${remaining}"
  exit 1
fi

printf '%s\n' 'All required dependencies are installed.'

printf '\n%s\n' 'Optional gaming performance backends:'
if ! pacman -Q gamemode >/dev/null 2>&1; then
  printf '%s\n' '  Feral GameMode applies temporary optimizations only while a game requests them.'
  if confirm_install 'Install the recommended Feral GameMode backend?'; then
    sudo pacman -S --needed gamemode
  fi
else
  printf '%s\n' '  Feral GameMode: installed'
fi

if ! pacman -Q system76-scheduler >/dev/null 2>&1; then
  printf '%s\n' '  System76 Scheduler is EXPERIMENTAL, persistent, system-wide, and may be unstable on some distributions.'
  if confirm_install_default_no 'Install experimental System76 Scheduler as an additional backend?'; then
    sudo pacman -S --needed system76-scheduler
  fi
else
  printf '%s\n' '  System76 Scheduler: installed'
fi

if pacman -Q system76-scheduler >/dev/null 2>&1 \
  && "${repo_root}/system76-pipewire-workaround.sh" status; then
  printf '%s\n' 'System76 Scheduler PipeWire monitoring is enabled.'
  printf '%s\n' 'On some Arch/CachyOS systems this optional helper repeatedly crashes; disabling it preserves the core scheduler and normal sound-server assignments.'
  if confirm_install 'Disable the experimental System76 PipeWire monitor?'; then
    sudo "${repo_root}/system76-pipewire-workaround.sh" disable
  fi
fi

if pacman -Q system76-scheduler >/dev/null 2>&1 \
  && ! systemctl is-active --quiet com.system76.Scheduler.service; then
  if confirm_install_default_no 'Enable and start the system-wide System76 Scheduler service now?'; then
    sudo systemctl enable --now com.system76.Scheduler.service
    printf '%s\n' 'System76 Scheduler enabled. If its helpers crash or produce repeated core dumps, disable it and use Feral GameMode.'
  fi
fi
