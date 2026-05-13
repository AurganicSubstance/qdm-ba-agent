# QDM BA Agent — Technical Architecture

> 钱大妈 (QDM) 业务分析自动取数、专家验证、自进化 Agent
> Last updated: 2026-05-13

---

## 1. System Overview

```
                             ECS (Cron)
                                  │
                   ┌──────────────┴──────────────┐
                   │                             │
            16:30 daily                  7 * * * * hourly
                   │                             │
            run_morning.sh                run_heartbeat.sh
                   │                             │
     ┌─────────────┼─────────────┐        claude -p "..."
     │             │             │              │
  Step 1      Step 2 ×5     Step 3       Check replies
  (Python)    (Claude Code) (Claude Code)   → Classify
     │             │             │           → Evolve skills
     ▼             ▼             ▼           → Notify if changed
  Direct       db_query      send_email
  DeepSeek     + manage_state
  API call
```

**Two runtimes, one backend:**

| Method | What | Why |
|--------|------|-----|
| Direct DeepSeek API (Python `anthropic` SDK) | Question generation | Fast ~5s, no tool use needed |
| Claude Code CLI + DeepSeek V4 Pro | SQL generation, execution, email | Needs agentic loop: read schema → build SQL → execute → handle errors → save |

---

## 2. File Map

```
QDM BA Agent/
├── run_morning.sh              # Cron: daily @16:30 — 3-step morning pipeline
├── run_heartbeat.sh            # Cron: hourly — feedback check + skill evolution
├── run_test.sh                 # Dry-run test (no emails sent)
├── CLAUDE.md                   # Self-evolving data retrieval rules (experts feed back)
├── .env                        # Credentials (API_HOST, MAIL_USERNAME, etc.)
│
├── agent/
│   ├── config.py               # Constants: paths, email, expert routing, QUESTIONS_PER_DAY=5
│   ├── llm_client.py           # Shared Anthropic SDK wrapper (DeepSeek backend)
│   ├── question_generator.py   # KB scanner + LLM prompt → question list
│   ├── email_sender.py         # _SimpleMailClient (SMTP)
│   ├── feedback_collector.py   # IMAP client for fetching replies
│   └── tools/
│       ├── db_query.py         # CLI: execute SQL → JSON rows
│       ├── send_email.py       # CLI: send HTML email via SMTP
│       ├── check_feedback.py   # CLI: fetch IMAP replies → JSON
│       ├── manage_state.py     # CLI: read/write agent_state.json
│       └── generate_questions.py # CLI: generate questions → save state
│
├── src/tools/
│   └── db_connector.py         # REST API connector (MD5 signature, SQL Server)
│
├── .claude/
│   ├── settings.local.json     # Permissions: allow ["*"], additionalDirectories
│   └── skills/dataqueryplus/
│       ├── SKILL.md            # Agent operating manual (200 lines)
│       └── references/
│           ├── data_dictionary.md  # Table/field documentation
│           └── sql_templates.md    # SQL patterns and corrections
│
└── data/
    └── agent_state.json        # Persistent state (daily_runs → questions → results)
```

---

## 3. CLI Tools — Interface Contract

All tools output JSON to stdout. Exit code 0 = success, 1 = error.

### 3.1 `db_query` — Execute SQL

```
python -m agent.tools.db_query "SELECT ..." [--limit N]
```

**Input:** SQL string (single arg)
**Output (success):** `[{"col1": "val1", ...}, ...]` — JSON array, truncated at 500 rows
**Output (error):** `{"error": "message"}`

**Backend:** `src/tools/db_connector.py` → REST API at `bdapp.qdama.cn` with MD5 signature auth.

### 3.2 `send_email` — Send HTML email

```
python -m agent.tools.send_email \
  --to "a@b.com,c@b.com" \
  --subject "Subject" \
  --body-file /tmp/body.html \
  [--cc "cc@b.com"] \
  [--sender-name "取数验证Agent"]
```

**Input:** CLI flags (to, subject, body-file, cc, sender-name). Body in a temp file to avoid shell escaping issues.
**Output:** `{"ok": true, "results": [{"to": "a@b.com", "status": "sent"}]}`
**Backend:** `agent/email_sender._SimpleMailClient` → SMTP at `smtp.exmail.qq.com:465`

### 3.3 `check_feedback` — Fetch IMAP replies

```
python -m agent.tools.check_feedback --hours 24
```

**Input:** `--hours` (look-back window, default 24)
**Output:** `{"replies": [{subject, from, in_reply_to, body, date}, ...], "count": N}`
**Backend:** `agent/feedback_collector._get_imap_client()` → IMAP at `imap.exmail.qq.com:993`

### 3.4 `manage_state` — Read/write persistent state

```
python -m agent.tools.manage_state --get                               # all state
python -m agent.tools.manage_state --get "daily_runs.2026-05-13.sent"  # specific key
python -m agent.tools.manage_state --set "key" '{"json":"value"}'      # set key
python -m agent.tools.manage_state --append "array" '{"item":...}'     # append to array
python -m agent.tools.manage_state --merge "dict" '{"field":"val"}'    # merge into dict
```

**Input:** Action + dot-notation key (supports `array[N]` indexing) + JSON value
**Output:** Requested JSON value, `{"ok": true}`, or `null` for missing keys
**Backend:** Reads/writes `data/agent_state.json` atomically (temp file + os.replace)

### 3.5 `generate_questions` — Generate questions (direct DeepSeek)

```
python -m agent.tools.generate_questions
```

**Input:** None (reads KB and skill files internally)
**Output:** `{"ok": true, "count": 5, "questions": [{question_id, question, domain, expert_name, tables_hint}, ...]}`
**Backend:** `agent.question_generator` → `agent.llm_client.chat()` → DeepSeek V4 Pro
**Side effect:** Saves questions to `agent_state.json` under `daily_runs.DATE.sent`

---

## 4. Phase 1: MORNING (run_morning.sh)

Triggered daily at 16:30 China time via cron.

### Step 1: Generate Questions

| Aspect | Detail |
|--------|--------|
| **Runtime** | Python (direct DeepSeek API, no Claude Code) |
| **Command** | `python -m agent.tools.generate_questions` |
| **What it does** | 1. Scans `../BAKnowledgeBase3.1/2026年/` for `.md` files (skips `会议纪要类`)<br>2. Reads 5 random documents, extracts front matter + body<br>3. Reads skill files: `data_dictionary.md` + `sql_templates.md`<br>4. Sends prompt to DeepSeek V4 Pro (temp=0.8)<br>5. Parses JSON response → 5 question objects<br>6. Classifies each question by domain (关键词 or LLM)<br>7. Assigns expert per domain routing table<br>8. Saves to `agent_state.json` |
| **Input** | KB documents (live scan each run), skill files |
| **Output** | `{"ok": true, "count": 5, "questions": [...]}` |
| **State written** | `daily_runs.DATE.sent[0..4]` — each with: question_id, question, domain, tables_hint, fields_hint, expert_name, expert_email |
| **Duration** | ~5-10 seconds |

### Step 2: Execute Queries (×5)

| Aspect | Detail |
|--------|--------|
| **Runtime** | Claude Code CLI (+ DeepSeek V4 Pro) — 5 separate calls, one per question |
| **Command** | `claude -p "<prompt>" --print --verbose` (in bash loop for i=0..4) |
| **What each call does** | 1. Reads question from state: `manage_state --get "daily_runs.DATE.sent[i]"`<br>2. Reads schema: `data_dictionary.md`<br>3. Builds SQL (Chinese fields backtick-quoted, English no quote, full table path, category filter rules)<br>4. Executes: `python -m agent.tools.db_query "SQL"`<br>5. If error, fixes SQL and retries once<br>6. Saves result via `manage_state --merge` with: sql, status, columns, row_count, **rows (first 20)** |
| **Input per call** | Question object from state, schema from skill files |
| **Output per call** | `{"status":"ok\|error","rows":N}` |
| **State written** | Each question in `sent[i]` gets merged: sql, status, columns, row_count, rows[] |
| **Duration** | ~15-30 seconds per call (×5 = ~2 minutes) |

### Step 3: Send Verification Emails

| Aspect | Detail |
|--------|--------|
| **Runtime** | Claude Code CLI — 1 call |
| **Command** | `claude -p "<prompt>" --print --verbose` |
| **What it does** | 1. Reads all results: `manage_state --get "daily_runs.DATE.sent"`<br>2. Groups questions by `expert_email` (max 3 per email)<br>3. For each group, writes HTML body to `/tmp/email_body_N.html`<br>4. Sends via: `python -m agent.tools.send_email --to "..." --subject "..." --body-file ...` |
| **Input** | Results from state (questions with sql, columns, rows) |
| **Output** | `{"sent":N,"to":["expert1","expert2"]}` |
| **Duration** | ~30-60 seconds |

### Expert Routing

| Domain | Expert | Email |
|--------|--------|-------|
| 商品 (Product) | 刘阗 | liutian1@qdama.cn |
| 运营 (Operations) | 刘舒颖 | liushuying1@qdama.cn |
| 物流 (Logistics) | 周晶晶 | zhoujingjing@qdama.cn |
| 用户 (User/Member) | 刘舒颖 | liushuying1@qdama.cn |

---

## 5. Phase 2: HEARTBEAT (run_heartbeat.sh)

Triggered hourly at :07 via cron.

| Aspect | Detail |
|--------|--------|
| **Runtime** | Claude Code CLI — 1 call |
| **Command** | `claude -p "Load SKILL.md and execute HEARTBEAT PHASE..." --print --verbose` |
| **Step 1** | Check replies: `python -m agent.tools.check_feedback --hours 2` |
| **Step 2** | Classify each reply: correct / incorrect / unclear. Send follow-up for unclear (ask "具体错在哪里？正确口径？") |
| **Step 3** | For **incorrect** replies with clear fixes: append correction to the right skill file<br>- `sql_templates.md` — SQL pattern wrong<br>- `data_dictionary.md` — field meaning wrong<br>- `CLAUDE.md` — general data retrieval rule |
| **Step 4** | Notify `liangsheng1@qdama.cn` ONLY if files changed. Silently exit otherwise. |
| **Evolution rule** | NEVER delete existing content. Only APPEND with date stamp: `## 修正 (evolved YYYY-MM-DD)`. |

---

## 6. State File Schema

`data/agent_state.json`:

```json
{
  "version": 2,
  "daily_runs": {
    "2026-05-13": {
      "sent": [
        {
          "id": "20260513_01",
          "question": "2026年3月华南区销售额排名前10的SKU？",
          "domain": "商品",
          "tables_hint": "product_center_business_sku_v3_info_di",
          "fields_hint": "articleName, totalSaleAmt, areaName, ym",
          "expert_name": "刘阗",
          "expert_email": "liutian1@qdama.cn",
          "sql": "SELECT * FROM ...",
          "status": "ok",
          "columns": ["col1", "col2", ...],
          "row_count": 10,
          "rows": [{"col1": "val1", ...}, ...],
          "reply_status": null,
          "reply_body": null,
          "replied_at": null
        }
      ],
      "replied": [],
      "correct": [],
      "incorrect": [],
      "evolved": []
    }
  }
}
```

**Key paths used by tools:**
- `daily_runs.DATE.sent[i]` — individual question+result
- `daily_runs.DATE.sent[i].sql` — executed SQL (merged by Step 2)
- `daily_runs.DATE.sent[i].rows` — first 20 data rows (merged by Step 2)
- `daily_runs.DATE.evolved[]` — evolution log entries

---

## 7. SQL Conventions (enforced by SKILL.md)

### Quoting Rules
- **Chinese field names**: backtick quotes — `` `销售额` ``
- **English field names**: NO quotes — `articleName`
- **Table names**: full path, no quotes — `default_catalog.ads_business_analysis.operation_center_wide_daily`

### Date Handling
- **运营表** `日期` field: milliseconds timestamp → `FROM_UNIXTIME(\`日期\`/1000, 'yyyy-MM-dd')`
- **商品表** `ym` field: string `'YYYY-MM'` → `ym = '2026-01'`

### Key Filters
- Store-level de-duplicated data: `品类分层` = `'门店'`
- Category aggregation: `品类分层` = `'中分类'` / `'小分类'` / `'sku'`
- Geographic: `门店汇总维度` = `'管理区域'` / `'门店'`

### Known Schema Quirks
- **SKU/SPU tables**: Individual column references (`SELECT articleName`) fail with "Column cannot be resolved". Use `SELECT *` with `WHERE ym=` filter.
- **Percentage fields** in 运营表: stored as strings like `'19.77%'`, need `CAST(REPLACE(..., '%', '') AS DOUBLE) / 100`

---

## 8. Database Tables

### 运营模块 (Operations)

| Table | Purpose |
|-------|---------|
| `operation_center_wide_daily` ⭐ | Core daily operations wide-table. Stores, sales, traffic, loss, margins. |
| `operation_center_dim_store_profile_di` | Store profiles |
| `operation_center_new_store_90d_weekly_store_di` | New store weekly tracking |
| `operation_center_new_store_90d_weekly_region_di` | New store regional aggregation |

### 商品模块 (Product)

| Table | Purpose |
|-------|---------|
| `product_center_business_sku_v3_info_di` ⭐ | SKU-level sales, profit, repurchase. ~10.6M rows. |
| `product_center_business_v3_info_di` | SPU-level. Includes logistics fields (deliverNum, ontimeNum). |

All tables under `default_catalog.ads_business_analysis.*`.

---

## 9. Self-Evolution System

### Mechanism
Expert replies to verification emails → Heartbeat phase classifies → edits skill files.

### Target Files
1. **`data_dictionary.md`** — field corrections/additions
2. **`sql_templates.md`** — corrected SQL patterns
3. **`CLAUDE.md`** — general data retrieval rules (appended to `## 自进化规则` section)

### Evolution Rules
- ONLY append, NEVER delete existing content
- Each entry stamped: `## 修正 (evolved YYYY-MM-DD)`
- Include: original question, SQL, expert feedback (brief context)

---

## 10. LLM Configuration

| Setting | Value |
|---------|-------|
| Model | DeepSeek V4 Pro |
| Endpoint | `ANTHROPIC_BASE_URL` = `https://api.deepseek.com/anthropic` |
| Auth | `ANTHROPIC_API_KEY` or `ANTHROPIC_AUTH_TOKEN` |
| Claude Code mode | `-p` (non-interactive), `--print --verbose` |
| Direct SDK | `anthropic.Anthropic` client, `messages.create()`, max_tokens=4096 |

### Why DeepSeek V4 Pro?
- Anthropic-compatible API endpoint
- Claude Code's agentic harness (tool use loop, skills, permission system) works unchanged
- Cost advantage over Anthropic for automated batch runs

### Why NOT Claude Code for Step 1?
- Question generation is a simple prompt→JSON task
- Claude Code adds ~30s overhead for skill loading before the first tool call
- Direct SDK call completes in ~5s

---

## 11. Cron Configuration (ECS)

```cron
# Morning — daily at 16:30 China time
30 16 * * * cd /root/qdm-ba-agent && bash run_morning.sh >> logs/morning.log 2>&1

# Heartbeat — every hour at :07
7 * * * * cd /root/qdm-ba-agent && bash run_heartbeat.sh >> logs/heartbeat.log 2>&1
```

---

## 12. Design Decisions

1. **Split morning into 7 calls instead of 1** — DeepSeek V4 Pro times out on multi-step prompts that require 15+ tool calls. Each call is now single-purpose: "execute ONE question" vs "execute all 10 questions".

2. **Direct DeepSeek for generation, Claude Code for execution** — Question generation needs no tools (just KB→LLM→JSON). Claude Code's overhead (~30s) is wasted here. Execution needs the agentic loop (build SQL→execute→handle error→save).

3. **State file as IPC** — bash can't easily pass complex data between Claude Code calls. `agent_state.json` serves as the data bus: Step 1 writes questions, Step 2 reads/merges results, Step 3 reads everything.

4. **Temp files for email bodies** — Shell escaping multi-paragraph HTML with Chinese characters is fragile. Writing to `/tmp/email_body_N.html` and passing `--body-file` avoids all escaping issues.

5. **5 questions not 10** — Originally 10, reduced to 5 because DeepSeek's per-call latency (~20s) made 10 calls = 4+ minutes just for Step 2. 5 calls = ~2 minutes.

6. **allow `"*"` permissions** — Claude Code's interactive permission prompts don't work in non-interactive cron mode. `allow: ["*"]` in settings.local.json disables all prompts.

---

## 13. Known Issues & Mitigations

| Issue | Mitigation |
|-------|------------|
| SKU/SPU tables reject column references | Always use `SELECT *`, filter by `WHERE ym=` |
| DeepSeek outputs "needs approval" text instead of executing | Prompt now says "Execute commands directly. Do NOT ask for permission." |
| DeepSeek slow on first token (~15s) | Split work into many small, focused calls |
| DB API `areaName` / `articleName` columns unresolvable | Documented in data_dictionary.md; use `SELECT *` workaround |
| State file JSON escaping in bash | Single-quote heredoc for literal text; `<<PROMPT` for variable expansion |
| `manage_state.py` PosixPath concat bug | Fixed: `str(STATE_FILE) + ".tmp"` |
