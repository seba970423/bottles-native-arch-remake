# Maintainer: Sebastian George

pkgname=bottles-native-arch
_pkgname=Bottles
pkgver=67.4
pkgrel=12
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
  'gamescope: per-game compositor, upscaling, resolution and FPS controls'
  'imagemagick: icon/image conversion'
  'mangohud: performance overlay, including mangoapp for Gamescope'
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
  test-display-backend.py
  system76-pipewire-workaround.sh
)
sha256sums=(
  'eb417e37851921565664c9dbe2713f94e643f0963d3c6c89afc4cf2bcd7aff3c'
  '63c4c545a98a2567d89222aec5a9ed5536c39b4d7ad7051c621cf76bc66f0bfe'
  '73d927e370bef906fd10086287348f8d7dd89d01a1cfdf6b20cfaf739f6083ab'
  '123891cdd3fc73f01d614c0a9d202d5a8057fe3c9e92ab0cbbc5df427c8a1211'
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
