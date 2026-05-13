"""
CLI tool: Generate questions via direct DeepSeek API call (no Claude Code overhead).
Usage: python -m agent.tools.generate_questions
Saves questions to state, prints summary JSON to stdout.
"""
import sys
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from agent.question_generator import generate_questions
from agent.config import STATE_FILE


def main():
    today = __import__('datetime').datetime.now().strftime('%Y-%m-%d')

    # Generate questions via direct DeepSeek call
    questions = generate_questions(dry_run=False)

    # Save to state
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r', encoding='utf-8') as f:
            state = json.load(f)
    else:
        state = {"version": 2, "daily_runs": {}}

    state["daily_runs"][today] = {
        "sent": questions,
        "replied": [],
        "correct": [],
        "incorrect": [],
        "evolved": [],
    }

    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    tmp = str(STATE_FILE) + ".tmp"
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    os.replace(tmp, STATE_FILE)

    print(json.dumps({
        "ok": True,
        "count": len(questions),
        "questions": [{"question_id": q["id"], "question": q["question"],
                        "domain": q["domain"], "expert_name": q["expert_name"],
                        "tables_hint": q.get("tables_hint", "")} for q in questions]
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
