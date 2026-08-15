#!/usr/bin/env bash
set -euo pipefail

generation=previous
assume_yes=false
for argument in "$@"; do
  case ${argument} in
    --known-good) generation=known-good ;;
    --yes) assume_yes=true ;;
    *)
      printf 'Usage: %s [--known-good] [--yes]\n' "${0##*/}" >&2
      exit 2
      ;;
  esac
done

state_root=${XDG_STATE_HOME:-"${HOME}/.local/state"}/bottles-native-arch
checkpoint="${state_root}/${generation}"
package="${checkpoint}/package.pkg.tar.zst"

if [[ ! -f ${package} || ! -f ${checkpoint}/sha256 || ! -f ${checkpoint}/version ]]; then
  printf 'No complete %s checkpoint is available.\n' "${generation}" >&2
  exit 1
fi

expected=$(<"${checkpoint}/sha256")
actual=$(sha256sum "${package}")
actual=${actual%% *}
if [[ ${actual} != "${expected}" ]]; then
  printf 'Refusing rollback: %s package checksum does not match.\n' "${generation}" >&2
  exit 1
fi

version=$(<"${checkpoint}/version")
if ! ${assume_yes}; then
  read -r -p "Install ${generation} bottles-native-arch ${version}? [y/N] " reply
  if [[ ${reply} != [Yy] && ${reply} != [Yy][Ee][Ss] ]]; then
    printf '%s\n' 'Rollback cancelled.'
    exit 1
  fi
fi

printf 'Installing %s checkpoint: %s\n' "${generation}" "${version}"
sudo pacman -U "${package}"
