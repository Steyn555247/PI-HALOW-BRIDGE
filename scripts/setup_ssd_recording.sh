#!/bin/bash
#
# Setup script for SSD recording on Serpent Base Pi
#
# This script:
# 1. Verifies SSD is mounted
# 2. Creates the recording directory structure
# 3. Creates a desktop symlink for easy access
# 4. Sets permissions
# 5. Tests write access
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
SSD_MOUNT="/media/serpentbase/SSK SSD"
RECORDINGS_DIR="$SSD_MOUNT/serpent_recordings"
DESKTOP_DIR="/home/serpentbase/Desktop"
SYMLINK_NAME="SerpentRecordings"

echo "=================================================="
echo "  Serpent SSD Recording Setup"
echo "=================================================="
echo ""

# Step 1: Verify SSD is mounted
echo -n "Checking SSD mount... "
if [ -d "$SSD_MOUNT" ]; then
    # Check if it's actually mounted (not just an empty directory)
    if mountpoint -q "$SSD_MOUNT" 2>/dev/null || [ "$(ls -A "$SSD_MOUNT" 2>/dev/null)" ]; then
        echo -e "${GREEN}OK${NC}"

        # Show disk space
        DISK_SPACE=$(df -h "$SSD_MOUNT" 2>/dev/null | tail -1 | awk '{print $4 " available of " $2}')
        echo "  Disk space: $DISK_SPACE"
    else
        echo -e "${RED}FAILED${NC}"
        echo "  Error: SSD mount point exists but appears empty"
        echo "  Please ensure the SSD is connected and mounted"
        exit 1
    fi
else
    echo -e "${RED}FAILED${NC}"
    echo "  Error: SSD not found at $SSD_MOUNT"
    echo "  Please connect and mount the SSD first"
    exit 1
fi

# Step 2: Create directory structure
echo ""
echo "Creating directory structure..."

for subdir in telemetry video commands; do
    dir_path="$RECORDINGS_DIR/$subdir"
    echo -n "  Creating $subdir... "
    if mkdir -p "$dir_path" 2>/dev/null; then
        echo -e "${GREEN}OK${NC}"
    else
        echo -e "${RED}FAILED${NC}"
        echo "  Error: Could not create $dir_path"
        exit 1
    fi
done

# Step 3: Set permissions (ensure serpentbase user owns the directories)
echo ""
echo -n "Setting permissions... "
if chown -R serpentbase:serpentbase "$RECORDINGS_DIR" 2>/dev/null || true; then
    chmod -R 755 "$RECORDINGS_DIR" 2>/dev/null || true
    echo -e "${GREEN}OK${NC}"
else
    echo -e "${YELLOW}WARNING${NC} (may need sudo)"
fi

# Step 4: Create desktop symlink
echo ""
echo -n "Creating desktop symlink... "
if [ -d "$DESKTOP_DIR" ]; then
    # Remove existing symlink if present
    if [ -L "$DESKTOP_DIR/$SYMLINK_NAME" ]; then
        rm "$DESKTOP_DIR/$SYMLINK_NAME"
    fi

    if ln -s "$RECORDINGS_DIR" "$DESKTOP_DIR/$SYMLINK_NAME" 2>/dev/null; then
        echo -e "${GREEN}OK${NC}"
        echo "  Symlink: $DESKTOP_DIR/$SYMLINK_NAME -> $RECORDINGS_DIR"
    else
        echo -e "${YELLOW}WARNING${NC}"
        echo "  Could not create symlink (non-critical)"
    fi
else
    echo -e "${YELLOW}SKIPPED${NC}"
    echo "  Desktop directory not found (non-critical)"
fi

# Step 5: Test write access
echo ""
echo "Testing write access..."

test_success=true
for subdir in telemetry video commands; do
    dir_path="$RECORDINGS_DIR/$subdir"
    test_file="$dir_path/.write_test_$$"
    echo -n "  Testing $subdir... "

    if touch "$test_file" 2>/dev/null && rm "$test_file" 2>/dev/null; then
        echo -e "${GREEN}OK${NC}"
    else
        echo -e "${RED}FAILED${NC}"
        test_success=false
    fi
done

# Summary
echo ""
echo "=================================================="
if [ "$test_success" = true ]; then
    echo -e "${GREEN}Setup completed successfully!${NC}"
    echo ""
    echo "Recording directories:"
    echo "  Telemetry: $RECORDINGS_DIR/telemetry"
    echo "  Video:     $RECORDINGS_DIR/video"
    echo "  Commands:  $RECORDINGS_DIR/commands"
    echo ""
    echo "Desktop shortcut: $DESKTOP_DIR/$SYMLINK_NAME"
    echo ""
    echo "To start recording, restart the bridge service:"
    echo "  sudo systemctl restart serpent-base-bridge"
    echo ""
else
    echo -e "${RED}Setup completed with errors${NC}"
    echo "Please check permissions and try again"
    exit 1
fi
echo "=================================================="
