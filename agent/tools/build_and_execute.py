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


def _call_claude(sql_prompt: str, timeout: int = 180) -> str:
    """Call Claude Code to generate SQL. Returns raw stdout."""
    env = os.environ.copy()
    try:
        result = subprocess.run(
            ["claude", "-p", sql_prompt, "--print"],
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            cwd=str(ROOT),
            env=env,
            timeout=timeout,
        )
        if result.returncode != 0:
            stderr = result.stderr.strip() if result.stderr else ""
            raise RuntimeError(f"claude exited {result.returncode}: {stderr[:200]}")
        return (result.stdout or "").strip()
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"claude subprocess timed out after {timeout}s")
    except FileNotFoundError:
        raise RuntimeError("claude CLI not found in PATH")


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
    schema_short = schema[:1500]
    tables_hint = question.get('tables_hint', '')
    return f"""You are a SQL expert. Generate ONE SQL query for this question.

QUESTION: {question['question']}
TABLE: {tables_hint}
FIELDS: {question.get('fields_hint', '')}

SCHEMA REFERENCE:
{schema_short}

CRITICAL RULES:
- Chinese field names: backtick quotes, English fields: NO quotes
- Full table path: default_catalog.ads_business_analysis.<table>
- `品类分层`='门店' for store-level
- from_unixtime(`日期`/1000) for date conversion
- No LIMIT unless question asks for top N

Output ONLY the SQL query in a ```sql code block. Nothing else."""


def _generate_template_sql(question: dict) -> str:
    """Template-generate SQL for SKU/SPU tables that only support SELECT * + ym=."""
    import re as _re
    q = question['question']
    tables_hint = question.get('tables_hint', '')
    table = tables_hint.split(',')[0].strip() if tables_hint else 'product_center_business_sku_v3_info_di'

    # Extract YYYY-MM from question
    m = _re.search(r'(\d{4})年(\d{1,2})月|(\d{4})-(\d{2})', q)
    if m:
        if m.group(1):
            ym = f"{m.group(1)}-{int(m.group(2)):02d}"
        else:
            ym = f"{m.group(3)}-{m.group(4)}"
    else:
        from datetime import datetime
        ym = datetime.now().strftime('%Y-%m')

    return f"SELECT * FROM default_catalog.ads_business_analysis.{table} WHERE ym='{ym}' LIMIT 20"


def _is_sku_table(tables_hint: str) -> bool:
    return any(t in tables_hint for t in ['sku', 'spu'])


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

    # ── Generate SQL (template for SKU tables, Claude Code for others) ──
    tables_hint = question.get('tables_hint', '')
    if _is_sku_table(tables_hint):
        sql = _generate_template_sql(question)
        print(f"[INFO] SKU table detected, using template SQL (no CC call)", file=sys.stderr)
    else:
        prompt = _build_sql_prompt(question)
        try:
            cc_output = _call_claude(prompt)
        except RuntimeError as e:
            print(json.dumps({"error": f"Claude Code call failed: {e}"}, ensure_ascii=False))
            sys.exit(1)
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
        is_sku = _is_sku_table(question.get('tables_hint', ''))
        col_error = 'cannot be resolved' in error_msg

        if is_sku and col_error:
            # SKU tables only support SELECT * + ym= — CC can't fix column refs
            print("[WARN] SKU column error is unfixable, skipping retry", file=sys.stderr)
        else:
            retry_prompt = f"""Fix this SQL error.

Error: {error_msg}
Failed SQL: {sql}
Question: {question['question']}
Table: {question.get('tables_hint', '')}

Rules:
- Chinese fields: backtick quotes, English fields: NO quotes
- Full path: default_catalog.ads_business_analysis.<table>
- `品类分层`='门店' for store-level queries

Output ONLY the corrected SQL in ```sql block."""
            try:
                cc_output2 = _call_claude(retry_prompt, timeout=120)
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
            except RuntimeError as e:
                print(f"[WARN] Retry call failed: {e}", file=sys.stderr)

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
        "question_id": question.get("question_id") or question.get("id"),
        "status": status,
        "sql": sql,
        "columns": columns,
        "row_count": row_count,
        "error": result_error,
    }, ensure_ascii=False))
    sys.exit(0 if status == "success" else 1)


if __name__ == "__main__":
    main()
