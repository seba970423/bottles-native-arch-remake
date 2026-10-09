#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)

for script in \
  install.sh install-dependencies.sh mark-known-good.sh rollback.sh uninstall.sh \
  system76-pipewire-workaround.sh update.sh test.sh verify-source.sh; do
  bash -n "${repo_root}/${script}"
done

if command -v shellcheck >/dev/null 2>&1; then
  shellcheck "${repo_root}"/*.sh
fi

# Optional explicit patched-source path for non-Arch development environments.
if [[ $# -gt 0 ]]; then
  "${repo_root}/verify-source.sh" "$1"
fi

if command -v makepkg >/dev/null 2>&1; then
  cd "${repo_root}"
  makepkg --verifysource
  # --nobuild downloads/extracts sources and runs prepare(), which is where
  # native-arch.patch and verify-source.sh are exercised. --nodeps keeps this
  # preflight independent from runtime/build dependency installation.
  makepkg --nobuild --nodeps --cleanbuild
  makepkg --printsrcinfo > .SRCINFO
else
  printf '%s\n' 'makepkg not found; skipped PKGBUILD source verification and .SRCINFO generation.'
fi

printf '%s\n' 'Static checks passed.'
