#!/bin/bash
#
# Update Script for Refactored PI-HALOW-BRIDGE
#
# This script safely updates an existing installation to the refactored
# modular architecture (backup/refactor-complete-2026-02-06 branch).
#
# Usage:
#   ./scripts/update_to_refactored.sh [robot|base]
#
# Safety features:
#   - Creates backup branch before updating
#   - Updates dependencies
#   - Fixes service configuration
#   - Provides rollback instructions
#
# Requirements:
#   - Existing PI-HALOW-BRIDGE installation
#   - Git repository initialized
#   - Internet connection to GitHub
#

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_step() {
    echo -e "${BLUE}[STEP]${NC} $1"
}

# Parse arguments
DEVICE_TYPE=$1
if [ -z "$DEVICE_TYPE" ]; then
    log_error "Device type not specified"
    echo "Usage: $0 [robot|base]"
    echo ""
    echo "Examples:"
    echo "  $0 robot    # Update Robot Pi"
    echo "  $0 base     # Update Base Pi"
    exit 1
fi

if [ "$DEVICE_TYPE" != "robot" ] && [ "$DEVICE_TYPE" != "base" ]; then
    log_error "Invalid device type: $DEVICE_TYPE"
    echo "Must be 'robot' or 'base'"
    exit 1
fi

echo "============================================================"
echo "  PI-HALOW-BRIDGE Update to Refactored Architecture"
echo "  Device Type: ${DEVICE_TYPE^^}"
echo "============================================================"
echo ""

# Verify we're in the correct directory
if [ ! -d "robot_pi" ] || [ ! -d "base_pi" ] || [ ! -d "common" ]; then
    log_error "Not in PI-HALOW-BRIDGE directory"
    echo "Please run this script from the project root:"
    echo "  cd /path/to/PI-HALOW-BRIDGE"
    echo "  ./scripts/update_to_refactored.sh $DEVICE_TYPE"
    exit 1
fi

PROJECT_ROOT=$(pwd)
log_info "Project root: $PROJECT_ROOT"

# Determine service name
if [ "$DEVICE_TYPE" == "robot" ]; then
    SERVICE_NAME="serpent-robot-bridge"
    SERVICE_FILE="robot_pi/serpent-robot-bridge.service"
    REQUIREMENTS="robot_pi/requirements.txt"
else
    SERVICE_NAME="serpent-base-bridge"
    SERVICE_FILE="base_pi/serpent-base-bridge.service"
    REQUIREMENTS="base_pi/requirements.txt"
fi

log_info "Service: $SERVICE_NAME"
echo ""

# ============================================================
# STEP 1: Check Current State
# ============================================================
log_step "Step 1: Checking current state..."

# Check if service exists
if systemctl list-unit-files | grep -q "^$SERVICE_NAME.service"; then
    log_info "Service $SERVICE_NAME found"

    if systemctl is-active --quiet $SERVICE_NAME; then
        log_info "Service is running"
        RESTART_NEEDED=true
        INITIAL_STATUS="running"
    else
        log_warn "Service is not running"
        RESTART_NEEDED=false
        INITIAL_STATUS="stopped"
    fi
else
    log_warn "Service $SERVICE_NAME not installed"
    RESTART_NEEDED=false
    INITIAL_STATUS="not_installed"
fi

# Check git status
if ! git rev-parse --git-dir > /dev/null 2>&1; then
    log_error "Not a git repository"
    exit 1
fi

CURRENT_BRANCH=$(git branch --show-current)
log_info "Current branch: $CURRENT_BRANCH"

# Check for uncommitted changes
if ! git diff-index --quiet HEAD -- 2>/dev/null; then
    log_warn "You have uncommitted changes"
    git status --short
    echo ""
    read -p "Continue anyway? [y/N] " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log_info "Update cancelled"
        exit 0
    fi
fi

echo ""

# ============================================================
# STEP 2: Create Backup
# ============================================================
log_step "Step 2: Creating backup branch..."

BACKUP_BRANCH="backup-before-update-$(date +%Y%m%d-%H%M%S)"
log_info "Backup branch: $BACKUP_BRANCH"

# Save current state
git add -A 2>/dev/null || true
git commit -m "Backup before updating to refactored version" 2>/dev/null || log_info "No changes to commit"

# Create backup branch
if git checkout -b $BACKUP_BRANCH 2>/dev/null; then
    log_info "✓ Backup branch created"
else
    log_info "✓ Already on backup branch or branch exists"
fi

echo ""

# ============================================================
# STEP 3: Fetch and Switch to Refactored Branch
# ============================================================
log_step "Step 3: Fetching refactored code from GitHub..."

log_info "Fetching from origin..."
git fetch origin

log_info "Switching to backup/refactor-complete-2026-02-06..."
if git checkout backup/refactor-complete-2026-02-06; then
    log_info "✓ Switched to refactored branch"
else
    log_error "Failed to checkout refactored branch"
    log_info "Attempting to create tracking branch..."
    git checkout -b backup/refactor-complete-2026-02-06 origin/backup/refactor-complete-2026-02-06
fi

log_info "Pulling latest changes..."
git pull origin backup/refactor-complete-2026-02-06 || log_warn "Already up to date"

echo ""
log_info "Code updated to refactored version"
log_info "Latest commit: $(git log -1 --oneline)"
echo ""

# ============================================================
# STEP 4: Update Dependencies
# ============================================================
log_step "Step 4: Updating Python dependencies..."

if [ ! -d "venv" ]; then
    log_error "Virtual environment not found at $PROJECT_ROOT/venv"
    log_info "Run: python3 -m venv venv"
    log_info "Then run this script again"
    exit 1
fi

log_info "Activating virtual environment..."
source venv/bin/activate

log_info "Upgrading pip..."
pip install --upgrade pip -q

log_info "Installing/upgrading dependencies from $REQUIREMENTS..."
pip install -r $REQUIREMENTS --upgrade

deactivate
log_info "✓ Dependencies updated"
echo ""

# ============================================================
# STEP 5: Update Service Configuration
# ============================================================
log_step "Step 5: Checking service configuration..."

# Check if service file needs WorkingDirectory update
CURRENT_WD=$(grep "^WorkingDirectory=" $SERVICE_FILE | cut -d= -f2)
log_info "Current WorkingDirectory: $CURRENT_WD"

# Robot Pi needs WorkingDirectory fix (from robot_pi subdir to project root)
if [ "$DEVICE_TYPE" == "robot" ] && [[ "$CURRENT_WD" == *"/robot_pi" ]]; then
    log_warn "WorkingDirectory needs update"
    log_info "Updating to: $PROJECT_ROOT"

    # Create temporary file with updated path
    sed "s|WorkingDirectory=.*|WorkingDirectory=$PROJECT_ROOT|g" $SERVICE_FILE > ${SERVICE_FILE}.tmp
    mv ${SERVICE_FILE}.tmp $SERVICE_FILE

    log_info "✓ Service file updated"
    SERVICE_UPDATED=true
elif [ "$DEVICE_TYPE" == "base" ]; then
    # Base Pi service file should already have correct WorkingDirectory
    # But verify it points to project root
    if [[ "$CURRENT_WD" == *"/base_pi" ]]; then
        log_warn "WorkingDirectory needs update"
        sed "s|WorkingDirectory=.*|WorkingDirectory=$PROJECT_ROOT|g" $SERVICE_FILE > ${SERVICE_FILE}.tmp
        mv ${SERVICE_FILE}.tmp $SERVICE_FILE
        log_info "✓ Service file updated"
        SERVICE_UPDATED=true
    else
        log_info "✓ Service WorkingDirectory already correct"
        SERVICE_UPDATED=false
    fi
else
    log_info "✓ Service WorkingDirectory already correct"
    SERVICE_UPDATED=false
fi

# Also update any hardcoded paths in service file to match current location
if [[ "$CURRENT_WD" != "$PROJECT_ROOT" ]]; then
    log_info "Updating all paths in service file to: $PROJECT_ROOT"
    sed -i "s|/home/[^/]*/[^/]*/PI-HALOW-BRIDGE|$PROJECT_ROOT|g" $SERVICE_FILE
fi

echo ""

# ============================================================
# STEP 6: Reinstall Service
# ============================================================
log_step "Step 6: Installing updated systemd service..."

log_info "Copying service file to /etc/systemd/system/..."
sudo cp $SERVICE_FILE /etc/systemd/system/

log_info "Reloading systemd daemon..."
sudo systemctl daemon-reload

log_info "✓ Service definition updated"
echo ""

# ============================================================
# STEP 7: Restart Service
# ============================================================
if [ "$RESTART_NEEDED" = true ]; then
    log_step "Step 7: Restarting service..."

    if [ "$DEVICE_TYPE" == "robot" ]; then
        log_warn "Robot will engage E-STOP during restart (safety feature)"
        log_warn "You will need to manually clear E-STOP after restart"
    fi

    echo ""
    read -p "Press Enter to restart $SERVICE_NAME (or Ctrl+C to cancel)..."

    log_info "Stopping $SERVICE_NAME..."
    sudo systemctl stop $SERVICE_NAME

    sleep 1

    log_info "Starting $SERVICE_NAME..."
    sudo systemctl start $SERVICE_NAME

    sleep 2

    # Check if service started successfully
    if systemctl is-active --quiet $SERVICE_NAME; then
        log_info "✓ Service restarted successfully"
    else
        log_error "Service failed to start!"
        echo ""
        log_info "Showing recent logs:"
        sudo journalctl -u $SERVICE_NAME -n 30 --no-pager
        echo ""
        log_error "Update may have failed. Check logs above."
        log_info "To rollback:"
        log_info "  git checkout $BACKUP_BRANCH"
        log_info "  sudo systemctl restart $SERVICE_NAME"
        exit 1
    fi
else
    log_warn "Service was not running, skipping restart"
    log_info "Start service with: sudo systemctl start $SERVICE_NAME"
fi

echo ""

# ============================================================
# STEP 8: Verification
# ============================================================
log_step "Step 8: Verifying installation..."

# Check Python imports
log_info "Testing Python imports..."
source venv/bin/activate
if [ "$DEVICE_TYPE" == "robot" ]; then
    if python3 -c "from robot_pi.core import bridge_coordinator" 2>/dev/null; then
        log_info "✓ robot_pi.core.bridge_coordinator imports successfully"
    else
        log_error "Failed to import robot_pi.core.bridge_coordinator"
        deactivate
        exit 1
    fi
else
    if python3 -c "from base_pi.core import bridge_coordinator" 2>/dev/null; then
        log_info "✓ base_pi.core.bridge_coordinator imports successfully"
    else
        log_error "Failed to import base_pi.core.bridge_coordinator"
        deactivate
        exit 1
    fi
fi
deactivate

# Show service status
echo ""
log_info "Service status:"
sudo systemctl status $SERVICE_NAME --no-pager -l | head -15

echo ""
echo "============================================================"
echo "  Update Complete!"
echo "============================================================"
echo ""
log_info "Summary:"
echo "  • Branch: $(git branch --show-current)"
echo "  • Service: $SERVICE_NAME"
echo "  • Status: $(systemctl is-active $SERVICE_NAME)"
echo "  • Backup: $BACKUP_BRANCH"
echo ""
echo "Next steps:"
echo ""
echo "  1. Monitor logs for any errors:"
echo "     ${BLUE}sudo journalctl -u $SERVICE_NAME -f${NC}"
echo ""
echo "  2. Check service status:"
echo "     ${BLUE}sudo systemctl status $SERVICE_NAME${NC}"
echo ""
echo "  3. Test system functionality"
echo ""
if [ "$DEVICE_TYPE" == "robot" ]; then
    echo "  4. Clear E-STOP if needed (via controller or backend)"
    echo ""
fi
echo "  5. If issues occur, rollback with:"
echo "     ${BLUE}git checkout $BACKUP_BRANCH${NC}"
echo "     ${BLUE}sudo cp $SERVICE_FILE /etc/systemd/system/${NC}"
echo "     ${BLUE}sudo systemctl daemon-reload${NC}"
echo "     ${BLUE}sudo systemctl restart $SERVICE_NAME${NC}"
echo ""
echo "============================================================"
echo ""
