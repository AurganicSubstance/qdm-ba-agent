"""
Skill Evolver.
When an expert gives clear feedback about what's wrong and how to fix it,
this module updates the dataqueryplus skill files to incorporate the fix.
"""
import os
import json
import re
from datetime import datetime
from pathlib import Path

from agent.config import PROJECT_ROOT, EVOLUTION_LOG
from agent.llm_client import chat_json as llm_chat_json

SKILL_DIR = PROJECT_ROOT / ".claude" / "skills" / "dataqueryplus"
SKILL_MD = SKILL_DIR / "SKILL.md"
SQL_TEMPLATES = SKILL_DIR / "references" / "sql_templates.md"
DATA_DICT = SKILL_DIR / "references" / "data_dictionary.md"
CLAUDE_MD = PROJECT_ROOT / "CLAUDE.md"


def _load_state() -> dict:
    from agent.config import STATE_FILE
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_state(state: dict):
    from agent.config import STATE_FILE
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def evolve_from_feedback(question_id: str, dry_run: bool = False) -> dict:
    """
    Given a question_id with INCORRECT expert feedback,
    analyze the feedback and update the appropriate skill file.

    Returns: {"action": "sql_templates"|"data_dictionary"|"claude_md"|"none",
              "description": str, "file_updated": str}
    """
    state = _load_state()

    # Find the entry
    entry = None
    for day_key in state.get("daily_runs", {}):
        for e in state["daily_runs"][day_key].get("sent", []):
            if e["question_id"] == question_id:
                entry = e
                break

    if not entry or entry.get("reply_status") != "incorrect":
        return {"action": "none", "description": "No actionable incorrect feedback found", "file_updated": ""}

    question = entry["question"]
    sql = entry.get("sql", "")
    feedback = entry.get("reply_body", "")

    # Use LLM to determine what needs to change
    action = _analyze_feedback(question, sql, feedback)

    if dry_run:
        return action

    # Apply the change
    if action["action"] == "sql_templates":
        _append_sql_template(question, sql, feedback, action)
    elif action["action"] == "data_dictionary":
        _update_data_dict(feedback, action)
    elif action["action"] == "claude_md":
        _update_claude_md(question, feedback, action)

    # Log evolution
    _log_evolution(question_id, question, feedback, action)

    # Update state
    entry["evolved"] = True
    entry["evolution_action"] = action["action"]
    entry["evolution_description"] = action["description"]
    _save_state(state)

    return action


def _analyze_feedback(question: str, sql: str, feedback: str) -> dict:
    """Use LLM to determine what type of skill update is needed."""
    prompt = f"""Analyze this data retrieval error feedback and determine:
1. What type of skill file needs updating
2. What specific change should be made

Question: {question}
SQL used: {sql}
Expert feedback: {feedback}

Options:
- sql_templates: The SQL pattern/template is wrong or missing → update sql_templates.md
- data_dictionary: The field name/meaning/usage is wrong → update data_dictionary.md
- claude_md: A general data retrieval rule/principle needs to be added → update CLAUDE.md
- none: No clear actionable change

Reply with JSON:
{{"action": "sql_templates|data_dictionary|claude_md|none",
 "description": "one-line summary of what changed",
 "content_to_add": "the markdown content to append to the file"}}"""

    try:
        return llm_chat_json(
            system_prompt="You are a technical documentation assistant. Reply with valid JSON only, no markdown fences.",
            user_message=prompt,
            temperature=0.3,
        )
    except Exception as e:
        return {"action": "none", "description": f"LLM analysis failed: {e}", "content_to_add": ""}


def _append_sql_template(question: str, sql: str, feedback: str, action: dict):
    """Append a new or corrected SQL template to sql_templates.md."""
    content = action.get("content_to_add", "")
    if not content:
        return

    today = datetime.now().strftime("%Y-%m-%d")
    with open(SQL_TEMPLATES, "a", encoding="utf-8") as f:
        f.write(f"""\n\n---
## 修正模板 (evolved {today})

{content}

**原始问题**: {question}
**专家反馈**: {feedback[:300]}
""")


def _update_data_dict(feedback: str, action: dict):
    """Append a field correction to data_dictionary.md."""
    content = action.get("content_to_add", "")
    if not content:
        return

    today = datetime.now().strftime("%Y-%m-%d")
    with open(DATA_DICT, "a", encoding="utf-8") as f:
        f.write(f"""\n\n---
## 字段口径修正 (evolved {today})

{content}
""")


def _update_claude_md(question: str, feedback: str, action: dict):
    """Append a data retrieval rule to CLAUDE.md."""
    content = action.get("content_to_add", "")
    if not content:
        return

    today = datetime.now().strftime("%Y-%m-%d")

    # Create CLAUDE.md if it doesn't exist
    if not os.path.exists(CLAUDE_MD):
        with open(CLAUDE_MD, "w", encoding="utf-8") as f:
            f.write("# QDM BA Agent - Data Retrieval Rules\n\n")

    with open(CLAUDE_MD, "a", encoding="utf-8") as f:
        f.write(f"""\n## 取数规则 (evolved {today})

{content}

> 问题: {question}
> 专家反馈: {feedback[:200]}
""")


def _log_evolution(question_id: str, question: str, feedback: str, action: dict):
    """Log the evolution to evolution_log.json."""
    log = []
    if os.path.exists(EVOLUTION_LOG):
        with open(EVOLUTION_LOG, "r", encoding="utf-8") as f:
            log = json.load(f)

    log.append({
        "timestamp": datetime.now().isoformat(),
        "question_id": question_id,
        "question": question,
        "feedback": feedback[:500],
        "action": action.get("action", "none"),
        "description": action.get("description", ""),
    })

    os.makedirs(os.path.dirname(EVOLUTION_LOG), exist_ok=True)
    with open(EVOLUTION_LOG, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)
