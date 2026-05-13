#!/bin/bash
# Test Run — Claude Code agent harness validation (no emails sent)
set -e

cd "$(dirname "$0")"
TODAY=$(date '+%Y-%m-%d')
echo "=== TEST RUN START $TODAY $(date '+%H:%M:%S') ==="

set -a
[ -f .env ] && source .env
set +a

export ANTHROPIC_BASE_URL="${ANTHROPIC_BASE_URL:-https://api.deepseek.com/anthropic}"
export ANTHROPIC_API_KEY="${ANTHROPIC_AUTH_TOKEN:-$ANTHROPIC_API_KEY}"
export ANTHROPIC_DEFAULT_SONNET_MODEL="${ANTHROPIC_DEFAULT_SONNET_MODEL:-deepseek-v4-pro}"

claude -p "You are the DataQueryPlus agent. Execute a TEST DRY RUN of the MORNING PHASE. Today is $TODAY.

IMPORTANT: This is a TEST. Do NOT send any emails. Skip Step 3 entirely.

Step 1: Generate 5 data retrieval questions from the KnowledgeBase at ../BAKnowledgeBase3.1/2026年/.
- Scan .md files, skip 会议纪要类 directories. Read 5 documents.
- Read .claude/skills/dataqueryplus/references/data_dictionary.md and sql_templates.md for table/field knowledge.
- Generate 5 diverse questions covering all 4 domains (商品/运营/物流/用户).
- Save questions to state via: python -m agent.tools.manage_state --set \"daily_runs.$TODAY\" '{\"sent\":[], \"replied\":[], \"correct\":[], \"incorrect\":[], \"evolved\":[]}'
- Then append each question via: python -m agent.tools.manage_state --append \"daily_runs.$TODAY.sent\" '<json>'

Step 2: Execute all 5 SQL queries.
- For each question, build a SINGLE SQL following conventions in .claude/skills/dataqueryplus/SKILL.md:
  * Chinese field names MUST use backtick quotes (e.g. \`销售额\`)
  * English field names NO quotes
  * Full table path: default_catalog.ads_business_analysis.operation_center_wide_daily
  * Date filter: FROM_UNIXTIME(\`日期\`/1000, 'yyyy-MM-dd') format
  * 品类分层 = '门店' for store-level queries
- Run: python -m agent.tools.db_query \"THE SQL\"
- If error, analyze and retry ONCE with fixed SQL.
- Print results to stdout.

Step 3: Report summary — how many queries succeeded, how many failed, what errors remain. Do NOT send emails.

After completing, run: python -m agent.tools.manage_state --get \"daily_runs.$TODAY\" to show the saved state." --print 2>&1

echo "=== TEST RUN END $(date '+%Y-%m-%d %H:%M:%S') ==="
