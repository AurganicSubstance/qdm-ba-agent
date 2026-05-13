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

claude -p "$(cat <<'PROMPT'
Load .claude/skills/dataqueryplus/SKILL.md and execute HEARTBEAT PHASE.

Step 1: Check for expert replies via python -m agent.tools.check_feedback --hours 2.
Step 2: Classify each as correct/incorrect/unclear. Send follow-up for unclear ones.
Step 3: For actionable incorrect replies, evolve the right skill file. Only append, never delete.
Step 4: Notify liangsheng1@qdama.cn ONLY if files changed. Otherwise exit silently.
PROMPT
)" --print --verbose

echo "=== HEARTBEAT END $(date '+%Y-%m-%d %H:%M:%S') ==="
