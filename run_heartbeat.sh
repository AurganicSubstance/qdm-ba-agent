#!/bin/bash
# Heartbeat Phase — Claude Code Data Retrieval Agent
# Cron: 7 * * * * cd /root/qdm-ba-agent && bash run_heartbeat.sh >> logs/heartbeat.log 2>&1
set -e

cd "$(dirname "$0")"
NOW=$(date '+%Y-%m-%d %H:%M:%S')
echo "=== HEARTBEAT START $NOW ==="

# Source environment
set -a
[ -f .env ] && source .env
set +a

# Claude Code configuration
export ANTHROPIC_BASE_URL="${ANTHROPIC_BASE_URL:-https://api.deepseek.com/anthropic}"
export ANTHROPIC_API_KEY="${ANTHROPIC_AUTH_TOKEN:-$ANTHROPIC_API_KEY}"
export ANTHROPIC_DEFAULT_SONNET_MODEL="${ANTHROPIC_DEFAULT_SONNET_MODEL:-deepseek-v4-pro}"

# ── Heartbeat: collect feedback → classify → evolve → notify ──
python -m agent.tools.run_evolution

echo "=== HEARTBEAT END $(date '+%Y-%m-%d %H:%M:%S') ==="
