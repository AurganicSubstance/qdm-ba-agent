#!/bin/bash
# Morning Phase — Claude Code Data Retrieval Agent
# Cron: 30 16 * * * cd /root/qdm-ba-agent && bash run_morning.sh >> logs/morning.log 2>&1
set -e

cd "$(dirname "$0")"
TODAY=$(date '+%Y-%m-%d')
echo "=== MORNING PHASE START $TODAY $(date '+%H:%M:%S') ==="

set -a
[ -f .env ] && source .env
set +a

export ANTHROPIC_BASE_URL="${ANTHROPIC_BASE_URL:-https://api.deepseek.com/anthropic}"
export ANTHROPIC_API_KEY="${ANTHROPIC_AUTH_TOKEN:-$ANTHROPIC_API_KEY}"
export ANTHROPIC_DEFAULT_SONNET_MODEL="${ANTHROPIC_DEFAULT_SONNET_MODEL:-deepseek-v4-pro}"

# ── Step 1: Generate 5 questions ──
echo "=== STEP 1: Generating questions ==="
claude -p "$(cat <<'PROMPT'
Task: Generate 5 data questions. Do nothing else.

1. Read 5 .md files from ../BAKnowledgeBase3.1/2026年/ (skip 会议纪要类 dirs).
2. Read .claude/skills/dataqueryplus/references/data_dictionary.md for table/field names.
3. Generate 5 questions covering 4 domains: 商品/运营/物流/用户.
4. Each question: {question_id, question, domain, tables_hint, fields_hint, expert_name, expert_email}
   Expert routing: 商品→刘阗/liutian1, 运营→刘舒颖/liushuying1, 物流→周晶晶/zhoujingjing, 用户→刘舒颖/liushuying1
5. Save to state then exit:
   python -m agent.tools.manage_state --set "daily_runs.DATE" '{"sent":[],"replied":[],"correct":[],"incorrect":[],"evolved":[]}'
   python -m agent.tools.manage_state --append "daily_runs.DATE.sent" 'QUESTION_JSON'
   (repeat append for all 5, replace DATE with today YYYY-MM-DD)
6. Output the 5 question IDs and exit. No email. No SQL execution.
PROMPT
)" --dangerously-skip-permissions --print --verbose
echo "=== STEP 1 DONE ==="

# ── Step 2: Execute each question (5 separate CC calls) ──
echo "=== STEP 2: Executing queries ==="
for i in 0 1 2 3 4; do
  echo "--- Question $((i+1))/5 ---"
  if claude -p "$(cat <<PROMPT
Execute ONE question. Read .claude/skills/dataqueryplus/references/data_dictionary.md first.
Then read the question at index $i: python -m agent.tools.manage_state --get "daily_runs.${TODAY}.sent[${i}]"
Write ONE SQL. Follow rules exactly:
- Chinese fields: backtick quotes. English fields: no quotes.
- Full table path: default_catalog.ads_business_analysis.<table>
- 品类分层='门店' for store-level. from_unixtime(日期/1000) for dates.
- Only SELECT *, no column references on SKU/SPU tables.
Run: python -m agent.tools.db_query "SQL"
If error, fix and retry ONCE.
Save result: python -m agent.tools.manage_state --merge "daily_runs.${TODAY}.sent[${i}]" '{"sql":"...","status":"success|error","columns":[...],"row_count":N}'
Report: success or fail. Nothing else.
PROMPT
)" --dangerously-skip-permissions --print --verbose; then
    echo "Q$i OK"
  else
    echo "Q$i FAILED"
  fi
done
echo "=== STEP 2 DONE ==="

# ── Step 3: Send verification emails ──
echo "=== STEP 3: Sending emails ==="
claude -p "$(cat <<PROMPT
Task: Send verification emails. Do nothing else.

1. Get today's results: python -m agent.tools.manage_state --get "daily_runs.${TODAY}.sent"
2. Group by expert email. Max 3 questions per email.
3. For each email, write HTML body to /tmp/email_body_N.html using the template from .claude/skills/dataqueryplus/SKILL.md (Phase 1 Step 3).
4. Send via: python -m agent.tools.send_email --to "EMAIL" --subject "【取数验证】DATE 数据取数验证 - NAME" --body-file /tmp/email_body_N.html --sender-name "取数验证Agent"
5. Report: how many emails sent to whom. Exit.
PROMPT
)" --dangerously-skip-permissions --print --verbose
echo "=== STEP 3 DONE ==="

echo "=== MORNING PHASE END $TODAY $(date '+%H:%M:%S') ==="
