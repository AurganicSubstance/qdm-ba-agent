"""
CLI tool: Build SQL via Claude Code (reasoning) → execute via Python.
Usage: python -m agent.tools.build_and_execute <index>

Flow:
1. Read question from state
2. Call claude -p to generate SQL (structured output)
3. Extract SQL from response (strip markdown/text)
4. Execute via db_query
5. Retry once on error
6. Save result to state
"""
import sys
import json
import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from src.tools.db_connector import create_connector_from_config, DBConnectorError
from agent.config import STATE_FILE, MAX_RESULT_ROWS


def _read_skill_schema() -> str:
    skill_dir = ROOT / ".claude" / "skills" / "dataqueryplus"
    parts = []
    for name in ["references/data_dictionary.md", "references/sql_templates.md"]:
        path = skill_dir / name
        if path.exists():
            content = path.read_text(encoding="utf-8")
            parts.append(content)
    return "\n\n".join(parts)


def _call_claude(sql_prompt: str) -> str:
    """Call Claude Code to generate SQL. Returns raw stdout."""
    env = os.environ.copy()
    result = subprocess.run(
        ["claude", "-p", sql_prompt, "--print"],
        capture_output=True, text=True,
        cwd=str(ROOT),
        env=env,
        timeout=120,
    )
    return result.stdout.strip()


def _extract_sql(text: str) -> str:
    """Extract SQL from Claude Code output. Handles markdown, chinese text, etc."""
    # Try to find SQL in ```sql ... ``` block first
    m = re.search(r"```(?:sql)?\s*\n?(.*?)\n?```", text, re.DOTALL | re.IGNORECASE)
    if m:
        sql = m.group(1).strip()
        if _looks_like_sql(sql):
            return _clean_sql(sql)

    # Try to find SQL in backtick-wrapped inline
    m = re.search(r"`(SELECT\b[^`]+)`", text, re.IGNORECASE | re.DOTALL)
    if m:
        sql = m.group(1).strip()
        if _looks_like_sql(sql):
            return _clean_sql(sql)

    # Fallback: find first SELECT statement
    m = re.search(r"(SELECT\b.+?)(?:\n\n|\n\S|$)", text, re.IGNORECASE | re.DOTALL)
    if m:
        sql = m.group(1).strip()
        if _looks_like_sql(sql):
            return _clean_sql(sql)

    # Last resort: return the whole text and hope db_query rejects it cleanly
    return text.strip()


def _looks_like_sql(text: str) -> bool:
    return bool(re.search(r"\bSELECT\b", text, re.IGNORECASE))


def _clean_sql(sql: str) -> str:
    sql = sql.strip().rstrip(";")
    return sql


def _run_db(sql: str):
    """Execute SQL against the database."""
    db = create_connector_from_config()
    data = db.execute_query(sql)
    if not data:
        return []
    if len(data) > MAX_RESULT_ROWS:
        data = data[:MAX_RESULT_ROWS]
    return data


def _build_sql_prompt(question: dict) -> str:
    schema = _read_skill_schema()
    return f"""You are a SQL expert. Generate ONE SQL query for this question.

QUESTION: {question['question']}
TABLE: {question.get('tables_hint', '')}
FIELDS: {question.get('fields_hint', '')}

SCHEMA REFERENCE:
{schema[:3000]}

CRITICAL RULES:
- Chinese field names: backtick quotes (e.g. \\`销售额\\`)
- English field names: NO quotes (e.g. articleName)
- Full table path: default_catalog.ads_business_analysis.<table>
- \\`品类分层\\`='门店' for store-level
- from_unixtime(\\`日期\\`/1000) for date conversion
- SKU/SPU tables: SELECT * only (column refs fail)
- No LIMIT unless question asks for top N

Output ONLY the SQL query in a ```sql code block. Nothing else."""


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "usage: python -m agent.tools.build_and_execute <index>"}, ensure_ascii=False))
        sys.exit(1)

    idx = int(sys.argv[1])
    today = __import__('datetime').datetime.now().strftime('%Y-%m-%d')

    # Read question from state
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r', encoding='utf-8') as f:
            state = json.load(f)
    else:
        print(json.dumps({"error": "state file not found"}, ensure_ascii=False))
        sys.exit(1)

    try:
        question = state["daily_runs"][today]["sent"][idx]
    except (KeyError, IndexError):
        print(json.dumps({"error": f"Question not found: {today}[{idx}]"}, ensure_ascii=False))
        sys.exit(1)

    # ── Generate SQL via Claude Code ──
    prompt = _build_sql_prompt(question)
    cc_output = _call_claude(prompt)

    # Extract SQL from CC output
    sql = _extract_sql(cc_output)
    if not sql or not _looks_like_sql(sql):
        print(json.dumps({"error": "Failed to extract SQL from Claude Code output", "cc_output": cc_output[:500]}, ensure_ascii=False))
        sys.exit(1)

    # ── Execute SQL ──
    try:
        data = _run_db(sql)
    except DBConnectorError as e:
        data = None
        error_msg = str(e)
    except Exception as e:
        data = None
        error_msg = f"Unexpected: {e}"

    # ── Retry once on error ──
    if data is None:
        print(f"[WARN] First attempt failed: {error_msg}, retrying...", file=sys.stderr)
        retry_prompt = f"""The following SQL failed with error: {error_msg}

Failed SQL:
{sql}

Question: {question['question']}
Table: {question.get('tables_hint', '')}

Schema:
{_read_skill_schema()[:3000]}

Fix the error and output ONLY the corrected SQL in a ```sql block. Nothing else."""
        cc_output2 = _call_claude(retry_prompt)
        sql2 = _extract_sql(cc_output2)
        if sql2 and _looks_like_sql(sql2):
            sql = sql2
            try:
                data = _run_db(sql)
            except DBConnectorError as e:
                data = None
                error_msg = str(e)
            except Exception as e:
                data = None
                error_msg = f"Unexpected: {e}"

    # ── Format result ──
    if data is not None:
        columns = list(data[0].keys()) if data else []
        rows = [[row.get(c) for c in columns] for row in data]
        status = "success"
        row_count = len(rows)
        result_error = None
    else:
        columns = []
        rows = []
        status = "error"
        row_count = 0
        result_error = error_msg

    # Save to state
    question["sql"] = sql
    question["status"] = status
    question["columns"] = columns
    question["row_count"] = row_count
    question["rows"] = rows
    if result_error:
        question["error"] = result_error

    tmp = str(STATE_FILE) + ".tmp"
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    os.replace(tmp, STATE_FILE)

    print(json.dumps({
        "ok": status == "success",
        "question_id": question["id"],
        "status": status,
        "sql": sql,
        "columns": columns,
        "row_count": row_count,
        "error": result_error,
    }, ensure_ascii=False))
    sys.exit(0 if status == "success" else 1)


if __name__ == "__main__":
    main()
