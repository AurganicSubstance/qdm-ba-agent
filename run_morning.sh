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

claude --skill dataqueryplus -p "Execute the complete MORNING PHASE as described in SKILL.md. Today is $TODAY.
Step 1: Generate 10 questions from the KnowledgeBase and save to state.
Step 2: Execute all 10 SQL queries (build SQL, run db_query, retry on error).
Step 3: Send verification emails grouped by expert (max 3 per email).
Follow ALL SQL Conventions exactly. Use the CLI tools for all database, email, and state operations." --print 2>&1

echo "=== MORNING PHASE END $TODAY $(date '+%H:%M:%S') ==="
