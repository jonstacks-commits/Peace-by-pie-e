#!/bin/bash
# ============================================================================
# install_schedule.sh — Install the daily 7 AM LinkedIn job search schedule
# Run this once:  bash install_schedule.sh
# ============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLIST_SRC="$SCRIPT_DIR/com.linkedin.jobsearch.plist"
PLIST_DST="$HOME/Library/LaunchAgents/com.linkedin.jobsearch.plist"
OUTPUT_DIR="$HOME/Desktop/LinkedIn_Jobs"

echo "=== LinkedIn Job Search — Scheduler Installer ==="
echo ""

# 1. Create output directory
mkdir -p "$OUTPUT_DIR"
echo "[OK] Created $OUTPUT_DIR"

# 2. Unload existing job if present
if launchctl list | grep -q "com.linkedin.jobsearch"; then
    launchctl unload "$PLIST_DST" 2>/dev/null || true
    echo "[OK] Unloaded previous schedule"
fi

# 3. Copy plist and replace placeholder paths
sed -e "s|PLACEHOLDER_PATH|$SCRIPT_DIR|g" \
    -e "s|PLACEHOLDER_HOME|$HOME|g" \
    "$PLIST_SRC" > "$PLIST_DST"
echo "[OK] Installed plist to $PLIST_DST"

# 4. Load the schedule
launchctl load "$PLIST_DST"
echo "[OK] Loaded schedule — job will run daily at 7:00 AM"

echo ""
echo "=== Setup Complete ==="
echo ""
echo "  CSV files will be saved to: $OUTPUT_DIR"
echo "  You'll get a macOS notification each morning."
echo ""
echo "  Useful commands:"
echo "    Test now:    bash $SCRIPT_DIR/run_daily_search.sh"
echo "    Uninstall:   launchctl unload $PLIST_DST && rm $PLIST_DST"
echo "    View logs:   cat $OUTPUT_DIR/search.log"
echo ""
