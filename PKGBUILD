# Maintainer: Sebastian George

pkgname=bottles-native-arch
_pkgname=Bottles
pkgver=66.6
pkgrel=13
epoch=2
pkgdesc='Latest upstream Bottles, packaged natively for Arch Linux'
arch=(any)
url='https://github.com/bottlesdevs/Bottles'
license=(GPL-3.0-only)
provides=("bottles=${pkgver}")
conflicts=(bottles)
depends=(
  fvs2
  gtk4
  gtksourceview5
  hicolor-icon-theme
  icoextract
  libadwaita
  libportal-gtk4
  patool
  python
  python-cairo
  python-certifi
  python-chardet
  python-charset-normalizer
  python-gobject
  python-idna
  python-markdown
  python-orjson
  python-pathvalidate
  python-pefile
  python-pycurl
  python-pysocks
  python-requests
  python-urllib3
  python-yaml
  python-yara
  umu-launcher
  vkbasalt-cli
)
makedepends=(
  appstream-glib
  blueprint-compiler
  desktop-file-utils
  gettext
  glib2-devel
  gobject-introspection
  meson
  ninja
)
optdepends=(
  'gamemode: launch games with temporary Feral GameMode optimizations'
  'gamescope: gamescope session integration'
  'imagemagick: icon/image conversion'
  'mangohud: performance overlay'
  'system76-scheduler: experimental foreground scheduling backend for UMU games'
  'vmtouch: preload bottle files into memory'
  'vulkan-tools: vkcube test and Vulkan information'
  'xorg-xdpyinfo: display information detection'
  'xterm: fallback terminal for Run executable in terminal'
)
source=(
  "${_pkgname}-${pkgver}.tar.gz::https://github.com/bottlesdevs/Bottles/archive/refs/tags/${pkgver}.tar.gz"
  native-arch.patch
  verify-source.sh
  system76-pipewire-workaround.sh
)
sha256sums=(
  'f6f9ed5c414307bf55ce534f2e3c25fc36625b323b4b7887e08c0182a12861ce'
  'bfa3e1cad94b791a8ba9facd7ba08b198368e6c3384a0c94f13e895f4d8cb744'
  '231aa8c036517984f4d67832b961e700bc35516ddc1baecdfbf34c877176119b'
  'df33a555ec11517841667948c8f2702719bd5d3887ee012efd73703661235d2a'
)

prepare() {
  cd "${srcdir}/${_pkgname}-${pkgver}"
  patch --forward --strip=1 --input="${srcdir}/native-arch.patch"
  "${srcdir}/verify-source.sh" .
}

build() {
  cd "${srcdir}/${_pkgname}-${pkgver}"
  arch-meson build
  meson compile -C build
}

check() {
  cd "${srcdir}/${_pkgname}-${pkgver}"
  # Upstream's remote screenshots and release-description formatting fail
  # newer appstream-util style checks. They do not affect the native build.
  meson test -C build --print-errorlogs \
    'bottles:Validate desktop file' \
    'bottles:Validate schema file'
}

package() {
  cd "${srcdir}/${_pkgname}-${pkgver}"
  meson install -C build --destdir "${pkgdir}"
  install -Dm755 "${srcdir}/system76-pipewire-workaround.sh" \
    "${pkgdir}/usr/lib/bottles-native-arch/system76-pipewire-workaround"
}

# vim: set ft=sh ts=2 sw=2 et:
