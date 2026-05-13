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

# ── Step 2: Execute each question (5 separate CC calls) ──
echo "=== STEP 2: Executing queries ==="
for i in 0 1 2 3 4; do
  echo "--- Question $((i+1))/5 ---"
  if claude -p "$(cat <<PROMPT
Read question: python -m agent.tools.manage_state --get "daily_runs.${TODAY}.sent[${i}]"
Read schema: Read .claude/skills/dataqueryplus/references/data_dictionary.md

Write SQL with these rules:
- Chinese fields: backtick \`quotes\`. English fields: NO quotes.
- Table: default_catalog.ads_business_analysis.<table>
- \`品类分层\`='门店' for store-level. from_unixtime(\`日期\`/1000) for dates.
- SKU/SPU tables: SELECT * only.

Execute: python -m agent.tools.db_query "SQL"
If error: fix SQL, run again.

After db_query succeeds, save result via manage_state --merge with FULL data:
python -m agent.tools.manage_state --merge "daily_runs.${TODAY}.sent[${i}]" '{"sql":"<the SQL>","status":"ok","columns":[...],"row_count":N,"rows":[...first 20 rows...]}'

CRITICAL: The merge MUST include the "rows" array with actual data. Step 3 emails need it.
CRITICAL: Execute commands directly. Do NOT ask for permission. Do NOT explain first.
Output after done: {"status":"ok|error","rows":N}
PROMPT
)" --print --verbose; then
    echo "Q$i OK"
  else
    echo "Q$i FAILED"
  fi
done
echo "=== STEP 2 DONE ==="

# ── Step 3: Send verification emails ──
echo "=== STEP 3: Sending emails ==="
claude -p "$(cat <<PROMPT
Read results: python -m agent.tools.manage_state --get "daily_runs.${TODAY}.sent"
Group by expert_email field. Max 3 per email.

For each group:
1. Write HTML body to /tmp/email_body_N.html:
<h2>取数验证 — ${TODAY_MMDD}</h2>
<p><b>NAME</b> 您好，以下是今日的自动取数结果。请验证数据是否正确：</p>
<blockquote style='background:#f5f5f5;padding:10px;'><b>验证方式</b>：正确请回复<b>"正确"</b>；不对请回复<b>"不对"</b>并说明正确口径和字段。</blockquote>
<!-- per question: -->
<div style='margin:20px 0;padding:15px;border:1px solid #ddd;'>
<h3>问题 N (DOMAIN)</h3>
<p><b>问题</b>: QUESTION_TEXT</p>
<p><b>表</b>: TABLE_HINT</p>
<pre style='background:#2d2d2d;color:#f8f8f2;padding:10px;'>SQL_TEXT</pre>
<p><b>结果</b> (ROW_COUNT rows):</p>
<table border='1' cellpadding='4' cellspacing='0' style='border-collapse:collapse;'>
<tr style='background:#f0f0f0;'>COLUMN_HEADERS</tr>
DATA_ROWS
</table>
</div>
<p style='color:#666;font-size:11px;'>此邮件由取数验证Agent自动发送。请直接回复本邮件。</p>

2. Send: python -m agent.tools.send_email --to "EXPERT_EMAIL" --subject "【取数验证】${TODAY_MMDD} 取数验证 - EXPERT_NAME" --body-file /tmp/email_body_N.html --sender-name "取数验证Agent"

CRITICAL: Execute commands directly. Do NOT ask for permission. Do NOT explain first.
After all sent, output: {"sent":N,"to":["expert1","expert2"]}
PROMPT
)" --print --verbose
echo "=== STEP 3 DONE ==="

echo "=== MORNING PHASE END $TODAY $(date '+%H:%M:%S') ==="
