#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 2 ]]; then
  printf 'Usage: %s PACKAGE VERSION\n' "${0##*/}" >&2
  exit 2
fi

package=$1
version=$2
state_root=${XDG_STATE_HOME:-"${HOME}/.local/state"}/bottles-native-arch
known_good="${state_root}/known-good"
previous="${state_root}/previous"

if [[ ! -f ${package} ]]; then
  printf 'Cannot checkpoint missing package: %s\n' "${package}" >&2
  exit 1
fi

mkdir -p "${state_root}"
stage=$(mktemp -d "${state_root}/.checkpoint.XXXXXX")
cleanup() {
  [[ ! -d ${stage} ]] || rm -rf -- "${stage}"
}
trap cleanup EXIT

cp -- "${package}" "${stage}/package.pkg.tar.zst"
sha256sum "${stage}/package.pkg.tar.zst" | cut -d ' ' -f 1 > "${stage}/sha256"
printf '%s\n' "${version}" > "${stage}/version"

if [[ -d ${known_good} ]]; then
  rm -rf -- "${previous}"
  mv -- "${known_good}" "${previous}"
fi
mv -- "${stage}" "${known_good}"
trap - EXIT

printf 'Marked bottles-native-arch %s as known good.\n' "${version}"
if [[ -d ${previous} ]]; then
  printf '%s\n' 'The preceding known-good package remains available as the previous generation.'
fi
