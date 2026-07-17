#!/usr/bin/env bash
# NexusTrader Raspberry Pi SD Card Pre-configuration & Deployment Script
set -e

echo "=========================================================="
echo "NexusTrader Raspberry Pi SD Card Provisioner"
echo "=========================================================="

# 1. Detect SD Card Partitions
BOOT_PATH="/media/chris/boot"
ROOTFS_PATH="/media/chris/rootfs"

# Try fallback mount points (used by some file managers)
if [ ! -d "$BOOT_PATH" ]; then
    BOOT_PATH=$(find /media/chris -maxdepth 2 -name "boot*" | head -n 1)
fi
if [ ! -d "$ROOTFS_PATH" ]; then
    ROOTFS_PATH=$(find /media/chris -maxdepth 2 -name "rootfs*" | head -n 1)
fi

# If still not found, mount using udisksctl
if [ -z "$BOOT_PATH" ] || [ -z "$ROOTFS_PATH" ]; then
    echo "Scanning block devices..."
    BOOT_DEV=$(lsblk -o NAME,FSTYPE,LABEL | grep -v "nvme" | grep -E "vfat" | awk '{print $1}' | tr -d '└─├─') || true
    ROOT_DEV=$(lsblk -o NAME,FSTYPE,LABEL | grep -v "nvme" | grep -E "ext4" | awk '{print $1}' | tr -d '└─├─') || true
    
    if [ -n "$BOOT_DEV" ]; then
        echo "Mounting boot partition /dev/$BOOT_DEV..."
        udisksctl mount -b "/dev/$BOOT_DEV" || true
        BOOT_PATH="/media/chris/boot"
    fi
    if [ -n "$ROOT_DEV" ]; then
        echo "Mounting rootfs partition /dev/$ROOT_DEV..."
        udisksctl mount -b "/dev/$ROOT_DEV" || true
        ROOTFS_PATH="/media/chris/rootfs"
    fi
fi

if [ ! -d "$BOOT_PATH" ] || [ ! -d "$ROOTFS_PATH" ]; then
    echo "❌ Error: Could not locate SD card partitions."
    echo "Make sure your SD card is plugged in and recognized by the system."
    exit 1
fi

echo "✔ Detected Boot Partition at: $BOOT_PATH"
echo "✔ Detected Rootfs Partition at: $ROOTFS_PATH"

# 2. Enable SSH
echo "🔧 Enabling SSH server on Pi..."
touch "$BOOT_PATH/ssh"
touch "$BOOT_PATH/ssh.txt"

# 3. Configure Wi-Fi (NetworkManager keyfile)
echo "📶 Configuring Wi-Fi profile (Bumble Cottage Wifi)..."
mkdir -p "$BOOT_PATH/system-connections"
cat << 'EOF' > "$BOOT_PATH/system-connections/Bumble_Cottage_Wifi.nmconnection"
[connection]
id=Bumble Cottage Wifi
uuid=2ba143b2-3afc-40bd-a439-fbbf3759f46e
type=wifi
interface-name=wlan0

[wifi]
mode=infrastructure
ssid=Bumble Cottage Wifi

[wifi-security]
auth-alg=open
key-mgmt=wpa-psk
psk=12341234

[ipv4]
method=auto

[ipv6]
method=auto
addr-gen-mode=default-or-eui64
EOF

# 4. Copy Codebase to Pi User Folder
PI_HOME="$ROOTFS_PATH/home/pi"
if [ ! -d "$PI_HOME" ]; then
    # Some Pi OS configurations use a custom user instead of 'pi'
    PI_HOME=$(find "$ROOTFS_PATH/home" -maxdepth 1 -mindepth 1 -type d | head -n 1)
fi

if [ -z "$PI_HOME" ] || [ ! -d "$PI_HOME" ]; then
    echo "❌ Error: Could not locate user home directory on rootfs."
    exit 1
fi

USER_NAME=$(basename "$PI_HOME")
echo "✔ Copying bot codebase to user '$USER_NAME' home directory..."
rsync -av --exclude=".git" --exclude="__pycache__" --exclude="*.db" --exclude="*.log" /home/chris/nexustrader/ "$PI_HOME/nexustrader/"

# 5. Provision GitHub SSH Keys & Identity
echo "🔑 Copying SSH keys for GitHub pushes..."
mkdir -p "$PI_HOME/.ssh"
cp /home/chris/.ssh/id_ed25519* "$PI_HOME/.ssh/"
cat /home/chris/.ssh/id_ed25519.pub >> "$PI_HOME/.ssh/authorized_keys"
cp /home/chris/.gitconfig "$PI_HOME/" || true

# Set correct owner & permissions (matches local laptop uid/gid 1000)
chmod 700 "$PI_HOME/.ssh"
chmod 600 "$PI_HOME/.ssh/id_ed25519"
chmod 644 "$PI_HOME/.ssh/id_ed25519.pub"
chmod 600 "$PI_HOME/.ssh/authorized_keys"

# 6. Configure Autostart Systemd Service
echo "⚙ Configured autostart service..."
mkdir -p "$PI_HOME/.config/systemd/user/default.target.wants"
cat << EOF > "$PI_HOME/.config/systemd/user/nexustrader.service"
[Unit]
Description=NexusTrader Algorithmic Trading Bot Daemon
After=network.target

[Service]
Type=simple
WorkingDirectory=/home/$USER_NAME/nexustrader
ExecStart=/usr/bin/python3 main.py --headless
Restart=always
RestartSec=5
Environment=PATH=/usr/bin:/usr/local/bin

[Install]
WantedBy=default.target
EOF

ln -sf ../nexustrader.service "$PI_HOME/.config/systemd/user/default.target.wants/nexustrader.service"

# Sync and Unmount
echo "💾 Syncing file buffers..."
sync

echo "🔌 Safely unmounting partitions..."
udisksctl unmount -b /dev/mmcblk0p1 || true
udisksctl unmount -b /dev/mmcblk0p2 || true

echo "=========================================================="
echo "🎉 SD Card Configured Successfully!"
echo "You can now insert it into the Pi and power it on."
echo "=========================================================="
