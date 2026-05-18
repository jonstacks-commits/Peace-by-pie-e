#!/bin/bash
# ============================================================================
# run_daily_search.sh — Daily LinkedIn Job Search Runner
# Intended to be called by macOS launchd at 7:00 AM each day.
# ============================================================================

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SCRIPT="$SCRIPT_DIR/linkedin_job_search.py"
OUTPUT_DIR="$HOME/Desktop/LinkedIn_Jobs"
TIMESTAMP="$(date +%Y-%m-%d)"
LOG_FILE="$OUTPUT_DIR/search.log"

# Ensure output directory exists
mkdir -p "$OUTPUT_DIR"

echo "======================================" >> "$LOG_FILE"
echo "Run: $TIMESTAMP $(date +%H:%M:%S)"     >> "$LOG_FILE"

# Run the search — save CSV and JSON to Desktop folder
/usr/bin/python3 "$SCRIPT" \
    --time 24h \
    --format csv \
    --output "$OUTPUT_DIR/jobs_${TIMESTAMP}.csv" \
    2>> "$LOG_FILE"

echo "Finished search: $(date +%H:%M:%S)"    >> "$LOG_FILE"

# Count results
COUNT=$(tail -n +2 "$OUTPUT_DIR/jobs_${TIMESTAMP}.csv" 2>/dev/null | wc -l | tr -d ' ')

# Push to Notion if config exists
NOTION_SCRIPT="$SCRIPT_DIR/notion_integration.py"
NOTION_CONFIG="$HOME/.linkedin_notion_config.json"
NOTION_MSG=""
if [ -f "$NOTION_CONFIG" ] && [ -f "$NOTION_SCRIPT" ]; then
    echo "Pushing to Notion..." >> "$LOG_FILE"
    /usr/bin/python3 "$NOTION_SCRIPT" \
        --csv "$OUTPUT_DIR/jobs_${TIMESTAMP}.csv" \
        2>> "$LOG_FILE"
    NOTION_MSG=" + synced to Notion"
fi

echo "Finished: $(date +%H:%M:%S)"           >> "$LOG_FILE"
echo "======================================" >> "$LOG_FILE"

# Send macOS notification
osascript -e "display notification \"Found ${COUNT} new jobs today${NOTION_MSG}. CSV on Desktop.\" with title \"LinkedIn Job Search\"" 2>/dev/null

exit 0
