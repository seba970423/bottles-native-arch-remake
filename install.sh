#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
update=true
state_root=${XDG_STATE_HOME:-"${HOME}/.local/state"}/bottles-native-arch
pkgbuild_backup=$(mktemp)
cp -- "${repo_root}/PKGBUILD" "${pkgbuild_backup}"
keep_pkgbuild=false

cleanup() {
  if ! ${keep_pkgbuild}; then
    cp -- "${pkgbuild_backup}" "${repo_root}/PKGBUILD"
  fi
  rm -f -- "${pkgbuild_backup}"
}
trap cleanup EXIT

if [[ ${1:-} == '--no-update' ]]; then
  update=false
elif [[ $# -gt 0 ]]; then
  printf 'Usage: %s [--no-update]\n' "${0##*/}" >&2
  exit 2
fi

if [[ ${EUID} -eq 0 ]]; then
  printf '%s\n' 'Do not run this script as root; makepkg will request sudo only for installation.' >&2
  exit 1
fi

if [[ ! -r /etc/arch-release ]] || ! command -v makepkg >/dev/null 2>&1; then
  printf '%s\n' 'This installer requires Arch Linux or an Arch-based distribution with makepkg.' >&2
  exit 1
fi

expected_version=$(bash -c '
  source "$1"
  if [[ -n ${epoch:-} ]]; then
    printf "%s:%s-%s" "$epoch" "$pkgver" "$pkgrel"
  else
    printf "%s-%s" "$pkgver" "$pkgrel"
  fi
' _ "${repo_root}/PKGBUILD")
printf 'Preparing Bottles Native package %s\n' "${expected_version}"

if ${update}; then
  "${repo_root}/update.sh"
fi

"${repo_root}/test.sh"
"${repo_root}/install-dependencies.sh"
cd "${repo_root}"
makepkg --clean --force

mapfile -t package_files < <(makepkg --packagelist)
if (( ${#package_files[@]} != 1 )) || [[ ! -f ${package_files[0]} ]]; then
  printf '%s\n' 'Could not identify the newly built package.' >&2
  exit 1
fi
candidate=${package_files[0]}

sudo pacman -U --needed "${candidate}"

installed_version=$(pacman -Q bottles-native-arch 2>/dev/null | awk '{print $2}')
if [[ ${installed_version} != "${expected_version}" ]]; then
  printf 'Installation verification failed: expected %s, found %s.\n' \
    "${expected_version}" "${installed_version:-not installed}" >&2
  exit 1
fi
printf 'Verified installed package: bottles-native-arch %s\n' "${installed_version}"

printf '\n%s\n' 'Candidate installed. Close Bottles before answering the validation question.'
read -r -p 'Launch Bottles now for testing? [Y/n] ' launch_reply
if [[ -z ${launch_reply} || ${launch_reply} == [Yy] || ${launch_reply} == [Yy][Ee][Ss] ]]; then
  bottles >/tmp/bottles-native-arch-validation.log 2>&1 &
  disown || true
  printf '%s\n' 'Bottles launched. Test the window, then close it before continuing here.'
fi

read -r -p 'Did this Bottles version launch and work correctly? [y/N] ' good_reply
if [[ ${good_reply} == [Yy] || ${good_reply} == [Yy][Ee][Ss] ]]; then
  keep_pkgbuild=true
  "${repo_root}/mark-known-good.sh" "${candidate}" "${installed_version}"
  printf '%s\n' 'Update completed and recorded as known good.'
  exit 0
fi

if [[ -d ${state_root}/known-good ]]; then
  printf '%s\n' 'Candidate rejected. Restoring the last known-good package...'
  "${repo_root}/rollback.sh" --known-good --yes
  printf '%s\n' 'The rejected update was rolled back.'
  exit 1
fi

keep_pkgbuild=true
printf '%s\n' 'Candidate was not approved, but no older checkpoint exists yet.' >&2
printf '%s\n' 'The installed package was left in place; rerun after verifying it to establish a checkpoint.' >&2
exit 1
