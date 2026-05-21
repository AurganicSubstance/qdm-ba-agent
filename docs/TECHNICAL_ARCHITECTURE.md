# QDM BA Agent — Technical Architecture

> 钱大妈 (QDM) 业务分析自动取数、专家验证、自进化 Agent
> Last updated: 2026-05-20 (Cross-batch reply matching, 3-strategy matching, HTML entity cleanup, 1800s evolution timeout)

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
     ┌─────────────┼─────────────┐     python -m agent.tools
     │             │             │     .run_evolution
  Step 1      Step 2 ×5     Step 3         │
  (Pure       (CC→SQL      (Pure      ┌────┴────┐
   Python)     Py→exec)     Python)   │         │
     │             │             │   Python   OpenCode
     ▼             ▼             ▼   (plumbing (agent:
  Direct       Claude Code   Template IMAP,     read skill
  DeepSeek     → SQL text    → HTML   classify, files,
  API call     → Python DB   → SMTP   backup,   edit them,
                                       notify)   record
                                                 state)
```

**Hybrid architecture — Claude Code for reasoning, Python for execution:**

| Step | Reasoning | Execution | Why |
|------|-----------|-----------|-----|
| 1. Question generation | — | Python (direct DeepSeek SDK) | Simple prompt→JSON, no tools needed, ~5s |
| 2. SQL generation + DB | Claude Code (`-p --print`) | Python (`subprocess` → extract SQL → DB) | CC reasons about schema+question, Python runs DB |
| 3. Email sending | — | Python (template fill + SMTP) | Deterministic, no LLM reasoning needed |
| Heartbeat: feedback + classify | — | Python (IMAP + direct DeepSeek SDK) | Routine: fetch emails, match reply headers, 3-label classify |
| Heartbeat: evolve skills | OpenCode (`opencode run`) | Python (backup + change detect + notify) | OpenCode reads skill files, restructures/rewrites; Python handles plumbing |


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
│       ├── run_evolution.py          # CLI: full heartbeat: feedback → evolve → notify
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
├── backups/
│   └── skills/                 # Skill file backups before evolution (local, gitignored)
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

**Why subprocess instead of tool calls:** DeepSeek V4 Pro can't reliably make Claude Code tool calls — it outputs "I need your approval" text. By calling `claude -p` as a subprocess, we get CC to output SQL text (which DeepSeek does well), then Python extracts and executes it (reliable). Subprocess uses `encoding="utf-8"` explicitly (default on Linux; required on Chinese Windows where system encoding is gbk). OpenCode can substitute via the same subprocess pattern — see §13 for comparison and swap instructions.

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

Triggered hourly at :07 via cron. Pure Python orchestration with OpenCode subprocess for evolution editing.

```
python -m agent.tools.run_evolution
```

### Flow

```
1. _backup_skills()
   └── Copy current skill files to backups/skills/YYYY-MM-DD_HHMMSS/ (local, gitignored)

2. collect_feedback() (from feedback_collector.py)
   ├── Load state, collect ALL active batches (not just latest)
   ├── Build combined message_id_map + per-batch pending lists
   ├── IMAP fetch (7-day window)
   ├── THREE-STRATEGY match replies:
   │   ├── Strategy 1: Message-ID header (in_reply_to) — exact, most reliable
   │   ├── Strategy 2: Subject date ("取数验证" + "MM/DD") + expert — tries EACH batch's date
   │   └── Strategy 3: Follow-up subject ("请帮忙澄清取数错误细节") — matches any entry for that expert, preferring unclear > incorrect+evolved > pending
   ├── Classify: heuristic pre-check → LLM (direct DeepSeek SDK)
   │   ├── Pre-check: "不对" + SQL/table refs + >30 Chinese chars → "incorrect" (no LLM)
   │   ├── Full reply body, HTML entities cleaned (&nbsp; → space etc)
   │   └── LLM 3-label: correct / incorrect / unclear
   ├── Send follow-up email for unclear replies (only if not dry-run)
   └── Return summary with actionable question_ids + batch_dates list

3. For each actionable (incorrect + detailed) reply:
   ├── Build prompt with expert feedback + file paths
   ├── Call OpenCode subprocess → reads skill files, edits them, records state
   └── Detect which files changed (mtime comparison)

4. Send notification to liangsheng1@qdama.cn ONLY if files changed
```

### Cross-Batch Processing

`collect_feedback()` collects **all** active batches (not just the latest). Each batch's pending entries are built into per-batch lists, and a combined `message_id_map` spans all batches. Strategy 2 tries each batch's date against the reply subject. The summary returns `batch_dates: [list]` instead of a single `batch_date`.

### Pending Entry Selection

| Status | Eligible? | Reason |
|--------|-----------|--------|
| `pending` | Yes | Not yet replied |
| `unclear` | Yes | Re-evaluable — expert may reply again with more detail, or improved classifier may re-score |
| `incorrect` + `evolved=False` | Yes | Expert replied but evolution hasn't processed it yet |
| `incorrect` + `evolved=True` | No | Already evolved |
| `correct` | No | No action needed |

### Reply Matching — Three Strategies

**Strategy 1: Message-ID header** — The verification email's `Message-ID` header is stored in state. When the expert replies, their email client includes it in `In-Reply-To`. Direct lookup in combined `message_id_map` across all active batches.

**Strategy 2: Subject date + expert fallback** — Some email clients strip `In-Reply-To`. For each active batch date, checks if the reply subject contains `取数验证` + that batch's date (both `05-15` and `05/15` formats), then matches by expert email or name. Iterates all pending entries in that batch.

**Strategy 3: Follow-up reply** — When a follow-up email (`Re: 【取数验证】请帮忙澄清取数错误细节`) was sent to an expert, their reply to it won't contain a batch date. Strategy 3 searches **all** entries (not just pending) for that expert across all batches, preferring `unclear` → `incorrect+evolved` → `pending`. Handles the case where the expert clarifies after the question was already evolved.

**Caveat**: Multiple questions per email share the same `message_id`. Strategy 1 maps message_id to the last entry (dict overwrite), so only one question per email is matched by Strategy 1. Strategies 2 and 3 have no such limitation.

### Reply Classification

**Heuristic pre-check** (runs before LLM, skips LLM on match):
- Reply contains negative words: `不对`, `错了`, `不正确`, `有问题`, `错误`
- AND contains SQL keywords (`SELECT`, `FROM`, `WHERE`, `JOIN`, `GROUP BY`) or known table references
- AND has >30 Chinese characters
- → Immediately classified as `incorrect` — no LLM call needed

**LLM classification** (fallback):
- Full reply body passed without truncation; HTML entities cleaned (`&nbsp;` → ` `, `&gt;` → `>`, etc.)
- LLM prompt explicitly instructs: SQL code in a reply = `incorrect` not `unclear`
- Exception handler: if LLM call fails, uses heuristic fallback (>50 Chinese chars + negative words → `incorrect`)

### Evolution Editing

OpenCode subprocess timeout: **1800s** (30 min). Expert reply body passed in full (no char truncation) with HTML entities cleaned. Prompt includes question, domain, SQL used, expert reply, and paths to the 3 evolvable files. OpenCode reads `SKILL.md` for context, then edits `sql_templates.md`, `data_dictionary.md`, and/or `CLAUDE.md` as needed. Python detects changes via mtime comparison before/after.

### Architecture

| Component | What | How |
|-----------|------|-----|
| IMAP fetch + classification | Python | `feedback_collector.collect_feedback()` — heuristic pre-check + direct DeepSeek SDK for 3-label classify |
| Skill file backup | Python | `shutil.copy2()` to `backups/skills/TIMESTAMP/` — local safety net, gitignored |
| Evolution editing | OpenCode agent | `opencode run --model deepseek/deepseek-v4-pro` — reads skill files, restructures/rewrites freely within 3 files |
| File change detection | Python | mtime comparison before/after OpenCode run |
| Notification email | Python | SMTP via `_SimpleMailClient` |

### OpenCode Scope

OpenCode may ONLY edit these 3 files:
- `.claude/skills/dataqueryplus/references/sql_templates.md`
- `.claude/skills/dataqueryplus/references/data_dictionary.md`
- `CLAUDE.md` (project root)

It may read `SKILL.md` for context. It must NOT touch agent code, config, state files, or anything else. State records go through `manage_state` Bash calls.

### Why OpenCode with tool access

The previous design (text-in/text-out via JSON) limited context — Python had to guess which file tails to send. With real tool access, OpenCode reads exactly what it needs from the skill files, makes nuanced decisions about which file(s) to touch, and restructures freely. Python snapshots before/after to detect what changed for notification.

---

## 6. State File Schema

`data/agent_state.json`:

```json
{
  "version": 2,
  "daily_runs": {
    "2026-05-15": {
      "sent": [
        {
          "question_id": "20260515_01",
          "question": "...",
          "domain": "商品",
          "tables_hint": "product_center_business_sku_v3_info_di",
          "fields_hint": "articleName, totalSaleAmt, areaName, ym",
          "expert_name": "刘阗",
          "expert_email": "liutian1@qdama.cn",
          "message_id": "<20260515101234.a1b2c3@qdama.cn>",
          "sql": "SELECT * FROM ...",
          "status": "success",
          "columns": ["col1", "col2"],
          "row_count": 10,
          "rows": [{"col1": "val1", "col2": "val2"}, ...],
          "reply_status": "incorrect",
          "reply_body": "SQL没加品类分层='门店'导致数据重复...",
          "reply_from": "liutian1@qdama.cn",
          "replied_at": "2026-05-15T10:30:00",
          "followup_sent": false,
          "evolved": true,
          "evolution_target": "sql_templates",
          "evolution_description": "运营宽表门店级查询补充品类分层过滤条件"
        }
      ],
      "evolved": [
        {"question_id": "20260515_01", "action": "sql_templates", "description": "运营宽表门店级查询补充品类分层过滤条件"}
      ]
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
           OpenCode agent edits skill files:
           - sql_templates.md     (SQL pattern wrong)
           - data_dictionary.md   (field meaning wrong)
           - CLAUDE.md            (general rule needed)
           (reads current state, restructures/rewrites freely)
              │
              ▼
           Python detects file changes (mtime diff)
              │
              ▼
           Notify 梁晟 (liangsheng1@qdama.cn)
           with expert name, reply, file changed, diff
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
#30 16 * * * cd /root/qdm-ba-agent && bash run_morning.sh >> logs/morning.log 2>&1

# Heartbeat — every hour at :07
#7 * * * * cd /root/qdm-ba-agent && bash run_heartbeat.sh >> logs/heartbeat.log 2>&1
```

> **Status 2026-05-20**: Both jobs commented out for review. Re-enable by removing `#` prefix.

### Re-enable

```bash
ssh root@8.138.41.205 "crontab -l | sed 's/^#30 16/30 16/; s/^#7 \* \* \*/7 * * */' | crontab -"
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

## 13. OpenCode — Alternative to Claude Code

OpenCode is an alternative AI coding CLI that can replace Claude Code in the hybrid architecture if needed. Both call DeepSeek V4 Pro under the hood — the difference is the CLI wrapper.

### CLI Equivalent

```bash
# Claude Code (current)
claude -p "<prompt>" --print

# OpenCode (equivalent)
opencode run --model deepseek/deepseek-v4-pro "<prompt>"
```

### Auth

OpenCode uses its own credential store at `~/.local/share/opencode/auth.json`:

```json
{"deepseek": {"type": "api", "key": "sk-..."}}
```

Claude Code uses `ANTHROPIC_API_KEY` / `ANTHROPIC_AUTH_TOKEN` env vars pointing at `ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic`.

### SQL Quality Comparison (tested 2026-05-14)

Both generate functionally correct SQL. Key differences observed across 2 test runs:

| Aspect | Claude Code | OpenCode |
|--------|------------|----------|
| Backtick quoting of Chinese fields | Inconsistent — sometimes drops backticks on `日期` inside function calls | Consistent — backtick on ALL Chinese fields everywhere |
| Date filter style | Varies (`FROM_UNIXTIME(..., 'yyyy-MM') =` vs range) | Consistently uses range (`>= ... AND < ...`) |
| Div-zero handling | `NULLIF(SUM(...), 0)` — cleaner | `HAVING SUM(...) > 0` — works, slightly more verbose |
| SQL block format | Clean ` ```sql ` blocks | Same, with CLI noise prefix (`> build · deepseek-v4-pro`) |

### Speed Comparison (both DeepSeek V4 Pro, same prompt, 2 runs)

| Run | Claude Code | OpenCode |
|-----|------------|----------|
| #1 (simple aggregation) | 25.3s | 36.9s |
| #2 (top-N with percentage) | 46.2s | 40.0s |
| **Average** | **35.8s** | **38.5s** |

No meaningful speed difference. Both are bottlenecked by DeepSeek API latency, not CLI startup overhead.

### Code Changes Required to Swap

In `agent/tools/build_and_execute.py`, change the `_call_claude()` function:

```python
def _call_llm(sql_prompt: str, timeout: int = 180) -> str:
    """Call LLM CLI to generate SQL. Supports both Claude Code and OpenCode."""
    import shutil
    # Auto-detect: prefer claude, fall back to opencode
    if shutil.which("claude"):
        cmd = ["claude", "-p", sql_prompt, "--print"]
    elif shutil.which("opencode"):
        cmd = ["opencode", "run", "--model", "deepseek/deepseek-v4-pro", sql_prompt]
    else:
        raise RuntimeError("No LLM CLI found (tried claude, opencode)")

    result = subprocess.run(
        cmd,
        capture_output=True, text=True,
        encoding="utf-8", errors="replace",
        cwd=str(ROOT),
        env=os.environ.copy(),
        timeout=timeout,
    )
    if result.returncode != 0:
        stderr = result.stderr.strip() if result.stderr else ""
        raise RuntimeError(f"LLM CLI exited {result.returncode}: {stderr[:200]}")
    return (result.stdout or "").strip()
```

`_extract_sql()` needs no changes — both output ` ```sql ` blocks.

### Verdict

OpenCode is a viable drop-in replacement. It's slightly more disciplined about SQL quoting rules but has no compelling advantage over Claude Code for this use case. The choice comes down to:
- **Stick with Claude Code**: already proven in pipeline, slightly cleaner output, fewer moving parts
- **Swap to OpenCode**: if CC licensing changes, if you want independent auth management, or if CC's permission system causes issues in cron

---

## 14. Known Issues & Mitigations

| Issue | Mitigation |
|-------|------------|
| DeepSeek tool-use hallucination ("I need approval") | Hybrid architecture: CC outputs text, Python executes |
| SKU/SPU column refs fail ("Column cannot be resolved") | Template SQL: `SELECT * WHERE ym=` LIMIT 20. Skip CC entirely for these tables. |
| DeepSeek slow first token (~15s) + variable latency | Split into small focused calls; direct SDK where possible; schema trimmed to 1500 chars |
| SKU/SPU `SELECT *` on wide date range → DB 500 error | Always `LIMIT 20` in template SQL |
| Windows subprocess encoding (Python defaults to gbk) | Explicit `encoding="utf-8"` in subprocess.run() |
| DeepSeek CC retry timeout >120s | Smart skip: don't retry unfixable column errors on SKU tables |
| ~~Heartbeat tool-use hallucination~~ | RESOLVED 2026-05-14: Heartbeat refactored to pure Python + OpenCode subprocess (see §5) |
| LLM question generation sometimes fails | Fallback to 10 static template questions |
| `question_id` vs `id` key mismatch across pipeline | RESOLVED 2026-05-16: `generate_questions` now sets both keys; all consumers use `.get()` fallback |
| `reply_status` never initialized to "pending" | RESOLVED 2026-05-16: `send_verification_emails` sets `reply_status="pending"` when writing `message_id` |
| `message_id` never saved to state (KeyError crash) | RESOLVED 2026-05-16: fixed `question_id`/`id` key mismatch in `send_verification_emails` |
| LLM classifies detailed SQL replies as "unclear" | RESOLVED 2026-05-16: heuristic pre-check (不对 + SQL → incorrect), full reply body no truncation |
| `unclear` entries excluded from re-evaluation | RESOLVED 2026-05-16: `unclear` entries now included in pending so expert's follow-up reply can re-classify |
| Multiple questions per email share one message_id | KNOWN: Strategy 1 (dict) only keeps last entry per message_id. Strategies 2+3 handle the rest. |
| ~~Heartbeat only checked latest batch~~ | RESOLVED 2026-05-20: `collect_feedback` now collects all active batches; combined `message_id_map`; Strategy 2 tries each batch's date; summary returns `batch_dates` list |
| ~~OpenCode 300s timeout on huge prompts~~ | RESOLVED 2026-05-20: timeout raised to 1800s; HTML entities cleaned from reply bodies; no char truncation |
| ~~Follow-up replies unmatched~~ | RESOLVED 2026-05-20: Strategy 3 matches follow-up replies ("请帮忙澄清取数错误细节") to the expert's entries across all batches |
| ~~`question_id` NameError in evolution prompt~~ | RESOLVED 2026-05-20: restored `question_id` variable after accidental removal during HTML cleanup refactor |
