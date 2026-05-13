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

claude -p "Load the skill from .claude/skills/dataqueryplus/SKILL.md and execute the HEARTBEAT PHASE as described in it.
Step 1: Check for expert replies via check_feedback.
Step 2: Classify each reply as correct/incorrect/unclear. Send follow-ups for unclear ones.
Step 3: For actionable incorrect replies, evolve the appropriate skill file (sql_templates.md, data_dictionary.md, or CLAUDE.md).
Step 4: ONLY notify user if skill files were actually changed. Otherwise exit silently." --print 2>&1

echo "=== HEARTBEAT END $(date '+%Y-%m-%d %H:%M:%S') ==="
