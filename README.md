# Vista Linux

```
 __     ___     _          _     _
 \ \   / (_)___| |_ __ _  | |   (_)_ __  _   ___  _
  \ \ / /| / __| __/ _` | | |   | | '_ \| | | \ \/ /
   \ V / | \__ \ || (_| | | |___| | | | | |_| |>  <
    \_/  |_|___/\__\__,_| |_____|_|_| |_|\__,_/_/\_\
```

**A Debian Sid rolling-release distro powered by the [Vista](https://github.com/whyfle/vista) package manager.**

Vista Linux is an Arch-style rolling release built on Debian unstable (sid). It replaces `apt` with the **Vista universal package manager** and ships with a pre-configured **GNOME desktop** and **Dash to Dock**.

---

## Features

| Feature | Details |
|---------|---------|
| **Base** | Debian Sid (unstable) — rolling release |
| **Package Manager** | [Vista](https://github.com/whyfle/vista) (Rust, wraps APT/DNF/Pacman/Flatpak) |
| **Desktop Options** | Choice in installer: **GNOME** (Dash to Dock) or **KDE Plasma** (custom pure-black `#000000` OLED theme) |
| **Installer** | Custom curses TUI installer (like `archinstall`) |
| **Fetch Tool** | Custom **Vista neofetch** (`vista-fetch` / `neofetch`) with ASCII logo and hardware detection |
| **Boot Splash** | Custom Plymouth boot splash with Vista eye logo on pure OLED black + matching GRUB background |
| **Bootloader** | GRUB (EFI + Legacy BIOS, compatible with Apple Mac EFI) |
| **Hybrid GPU & Mac** | NVIDIA PRIME offload (`prime-run`), dynamic power management, Broadcom Wi-Fi (`b43`/`wl`), `macfanctld` for iMacs |
| **apt Compatibility** | `apt`/`apt-get` are wrapped — they suggest Vista but still allow passthrough |



---

## Project Structure

```
vista-linux/
├── build.sh                                  # Main build script
├── branding/
│   ├── os-release                            # /etc/os-release
│   ├── issue                                 # Login banner
│   ├── motd                                  # Message of the day
│   └── vista-ascii.txt                       # ASCII logo
├── config/
│   ├── auto/config                           # live-build lb config
│   ├── package-lists/
│   │   └── vista.list.chroot                 # Packages to install
│   ├── hooks/live/
│   │   ├── 0100-install-vista.hook.chroot    # Build & install Vista from source
│   │   ├── 0200-replace-apt.hook.chroot      # Wrap apt → Vista
│   │   └── 0300-configure-gnome.hook.chroot  # GNOME + Dash to Dock config
│   └── includes.chroot/
│       ├── etc/skel/.bashrc                  # Default user shell config
│       └── usr/share/applications/
│           └── vista-installer.desktop       # Desktop shortcut
├── installer/
│   └── vista-installer.py                    # TUI installer (Python curses)
└── README.md
```

---

## Prerequisites

You need a **Debian or Ubuntu** host system with:

```bash
sudo apt update
sudo apt install -y live-build debootstrap git
```

> [!NOTE]
> The build must be run on an x86_64 Linux system. It will not work from WSL or Windows directly.
> Use a Debian VM or bare-metal machine.

---

## How to Build the ISO

```bash
# Clone or copy this project to your build machine
cd vista-linux

# Build (takes 15-30+ minutes depending on internet speed)
sudo ./build.sh
```

The output will be `vista-linux-YYYYMMDD-amd64.iso` in the project root.

---

## Testing in a VM

### QEMU/KVM (recommended)

```bash
# Create a test disk
qemu-img create -f qcow2 vista-test.qcow2 30G

# Boot with EFI
qemu-system-x86_64 \
    -m 4G \
    -enable-kvm \
    -cpu host \
    -smp 4 \
    -bios /usr/share/ovmf/OVMF.fd \
    -drive file=vista-test.qcow2,format=qcow2 \
    -cdrom vista-linux-*.iso \
    -boot d \
    -vga virtio \
    -display gtk
```

### VirtualBox

1. Create a new VM (Debian 64-bit, 4GB RAM, 30GB disk)
2. Enable EFI in Settings → System
3. Attach the ISO as a CD
4. Boot and run the installer

---

## Using the Installer

When you boot the live ISO, you can launch the installer in two ways:

1. **Desktop icon** — click "Install Vista Linux" on the GNOME desktop
2. **Terminal** — run `sudo vista-installer`

The installer walks you through:
1. Keyboard layout selection
2. Timezone selection
3. Disk selection (WARNING: erases entire disk!)
4. Partition scheme preview (EFI or BIOS auto-detected)
5. User account setup (username, password, hostname)
6. Summary & confirmation
7. Automated installation with progress
8. Reboot

---

## How `apt` Replacement Works

Vista Linux does **not** delete `apt` — it wraps it. The real binaries are kept as `apt.real` and `apt-get.real` so Vista can use them as a backend.

When a user types `apt install something`:

```
╔══════════════════════════════════════════════════════════════╗
║  Vista Linux uses vista as its package manager.              ║
╚══════════════════════════════════════════════════════════════╝

  Try:  vista install <package>

Run the original apt command anyway? [y/N]
```

This way nothing breaks, but users are trained to use `vista`.

---

## Vista Package Manager Quick Reference

```bash
vista search <query>           # Search packages
vista install <package>        # Install a package
vista remove <package>         # Remove a package
vista sys-info                 # Show system info
vista install pkg --dry-run    # Preview without installing
```

Shell aliases in `.bashrc`:
- `vi` → `vista install`
- `vs` → `vista search`
- `vr` → `vista remove`
- `vu` → `vista update`
- `vinfo` → `vista sys-info`

---

## Customisation

### Change the wallpaper
Place a wallpaper at `config/includes.chroot/usr/share/backgrounds/vista-wallpaper.png` and update the dconf key in the GNOME hook.

### Add more packages
Edit `config/package-lists/vista.list.chroot` — one package per line.

### Change Dash to Dock position
Edit the `dock-position` value in `config/hooks/live/0300-configure-gnome.hook.chroot`. Options: `'TOP'`, `'BOTTOM'`, `'LEFT'`, `'RIGHT'`.

---

## License

This build system is provided as-is. Vista package manager is © [whyfle](https://github.com/whyfle/vista). Debian components are under their respective licenses.
