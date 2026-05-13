#!/bin/bash
# Morning Phase — Claude Code Data Retrieval Agent
# Cron: 30 16 * * * cd /root/qdm-ba-agent && bash run_morning.sh >> logs/morning.log 2>&1
set -e

cd "$(dirname "$0")"
TODAY=$(date '+%Y-%m-%d')
echo "=== MORNING PHASE START $TODAY $(date '+%H:%M:%S') ==="

# Source environment
set -a
[ -f .env ] && source .env
set +a

# Claude Code configuration
export ANTHROPIC_BASE_URL="${ANTHROPIC_BASE_URL:-https://api.deepseek.com/anthropic}"
export ANTHROPIC_API_KEY="${ANTHROPIC_AUTH_TOKEN:-$ANTHROPIC_API_KEY}"
export ANTHROPIC_DEFAULT_SONNET_MODEL="${ANTHROPIC_DEFAULT_SONNET_MODEL:-deepseek-v4-pro}"

claude -p "$(cat <<'PROMPT'
Load .claude/skills/dataqueryplus/SKILL.md and execute MORNING PHASE.

Step 1: Generate 5 questions from ../BAKnowledgeBase3.1/2026年/ covering 商品/运营/物流/用户. Save to state.
Step 2: Execute each via python -m agent.tools.db_query. Retry once on error.
Step 3: Send verification emails grouped by expert (max 3 per email).

Follow SQL Conventions in SKILL.md. Use CLI tools for all operations.
PROMPT
)" --print --verbose

echo "=== MORNING PHASE END $TODAY $(date '+%H:%M:%S') ==="
