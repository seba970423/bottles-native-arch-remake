#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
pkgbuild="${repo_root}/PKGBUILD"
api_url='https://api.github.com/repos/bottlesdevs/Bottles/releases/latest'

for command_name in curl python3 sha256sum; do
  if ! command -v "${command_name}" >/dev/null 2>&1; then
    printf 'Missing required command: %s\n' "${command_name}" >&2
    exit 1
  fi
done

latest_version=$(
  curl --fail --location --silent --show-error --retry 3 "${api_url}" |
    python3 -c 'import json,sys; print(json.load(sys.stdin)["tag_name"])'
)

if [[ ! ${latest_version} =~ ^[0-9]+([.][0-9]+)*$ ]]; then
  printf 'Refusing unexpected upstream version: %s\n' "${latest_version}" >&2
  exit 1
fi

current_version=$(sed -n 's/^pkgver=//p' "${pkgbuild}")
if [[ ${current_version} == "${latest_version}" ]]; then
  printf 'Already tracking latest Bottles release: %s\n' "${latest_version}"
  exit 0
fi

archive=$(mktemp --suffix=.tar.gz)
trap 'rm -f -- "${archive}"' EXIT
archive_url="https://github.com/bottlesdevs/Bottles/archive/refs/tags/${latest_version}.tar.gz"

printf 'Downloading Bottles %s...\n' "${latest_version}"
curl --fail --location --show-error --retry 3 --output "${archive}" "${archive_url}"
archive_sha256=$(sha256sum "${archive}")
archive_sha256=${archive_sha256%% *}

sed -i \
  -e "s/^pkgver=.*/pkgver=${latest_version}/" \
  -e 's/^pkgrel=.*/pkgrel=1/' \
  "${pkgbuild}"

python3 - "${pkgbuild}" "${archive_sha256}" <<'PY'
from pathlib import Path
import re
import sys

path = Path(sys.argv[1])
checksum = sys.argv[2]
text = path.read_text()
text, count = re.subn(
    r"(sha256sums=\(\n\s*)'[^']+'",
    rf"\1'{checksum}'",
    text,
    count=1,
)
if count != 1:
    raise SystemExit("Could not update the source checksum in PKGBUILD")
path.write_text(text)
PY

printf 'Updated PKGBUILD: Bottles %s -> %s\n' "${current_version}" "${latest_version}"
printf '%s\n' 'Run ./test.sh before committing the update; patches may need refreshing.'
