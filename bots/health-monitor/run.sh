#!/bin/bash
# Morning report runner - call it from cron, e.g.:  0 8 * * *  /path/to/health-monitor/run.sh
cd "$(dirname "$0")" || exit 1
mkdir -p data
exec >> data/cron.log 2>&1
echo "=== $(date) ==="
python3 main.py
echo "=== Done ==="
