#!/bin/bash
# Morning Phase — Claude Code Data Retrieval Agent
# Cron: 30 16 * * * cd /root/qdm-ba-agent && bash run_morning.sh >> logs/morning.log 2>&1
set -e

cd "$(dirname "$0")"
TODAY=$(date '+%Y-%m-%d')
TODAY_MMDD=$(date '+%m/%d')
echo "=== MORNING PHASE START $TODAY $(date '+%H:%M:%S') ==="

set -a
[ -f .env ] && source .env
set +a

export ANTHROPIC_BASE_URL="${ANTHROPIC_BASE_URL:-https://api.deepseek.com/anthropic}"
export ANTHROPIC_API_KEY="${ANTHROPIC_AUTH_TOKEN:-$ANTHROPIC_API_KEY}"
export ANTHROPIC_DEFAULT_SONNET_MODEL="${ANTHROPIC_DEFAULT_SONNET_MODEL:-deepseek-v4-pro}"

# ── Step 1: Generate 5 questions (direct DeepSeek, no Claude Code) ──
echo "=== STEP 1: Generating questions ==="
python -m agent.tools.generate_questions
echo "=== STEP 1 DONE ==="

# ── Step 2: Execute each question (Claude Code → SQL, Python → DB) ──
echo "=== STEP 2: Executing queries ==="
for i in 0 1 2 3 4; do
  echo "--- Question $((i+1))/5 ---"
  if python -m agent.tools.build_and_execute $i; then
    echo "Q$i OK"
  else
    echo "Q$i FAILED"
  fi
done
echo "=== STEP 2 DONE ==="

# ── Step 3: Send verification emails (pure Python) ──
echo "=== STEP 3: Sending emails ==="
python -m agent.tools.send_verification_emails
echo "=== STEP 3 DONE ==="

echo "=== MORNING PHASE END $TODAY $(date '+%H:%M:%S') ==="
