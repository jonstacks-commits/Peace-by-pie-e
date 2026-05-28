#!/bin/bash
# run_daily_search.sh - Daily LinkedIn Job Search Runner (3 Resume Tracks)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SEARCH_SCRIPT="$SCRIPT_DIR/linkedin_job_search.py"
NOTION_SCRIPT="$SCRIPT_DIR/notion_integration.py"
OUTPUT_DIR="$HOME/Desktop/LinkedIn_Jobs"
TIMESTAMP="$(date +%Y-%m-%d)"
LOG_FILE="$HOME/Peace-by-pie-e/search.log"
NOTION_CONFIG="$HOME/.linkedin_notion_config.json"

mkdir -p "$OUTPUT_DIR"
echo "========================================" >> "$LOG_FILE"
echo "Run: $TIMESTAMP $(date +%H:%M:%S)" >> "$LOG_FILE"

TOTAL=0

run_track() {
    local track_name=$1
    local resume_version=$2
    local output_file="$OUTPUT_DIR/jobs_${track_name}_${TIMESTAMP}.csv"
    shift 2
    echo "--- Track: $track_name ---" >> "$LOG_FILE"
    /usr/bin/python3 "$SEARCH_SCRIPT" --time 24h --format csv --output "$output_file" "$@" 2>> "$LOG_FILE"
    if [ -f "$output_file" ]; then
        COUNT=$(tail -n +2 "$output_file" 2>/dev/null | wc -l | tr -d " ")
        echo "Found $COUNT jobs for $track_name" >> "$LOG_FILE"
        TOTAL=$((TOTAL + COUNT))
        if [ -f "$NOTION_CONFIG" ] && [ -f "$NOTION_SCRIPT" ]; then
            /usr/bin/python3 "$NOTION_SCRIPT" --csv "$output_file" --resume-version "$resume_version" 2>> "$LOG_FILE"
        fi
    fi
}

run_track "gtm_strategy" "Strategy" \
    --extra-roles "GTM strategy" "go-to-market strategy" "market development" "platform strategy" "commercial strategy" "launch strategy" "market access strategy" \
    --extra-industries "biotech" "biopharma" "life sciences" "genomics" "CRO" "CDMO"

run_track "business_dev" "Business Development" \
    --extra-roles "business development" "strategic alliances" "partnerships director" "VP partnerships" "alliance management" "corporate development" "BD director" \
    --extra-industries "biotech" "biopharma" "life sciences" "genomics" "CRO" "CDMO"

run_track "commercial_ops" "Operations" \
    --extra-roles "commercial operations" "revenue operations" "sales operations" "CRM director" "RevOps" "sales enablement director" "forecast operations" \
    --extra-industries "biotech" "biopharma" "life sciences" "genomics" "CRO" "CDMO"

echo "Total new jobs: $TOTAL" >> "$LOG_FILE"
echo "========================================" >> "$LOG_FILE"

osascript -e "display notification \"Found $TOTAL new jobs today across 3 resume tracks.\" with title \"LinkedIn Job Search\"" 2>/dev/null
exit 0
