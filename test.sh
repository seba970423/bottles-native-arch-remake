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

if command -v makepkg >/dev/null 2>&1; then
  cd "${repo_root}"
  makepkg --verifysource
  makepkg --printsrcinfo > .SRCINFO
else
  printf '%s\n' 'makepkg not found; skipped PKGBUILD source verification and .SRCINFO generation.'
fi

printf '%s\n' 'Static checks passed.'
