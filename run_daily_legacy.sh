#!/bin/bash
# Daily Agent Pipeline
# Usage: bash run_daily.sh [morning|evening|full]
# Cron:
#   0 9 * * * cd ~/QDM-BA-Agent && bash run_daily.sh morning >> ~/agent_morning.log 2>&1
#   0 18 * * * cd ~/QDM-BA-Agent && bash run_daily.sh evening >> ~/agent_evening.log 2>&1

PHASE="${1:-full}"

cd "$(dirname "$0")"

# Activate Python 3.9 (CentOS 7 default is 3.6)
export PATH="/usr/local/bin:$PATH"

echo "============================================"
echo "Agent Pipeline: $PHASE — $(date '+%Y-%m-%d %H:%M:%S')"
echo "============================================"

python3 -m agent.orchestrator --phase "$PHASE"

echo "============================================"
echo "Agent Pipeline: $PHASE — DONE $(date '+%Y-%m-%d %H:%M:%S')"
echo "============================================"
