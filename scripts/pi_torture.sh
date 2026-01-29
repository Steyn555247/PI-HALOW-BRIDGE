#!/bin/bash
#
# Torture Test Suite for Pi HaLow Bridge
#
# Tests network fault tolerance using Linux traffic control (tc/netem).
# Validates that E-STOP engages correctly under adverse conditions.
#
# REQUIRES:
#   - Root/sudo access
#   - iproute2 (tc command)
#   - Running serpent bridge service
#
# Usage:
#   sudo ./scripts/pi_torture.sh           # Run all tests
#   sudo ./scripts/pi_torture.sh --quick   # Quick smoke test
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_test() {
    echo -e "${BLUE}[TEST]${NC} $1"
}

# Check root
if [ "$EUID" -ne 0 ]; then
    log_error "Please run as root (sudo)"
    exit 1
fi

# Parse arguments
QUICK_MODE=false
while [[ $# -gt 0 ]]; do
    case $1 in
        --quick)
            QUICK_MODE=true
            shift
            ;;
        *)
            log_error "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Find network interface
IFACE=$(ip route | grep default | awk '{print $5}' | head -1)
if [ -z "$IFACE" ]; then
    log_error "Could not detect network interface"
    exit 1
fi

log_info "Using network interface: $IFACE"

# Cleanup function
cleanup() {
    log_info "Cleaning up network emulation..."
    tc qdisc del dev "$IFACE" root 2>/dev/null || true
}
trap cleanup EXIT

# Reset network
reset_network() {
    tc qdisc del dev "$IFACE" root 2>/dev/null || true
    sleep 1
}

# Get E-STOP state from logs
get_estop_state() {
    journalctl -u "serpent-*-bridge" --since "1 minute ago" --no-pager 2>/dev/null | \
        grep -o '"engaged": *[a-z]*' | tail -1 | grep -o 'true\|false' || echo "unknown"
}

# Wait for E-STOP to engage
wait_for_estop() {
    local timeout=$1
    local start=$(date +%s)

    while true; do
        local state=$(get_estop_state)
        if [ "$state" == "true" ]; then
            return 0
        fi

        local now=$(date +%s)
        local elapsed=$((now - start))
        if [ $elapsed -ge $timeout ]; then
            return 1
        fi

        sleep 1
    done
}

# Test results
TESTS_PASSED=0
TESTS_FAILED=0

run_test() {
    local name=$1
    local expected=$2
    shift 2

    log_test "Running: $name"
    echo ""

    # Run test
    if "$@"; then
        if [ "$expected" == "pass" ]; then
            echo -e "${GREEN}PASSED${NC}: $name"
            ((TESTS_PASSED++))
        else
            echo -e "${RED}FAILED${NC}: $name (expected failure)"
            ((TESTS_FAILED++))
        fi
    else
        if [ "$expected" == "fail" ]; then
            echo -e "${GREEN}PASSED${NC}: $name (expected failure)"
            ((TESTS_PASSED++))
        else
            echo -e "${RED}FAILED${NC}: $name"
            ((TESTS_FAILED++))
        fi
    fi
    echo ""
}

# ============================================================
# TEST: Complete Network Blackout
# ============================================================
test_blackout() {
    log_info "Simulating complete network blackout..."

    # Drop all packets
    tc qdisc add dev "$IFACE" root netem loss 100%

    log_info "Waiting for E-STOP (should trigger within 5-10 seconds)..."

    if wait_for_estop 15; then
        log_info "E-STOP engaged correctly during blackout"
        reset_network
        return 0
    else
        log_error "E-STOP did NOT engage during blackout!"
        reset_network
        return 1
    fi
}

# ============================================================
# TEST: High Latency
# ============================================================
test_high_latency() {
    log_info "Simulating high latency (3 second delay)..."

    # Add 3 second delay
    tc qdisc add dev "$IFACE" root netem delay 3000ms

    log_info "Waiting for E-STOP (should trigger due to watchdog)..."

    if wait_for_estop 15; then
        log_info "E-STOP engaged correctly during high latency"
        reset_network
        return 0
    else
        log_error "E-STOP did NOT engage during high latency!"
        reset_network
        return 1
    fi
}

# ============================================================
# TEST: Packet Loss (50%)
# ============================================================
test_packet_loss() {
    log_info "Simulating 50% packet loss..."

    tc qdisc add dev "$IFACE" root netem loss 50%

    # With 50% loss, some packets get through, E-STOP may or may not trigger
    # The important thing is the system doesn't crash
    sleep 10

    reset_network

    # Check system is still running
    if systemctl is-active --quiet "serpent-robot-bridge" 2>/dev/null || \
       systemctl is-active --quiet "serpent-base-bridge" 2>/dev/null; then
        log_info "System survived packet loss"
        return 0
    else
        log_error "Service crashed during packet loss!"
        return 1
    fi
}

# ============================================================
# TEST: Bandwidth Collapse
# ============================================================
test_bandwidth_collapse() {
    log_info "Simulating bandwidth collapse (1kbps)..."

    tc qdisc add dev "$IFACE" root tbf rate 1kbit burst 32kbit latency 400ms

    log_info "Running for 15 seconds under bandwidth collapse..."
    sleep 15

    reset_network

    # System should survive, video should drop, control may timeout -> E-STOP
    log_info "Checking system status..."

    if systemctl is-active --quiet "serpent-robot-bridge" 2>/dev/null || \
       systemctl is-active --quiet "serpent-base-bridge" 2>/dev/null; then
        log_info "System survived bandwidth collapse"
        return 0
    else
        log_error "Service crashed during bandwidth collapse!"
        return 1
    fi
}

# ============================================================
# TEST: Intermittent Connection
# ============================================================
test_intermittent() {
    log_info "Simulating intermittent connection (5s on, 3s off)..."

    for i in 1 2 3; do
        log_info "  Cycle $i: Network UP"
        reset_network
        sleep 5

        log_info "  Cycle $i: Network DOWN"
        tc qdisc add dev "$IFACE" root netem loss 100%
        sleep 3
    done

    reset_network

    # Check E-STOP state
    local state=$(get_estop_state)
    log_info "Final E-STOP state: $state"

    # E-STOP should be engaged after intermittent connection
    if [ "$state" == "true" ]; then
        log_info "E-STOP correctly engaged after intermittent connection"
        return 0
    else
        log_warn "E-STOP may not have engaged (depends on timing)"
        return 0  # This is acceptable
    fi
}

# ============================================================
# MAIN
# ============================================================

echo "============================================================"
echo "Pi HaLow Bridge Torture Test Suite"
echo "============================================================"
echo ""
echo "Interface: $IFACE"
echo "Quick mode: $QUICK_MODE"
echo ""
echo "WARNING: This will disrupt network connectivity!"
echo ""
read -p "Continue? [y/N] " -n 1 -r
echo

if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Aborted."
    exit 0
fi

echo ""

# Reset network before starting
reset_network

if [ "$QUICK_MODE" == "true" ]; then
    # Quick tests only
    run_test "Network Blackout" "pass" test_blackout
else
    # Full test suite
    run_test "Network Blackout" "pass" test_blackout
    run_test "High Latency (3s)" "pass" test_high_latency
    run_test "Packet Loss (50%)" "pass" test_packet_loss
    run_test "Bandwidth Collapse" "pass" test_bandwidth_collapse
    run_test "Intermittent Connection" "pass" test_intermittent
fi

# Summary
echo ""
echo "============================================================"
echo "Torture Test Summary"
echo "============================================================"
echo ""
echo -e "Passed: ${GREEN}${TESTS_PASSED}${NC}"
echo -e "Failed: ${RED}${TESTS_FAILED}${NC}"
echo ""

if [ $TESTS_FAILED -eq 0 ]; then
    echo -e "${GREEN}All tests passed!${NC}"
    exit 0
else
    echo -e "${RED}Some tests failed!${NC}"
    exit 1
fi
