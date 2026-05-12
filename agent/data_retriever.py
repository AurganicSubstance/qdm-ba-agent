"""
Data Retriever Agent.
Takes a question → reads the dataqueryplus skill → builds SQL via LLM →
executes via db_connector → returns table + SQL.

The skill is the SINGLE SOURCE OF TRUTH for table schemas and SQL patterns.
No table schemas are hardcoded here — all knowledge comes from the skill files.
"""
import sys
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from src.tools.db_connector import create_connector_from_config, DBConnectorError
from agent.config import MAX_RESULT_ROWS
from agent.llm_client import chat as llm_chat
import json
import re

SKILL_DIR = ROOT / ".claude" / "skills" / "dataqueryplus"


def _read_skill_context() -> str:
    """Read the current skill files as context for SQL generation."""
    parts = []
    for name in ["SKILL.md", "references/data_dictionary.md", "references/sql_templates.md"]:
        path = SKILL_DIR / name
        if path.exists():
            parts.append(path.read_text(encoding="utf-8"))
    return "\n\n".join(parts)


def _build_sql(question: dict) -> str:
    """Use LLM to build a SQL query. Skill files provide all table/schema knowledge."""
    skill_context = _read_skill_context()

    prompt = f"""You are a SQL expert. Write a SINGLE SQL query for this data retrieval question.

Below is the COMPLETE DATAQUERYPLUS SKILL — the single source of truth for all table schemas,
field names, SQL patterns, and rules. Use ONLY the tables and fields documented here:

---
{skill_context}
---

SQL RULES:
1. Return ONLY the SQL query, no markdown, no backticks, no explanations
2. Default to the 大妈 (Dama) operation_center_wide_daily table unless the question is about users/orders
3. Follow ALL conventions from the skill (timestamp dates, Chinese field names, percentage handling, etc.)
4. ORDER BY date/group appropriately
5. Round decimal results to 2-4 places
6. Do NOT use LIMIT unless question asks for "top N"

Question: {question['question']}
Hint tables: {question.get('tables_hint', '')}
Hint fields: {question.get('fields_hint', '')}
Expected output: {question.get('expected_output_type', '')}"""

    try:
        sql = llm_chat(
            system_prompt="You are a SQL expert. Reply with ONLY the SQL query, no markdown, no backticks, no explanations.",
            user_message=prompt,
            temperature=0.1,
        ).strip()
        sql = re.sub(r'^```(?:sql)?\s*', '', sql)
        sql = re.sub(r'\s*```$', '', sql)
        sql = sql.strip().rstrip(";")
        return sql
    except Exception as e:
        raise RuntimeError(f"SQL generation failed: {e}")


def execute_question(question: dict) -> dict:
    """
    Execute a data retrieval question.

    Returns: {
        "question_id": str,
        "status": "success" | "error",
        "sql": str,
        "columns": [str],
        "rows": [[...]],
        "row_count": int,
        "error": str | None,
    }
    """
    result = {
        "question_id": question["id"],
        "status": "error",
        "sql": "",
        "columns": [],
        "rows": [],
        "row_count": 0,
        "error": None,
    }

    try:
        sql = _build_sql(question)
        result["sql"] = sql

        db = create_connector_from_config()
        data = db.execute_query(sql)

        if not data:
            result["status"] = "success"
            result["error"] = "Query returned 0 rows"
            return result

        # Truncate if too many rows
        if len(data) > MAX_RESULT_ROWS:
            data = data[:MAX_RESULT_ROWS]

        columns = list(data[0].keys())
        rows = [[row.get(c) for c in columns] for row in data]

        result["status"] = "success"
        result["columns"] = columns
        result["rows"] = rows
        result["row_count"] = len(rows)

    except DBConnectorError as e:
        result["error"] = f"DB Error: {e}"
    except Exception as e:
        result["error"] = f"Error: {e}"

    return result
