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
Send verification emails for today's questions. No questions, no planning — just send.

Step A: python -m agent.tools.manage_state --get "daily_runs.${TODAY}.sent"
Step B: Group results by expert_email. Max 3 per email.
Step C: For each group, write HTML to /tmp/email_body_N.html following the template below, then send:
python -m agent.tools.send_email --to "expert@email" --subject "【取数验证】${TODAY_MMDD} 取数验证 - Name" --body-file /tmp/email_body_N.html --sender-name "取数验证Agent"

HTML template (use exactly):
<h2>取数验证 — ${TODAY_MMDD}</h2>
<p><b>NAME</b> 您好，以下是今日的自动取数结果。请验证数据是否正确：</p>
<blockquote style='background:#f5f5f5;padding:10px;'><b>验证方式</b>：正确请回复<b>"正确"</b>；不对请回复<b>"不对"</b>并说明正确口径和字段。</blockquote>
<!-- per question: -->
<div style='margin:20px 0;padding:15px;border:1px solid #ddd;'>
<h3>问题 N (DOMAIN)</h3>
<p><b>问题</b>: QUESTION</p>
<p><b>表</b>: TABLE</p>
<pre style='background:#2d2d2d;color:#f8f8f2;padding:10px;'>SQL</pre>
<p><b>结果</b> (N rows):</p>
<table border='1' cellpadding='4' cellspacing='0' style='border-collapse:collapse;'>
<tr style='background:#f0f0f0;'>HEADER</tr>
<!-- first 20 data rows -->
</table>
</div>
<p style='color:#666;font-size:11px;'>此邮件由取数验证Agent自动发送。请直接回复本邮件。</p>

After all emails sent, output: "SENT: N emails to [experts]". No further tool calls.
PROMPT
)" --print --verbose
echo "=== STEP 3 DONE ==="

echo "=== MORNING PHASE END $TODAY $(date '+%H:%M:%S') ==="
