#!/bin/bash
set -euo pipefail

DISTRO_NAME="Vista Linux"
ISO_LABEL="VISTA_LIVE"
BUILD_DIR="$(cd "$(dirname "$0")" && pwd)"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log()  { echo -e "${GREEN}[VISTA]${NC} $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC}  $*"; }
die()  { echo -e "${RED}[ERROR]${NC} $*" >&2; exit 1; }

# ------------------------------------------------------------------
# Preflight checks
# ------------------------------------------------------------------
if [ "$EUID" -ne 0 ]; then
    die "This script must be run as root. Try: sudo $0"
fi

for dep in lb debootstrap git; do
    command -v "$dep" >/dev/null 2>&1 || die "'$dep' not found. Install with: apt install live-build debootstrap git"
done

log "Building ${DISTRO_NAME} ISO …"
cd "$BUILD_DIR"

# ------------------------------------------------------------------
# Clean any previous build
# ------------------------------------------------------------------
if [ -d ".build" ] || [ -f ".build/config" ]; then
    log "Cleaning previous build artefacts …"
    lb clean --purge 2>/dev/null || true
fi

# ------------------------------------------------------------------
# Copy branding into the chroot overlay
# ------------------------------------------------------------------
log "Installing branding files …"
mkdir -p config/includes.chroot/etc
cp branding/os-release config/includes.chroot/etc/os-release
cp branding/issue       config/includes.chroot/etc/issue
cp branding/motd        config/includes.chroot/etc/motd

# ------------------------------------------------------------------
# Copy the TUI installer & fetch utility
# ------------------------------------------------------------------
log "Installing vista-installer and custom neofetch …"
mkdir -p config/includes.chroot/usr/local/bin
cp installer/vista-installer.py config/includes.chroot/usr/local/bin/vista-installer
chmod +x config/includes.chroot/usr/local/bin/vista-installer
chmod +x config/includes.chroot/usr/local/bin/vista-installer-launcher 2>/dev/null || true
chmod +x config/includes.chroot/usr/local/bin/neofetch
ln -sf neofetch config/includes.chroot/usr/local/bin/vista-fetch

# ------------------------------------------------------------------
# Copy the ASCII banner & boot theme assets for the installer & Plymouth
# ------------------------------------------------------------------
mkdir -p config/includes.chroot/usr/share/vista/plymouth
cp branding/vista-ascii.txt config/includes.chroot/usr/share/vista/vista-ascii.txt
cp branding/plymouth/* config/includes.chroot/usr/share/vista/plymouth/ 2>/dev/null || true

# Copy GRUB splash
mkdir -p config/includes.chroot/boot/grub
cp branding/grub-splash.png config/includes.chroot/boot/grub/grub-splash.png 2>/dev/null || true


log "Running lb config …"
lb config --distribution noble --architecture amd64 --archive-areas "main restricted universe multiverse" --binary-images iso-hybrid --iso-application "Vista Linux Live" --iso-publisher "Vista Linux" --iso-volume "VISTA_LIVE" --bootappend-live "boot=live components quiet splash plymouth.ignore-serial-consoles vt.handoff=7" --linux-packages "linux-image"

# ------------------------------------------------------------------
# Build
# ------------------------------------------------------------------
log "Starting ISO build (this will take a while) …"
lb build 2>&1 | tee build.log

# ------------------------------------------------------------------
# Rename the output ISO
# ------------------------------------------------------------------
shopt -s nullglob
for iso in live-image-*.hybrid.iso; do
    mv "$iso" "vista-linux-$(date +%Y%m%d)-amd64.iso"
    break
done

log "Build complete! ISO is in ${BUILD_DIR}/"
ls -lh "$BUILD_DIR"/vista-linux-*.iso 2>/dev/null || true
