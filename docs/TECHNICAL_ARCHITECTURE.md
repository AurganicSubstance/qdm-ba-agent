# QDM BA Agent — Technical Architecture

> 钱大妈 (QDM) 业务分析自动取数、专家验证、自进化 Agent
> Last updated: 2026-05-13 (hybrid CC+Python architecture)

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
  (Pure       (CC→SQL      (Pure         → Classify
   Python)     Py→exec)     Python)       → Evolve skills
     │             │             │         → Notify if changed
     ▼             ▼             ▼
  Direct       Claude Code   Template
  DeepSeek     → SQL text    → HTML
  API call     → Python DB   → SMTP
```

**Hybrid architecture — Claude Code for reasoning, Python for execution:**

| Step | Reasoning | Execution | Why |
|------|-----------|-----------|-----|
| 1. Question generation | — | Python (direct DeepSeek SDK) | Simple prompt→JSON, no tools needed, ~5s |
| 2. SQL generation + DB | Claude Code (`-p --print`) | Python (`subprocess` → extract SQL → DB) | CC reasons about schema+question, Python runs DB |
| 3. Email sending | — | Python (template fill + SMTP) | Deterministic, no LLM reasoning needed |
| Heartbeat | Claude Code (`-p --print`) | Python tools | CC classifies reply text, calls tools for state/files |

**Why hybrid?** DeepSeek V4 Pro hallucinates tool calls — outputs "I need your approval" text instead of invoking tools. Claude Code is kept for text reasoning (SQL generation, reply classification). All actual execution is Python calling Python.

---

## 2. File Map

```
QDM BA Agent/
├── run_morning.sh              # Cron: daily @16:30 — 3-step pipeline
├── run_heartbeat.sh            # Cron: hourly — feedback check + skill evolution
├── run_test.sh                 # Shortcut: run_morning.sh --test
├── CLAUDE.md                   # Self-evolving data retrieval rules
├── .env                        # Credentials (API_HOST, MAIL_USERNAME, etc.)
│
├── agent/
│   ├── config.py               # Constants: paths, expert routing, QUESTIONS_PER_DAY=5
│   ├── llm_client.py           # Anthropic SDK wrapper (DeepSeek V4 Pro backend)
│   ├── question_generator.py   # KB scanner + LLM→questions + domain classification
│   ├── data_retriever.py       # _build_sql() + execute_question() — SQL gen + DB execution
│   ├── email_sender.py         # _SimpleMailClient (SMTP)
│   ├── feedback_collector.py   # IMAP client for fetching replies
│   └── tools/
│       ├── generate_questions.py    # CLI: scan KB → LLM → questions → save state
│       ├── build_and_execute.py     # CLI: CC→SQL text → Python extract → DB → save
│       ├── send_verification_emails.py # CLI: read state → build HTML → send emails
│       ├── db_query.py              # CLI: execute SQL → JSON rows
│       ├── send_email.py            # CLI: send HTML email via SMTP
│       ├── check_feedback.py        # CLI: fetch IMAP replies → JSON
│       └── manage_state.py          # CLI: read/write agent_state.json
│
├── src/tools/
│   └── db_connector.py         # REST API connector (MD5 signature auth)
│
├── .claude/
│   ├── settings.local.json     # Permissions: allow ["*"] (no interactive prompts)
│   └── skills/dataqueryplus/
│       ├── SKILL.md            # Operating manual for Claude Code (200 lines)
│       └── references/
│           ├── data_dictionary.md  # Table/field documentation
│           └── sql_templates.md    # SQL patterns and expert corrections
│
└── data/
    └── agent_state.json        # Persistent state (daily_runs → questions → results)
```

---

## 3. CLI Tools — Interface Contract

All tools output JSON to stdout. Exit code 0 = success, 1 = error.

### 3.1 `generate_questions` — Generate questions (direct DeepSeek)

```
python -m agent.tools.generate_questions
```

| | |
|---|---|
| **Input** | None (reads KB + skill files internally) |
| **Output** | `{"ok": true, "count": 5, "questions": [...]}` |
| **Backend** | `question_generator.py` → `llm_client.chat()` → DeepSeek V4 Pro (temp=0.8) |
| **Side effect** | Saves questions to `agent_state.json` under `daily_runs.DATE.sent` |
| **Duration** | ~5-10 seconds |
| **Fallback** | If LLM fails, uses 10 static template questions covering all 4 domains |

### 3.2 `build_and_execute` — Hybrid SQL + Python DB (KEY TOOL)

```
python -m agent.tools.build_and_execute <index>
```

Two code paths depending on table type:

| | |
|---|---|
| **Input** | Question index (0-4), reads question from `daily_runs.DATE.sent[index]` |
| **Step 1** | Detects table type from `tables_hint` |
| **Step 2a** | **SKU/SPU tables** (`product_center_business_sku_v3_info_di`, etc.): template-generates `SELECT * WHERE ym='YYYY-MM' LIMIT 20` — NO Claude Code call |
| **Step 2b** | **Operation tables** (`operation_center_wide_daily`, etc.): calls `claude -p "Write SQL..." --print` as subprocess with trimmed schema (1500 chars) |
| **Step 3** | Extracts SQL from CC output (regex: code blocks, inline SQL, raw SELECT) |
| **Step 4** | Executes SQL via `db_connector.execute_query()` |
| **Step 5** | On error: skips retry if SKU table column error (unfixable); otherwise sends error back to CC for fix |
| **Step 6** | Saves result (sql, status, columns, row_count, rows[0:20]) to state |
| **Output** | `{"ok": true/false, "sql": "...", "status": "ok|error", "row_count": N, "error": "..."}` |
| **Duration** | SKU: ~3s (no CC); operation: ~20-30s (CC subprocess 15s + DB 5s) |

**Why two paths:** SKU/SPU tables only support `SELECT *` with `WHERE ym=` — individual column refs fail at the SQL engine level. DeepSeek ignores the `SELECT * only` rule in prompts, so we template-generate directly. Operation tables have complex filters (品类分层, 门店汇总维度, date conversion) where CC's reasoning adds value.

**Why subprocess instead of tool calls:** DeepSeek V4 Pro can't reliably make Claude Code tool calls — it outputs "I need your approval" text. By calling `claude -p` as a subprocess, we get CC to output SQL text (which DeepSeek does well), then Python extracts and executes it (reliable). Subprocess uses `encoding="utf-8"` explicitly (default on Linux; required on Chinese Windows where system encoding is gbk).

### 3.3 `send_verification_emails` — Build HTML + send emails

```
python -m agent.tools.send_verification_emails
```

| | |
|---|---|
| **Input** | None (reads `daily_runs.DATE.sent` from state) |
| **Step 1** | Groups questions by `expert_email` |
| **Step 2** | For each group: builds HTML with question, SQL, result table (max 20 rows) |
| **Step 3** | Splits groups into batches of max 3 questions per email |
| **Step 4** | Sends via `email_sender._SimpleMailClient` |
| **Output** | `{"ok": true, "sent": N, "to": ["email1", ...]}` |
| **Duration** | ~5-10 seconds |

### 3.4 `db_query` — Execute SQL

```
python -m agent.tools.db_query "SELECT ..." [--limit N]
```

| | |
|---|---|
| **Input** | SQL string (single arg) |
| **Output (success)** | `[{"col1": "val1", ...}, ...]` — JSON array, truncated at 500 rows |
| **Output (error)** | `{"error": "message"}` |
| **Backend** | `src/tools/db_connector.py` → REST API at bdapp.qdama.cn (MD5 signature auth) |

### 3.5 `send_email` — Send single HTML email

```
python -m agent.tools.send_email --to "a@b.com" --subject "Subj" --body-file /tmp/b.html --sender-name "Name"
```

### 3.6 `check_feedback` — Fetch IMAP replies

```
python -m agent.tools.check_feedback --hours 24
```

| | |
|---|---|
| **Output** | `{"replies": [{subject, from, in_reply_to, body, date}, ...], "count": N}` |
| **Backend** | `feedback_collector._get_imap_client()` → IMAP at imap.exmail.qq.com:993 |

### 3.7 `manage_state` — Read/write state

```
python -m agent.tools.manage_state --get "daily_runs.2026-05-13.sent[0]"
python -m agent.tools.manage_state --merge "daily_runs.2026-05-13.sent[0]" '{"sql":"..."}'
python -m agent.tools.manage_state --set "key" '{"json":"value"}'
python -m agent.tools.manage_state --append "array_key" '{"item":...}'
```

| | |
|---|---|
| **Key syntax** | Dot notation with `[N]` array index support |
| **Backend** | Reads/writes `data/agent_state.json` atomically (temp file + os.replace) |

---

## 4. Phase 1: MORNING (run_morning.sh)

### Test mode

```bash
bash run_morning.sh --test     # Steps 1-2 only, no emails
bash run_morning.sh             # Full production run
bash run_test.sh                # Shortcut for --test
```

### Step 1: Generate Questions

Python calls DeepSeek API directly (no Claude Code). Scans `../BAKnowledgeBase3.1/2026年/`, reads skill files, generates 5 diverse questions covering 4 domains, saves to state.

**Duration:** ~5-10s

### Step 2: Execute Queries (×5)

For each question (index 0-4), `build_and_execute.py`:

**SKU/SPU tables** (detected from `tables_hint`):
1. Template-generates `SELECT * FROM ... WHERE ym='YYYY-MM' LIMIT 20` — no CC call
2. Executes SQL via DB REST API
3. Saves result to state
**Duration:** ~3s each

**Operation tables** (`operation_center_wide_daily`, etc.):
1. Calls `claude -p` as subprocess with trimmed schema (1500 chars) → CC outputs SQL text
2. Parses SQL from CC output (handles markdown fences, inline SQL, plain SELECT)
3. Executes SQL via DB REST API
4. On error: sends error back to CC, retries once (unless column error on unfixable table)
5. Saves SQL + columns + row_count + rows[0:20] to state
**Duration:** ~20-30s each

**Total:** ~2-3 min (depends on SKU/operation mix)

### Step 3: Send Verification Emails

`send_verification_emails.py` reads state, groups by expert, builds HTML tables from rows, sends via SMTP. Max 3 questions per email.

**Duration:** ~5-10s

### Expert Routing

| Domain | Expert | Email |
|--------|--------|-------|
| 商品 | 刘阗 | liutian1@qdama.cn |
| 运营 | 刘舒颖 | liushuying1@qdama.cn |
| 物流 | 周晶晶 | zhoujingjing@qdama.cn |
| 用户 | 刘舒颖 | liushuying1@qdama.cn |

---

## 5. Phase 2: HEARTBEAT (run_heartbeat.sh)

Triggered hourly at :07 via cron. Uses Claude Code (`-p --print --verbose`).

```
Step 1: python -m agent.tools.check_feedback --hours 2
Step 2: Classify each reply as correct/incorrect/unclear
Step 3: For incorrect with clear fixes → append correction to sql_templates.md | data_dictionary.md | CLAUDE.md
Step 4: Notify liangsheng1@qdama.cn ONLY if files changed. Exit silently otherwise.
```

**Evolution rules:** NEVER delete. Only APPEND with date stamp `## 修正 (evolved YYYY-MM-DD)`.

Note: Heartbeat still uses CC for the classification + evolution logic. If DeepSeek tool-use hallucination also blocks heartbeat, it will be refactored to the same hybrid pattern (CC text + Python execution).

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
          "question": "...",
          "domain": "商品",
          "tables_hint": "product_center_business_sku_v3_info_di",
          "fields_hint": "articleName, totalSaleAmt, areaName, ym",
          "expert_name": "刘阗",
          "expert_email": "liutian1@qdama.cn",
          "sql": "SELECT * FROM ...",
          "status": "success",
          "columns": ["col1", "col2"],
          "row_count": 10,
          "rows": [["val1", "val2"], ...],
          "reply_status": null,
          "reply_body": null
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

---

## 7. SQL Conventions

### Quoting
- Chinese fields: backtick — `` `销售额` ``
- English fields: NO quotes — `articleName`
- Table path: no quotes — `default_catalog.ads_business_analysis.operation_center_wide_daily`

### Dates
- 运营表 `日期`: timestamp ms → `FROM_UNIXTIME(\`日期\`/1000, 'yyyy-MM-dd')`
- 商品表 `ym`: string `'YYYY-MM'` → `ym = '2026-01'`

### Filters
- Store-level: `品类分层` = `'门店'`
- Category: `品类分层` = `'中分类'` / `'小分类'` / `'sku'`

### Known Quirks
- SKU/SPU tables: column refs fail → use `SELECT *` + `WHERE ym=`
- 运营表 percentages: strings like `'19.77%'` → `CAST(REPLACE(..., '%', '') AS DOUBLE) / 100`

---

## 8. Database Tables (大妈 only)

| Module | Table | Rows |
|--------|-------|------|
| 运营 ⭐ | `operation_center_wide_daily` | ~55K/mo |
| 运营 | `operation_center_dim_store_profile_di` | |
| 运营 | `operation_center_new_store_90d_weekly_*` | |
| 商品 ⭐ | `product_center_business_sku_v3_info_di` | ~10.6M |
| 商品 | `product_center_business_v3_info_di` | |

All under `default_catalog.ads_business_analysis.*`.

---

## 9. Self-Evolution Loop

```
Experts reply to emails
       │
       ▼
Heartbeat checks IMAP (hourly)
       │
       ▼
Classify: correct / incorrect / unclear
       │
       ├── correct → log, do nothing
       ├── unclear → send follow-up: "具体哪里错了？正确口径？"
       └── incorrect + clear fix:
              │
              ▼
           Append to skill file:
           - sql_templates.md     (SQL pattern wrong)
           - data_dictionary.md   (field meaning wrong)
           - CLAUDE.md            (general rule needed)
              │
              ▼
           Notify 梁晟 (liangsheng1@qdama.cn)
```

---

## 10. LLM Configuration

| Setting | Value |
|---------|-------|
| Model | DeepSeek V4 Pro |
| Claude Code endpoint | `ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic` |
| Auth | `ANTHROPIC_API_KEY` or `ANTHROPIC_AUTH_TOKEN` |
| Direct SDK | `anthropic.Anthropic` client, `messages.create()`, max_tokens=4096 |

**Two usage modes:**
1. **Direct SDK** (question_generator.py, data_retriever.py): `anthropic.Anthropic.messages.create()` for simple prompt→response
2. **Claude Code CLI** (build_and_execute.py, heartbeat): `claude -p "..." --print` for multi-turn reasoning

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

1. **Hybrid CC+Python for Step 2** — DeepSeek V4 Pro hallucinates "I need approval" text instead of making tool calls. CC is kept for SQL reasoning (text output), Python extracts SQL and executes it via subprocess. Reliable execution without giving up CC's reasoning.

2. **Template SQL for SKU/SPU tables** — These tables only support `SELECT *` with `WHERE ym=`. DeepSeek ignores the rule in prompts, so we skip CC entirely and template-generate: `SELECT * WHERE ym='YYYY-MM' LIMIT 20`. No CC call, no column errors, ~3s per question.

3. **Pure Python for Steps 1 and 3** — Question generation (prompt→JSON) and email sending (template fill) don't need CC's agentic loop. Direct SDK/script calls are faster and more reliable.

4. **State file as IPC** — Each step reads/writes `agent_state.json`. No data passed through shell variables. Enables independent testing of each step.

5. **5 questions not 10** — Reduced to mitigate total pipeline time (~2 min vs ~4 min).

6. **allow `["*"]` permissions** — Non-interactive cron mode can't handle prompts. Full allow + critical deny rules (rm -rf /, sudo, etc.).

7. **Test mode via CLI flag** — `--test` skips Step 3. Zero-cost validation before bothering experts.

---

## 13. Known Issues & Mitigations

| Issue | Mitigation |
|-------|------------|
| DeepSeek tool-use hallucination ("I need approval") | Hybrid architecture: CC outputs text, Python executes |
| SKU/SPU column refs fail ("Column cannot be resolved") | Template SQL: `SELECT * WHERE ym=` LIMIT 20. Skip CC entirely for these tables. |
| DeepSeek slow first token (~15s) + variable latency | Split into small focused calls; direct SDK where possible; schema trimmed to 1500 chars |
| SKU/SPU `SELECT *` on wide date range → DB 500 error | Always `LIMIT 20` in template SQL |
| Windows subprocess encoding (Python defaults to gbk) | Explicit `encoding="utf-8"` in subprocess.run() |
| DeepSeek CC retry timeout >120s | Smart skip: don't retry unfixable column errors on SKU tables |
| Heartbeat may also have tool-use issues | If so, refactor to same hybrid pattern |
| LLM question generation sometimes fails | Fallback to 10 static template questions |
