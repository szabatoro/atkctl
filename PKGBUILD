# Maintainer: ATK Mouse contributors

pkgname=atkctl
pkgver=0.1.0
pkgrel=1
pkgdesc="ATK A9 PRO MAX 2.0 NK mouse — battery monitor and config tool (BITMOUSE protocol)"
arch=('any')
url="https://github.com/szabatoro/atkctl"
license=('BSD')
depends=(
    'python>=3.13'
    'python-hid'
)
makedepends=(
    'python-installer'
    'python-wheel'
    'uv'
)

# ── Source ──────────────────────────────────────────────────────────────────────
# When a tag/release is published on GitHub, replace with:
#   source=("$pkgname-$pkgver.tar.gz::https://github.com/szabatoro/atkctl/archive/v$pkgver/$pkgname-$pkgver.tar.gz")
#   sha256sums=('<real_sha256>')
# For now, build from the local git checkout (run makepkg from the repo root).
source=()
noextract=()
validpgpkeys=()
sha256sums=()

prepare() {
    # Create a clean source tree from the git checkout
    git -C "$startdir" archive --format=tar.gz \
        --prefix="$pkgname-$pkgver/" \
        -o "$srcdir/$pkgname-$pkgver.tar.gz" HEAD
    cd "$srcdir"
    tar xzf "$pkgname-$pkgver.tar.gz"
}

build() {
    cd "$srcdir/$pkgname-$pkgver"
    # uv build handles the uv_build backend bundled with uv itself.
    uv build
}

check() {
    cd "$srcdir/$pkgname-$pkgver"
    # Smoke test: verify package imports and key constants
    PYTHONPATH=src python -c "
from atkctl import __version__
from atkctl.protocol import (
    BatteryStatus, POLLING_CODES, lift_off_description,
    REPORT_ID, PACKET_SIZE, SLOT_WIRED, SLOT_WIRELESS,
)
assert __version__ == '$pkgver', f'expected $pkgver, got {__version__}'
assert POLLING_CODES[0] == 1000
assert POLLING_CODES[6] == 2000
assert lift_off_description(1) == '0.7 mm  (Low)'
from atkctl.cli import main
print(f'OK atkctl {__version__} — smoke test passed')
"
}

package() {
    cd "$srcdir/$pkgname-$pkgver"

    # ── Python module + scripts ─────────────────────────────────────────────
    python -m installer --destdir="$pkgdir" dist/*.whl

    # ── udev rules — users physically at the console get ACL-based access ───
    install -Dm644 udev/99-atkctl-mouse.rules "$pkgdir/usr/lib/udev/rules.d/99-atkctl-mouse.rules"
}