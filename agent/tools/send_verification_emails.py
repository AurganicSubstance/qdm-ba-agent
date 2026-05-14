"""
CLI tool: Send verification emails for today's questions.
Usage: python -m agent.tools.send_verification_emails

Reads today's results from state, groups by expert, builds HTML, sends.
No Claude Code needed — deterministic template filling + SMTP.
"""
import sys
import json
import os
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from agent.email_sender import _SimpleMailClient
from agent.config import STATE_FILE


def _build_html(questions: list, expert_name: str, date_mmdd: str) -> str:
    """Build verification email HTML for one expert."""
    parts = [
        f'<h2>取数验证 — {date_mmdd}</h2>',
        f'<p><b>{expert_name}</b> 您好，以下是今日的自动取数结果。请验证数据是否正确：</p>',
        '<blockquote style="background:#f5f5f5;padding:10px;">',
        '<b>验证方式</b>：正确请回复<b>"正确"</b>；不对请回复<b>"不对"</b>并说明正确口径和字段。',
        '</blockquote>',
    ]

    for n, q in enumerate(questions, 1):
        status = q.get("status", "error")
        parts.append(f'<div style="margin:20px 0;padding:15px;border:1px solid #ddd;">')
        parts.append(f'<h3>问题 {n} ({q.get("domain", "")})</h3>')
        parts.append(f'<p><b>问题</b>: {q["question"]}</p>')
        parts.append(f'<p><b>涉及表</b>: {q.get("tables_hint", "")}</p>')

        sql = q.get("sql", "")
        if sql:
            parts.append(f'<p><b>SQL</b>:</p>')
            parts.append(f'<pre style="background:#2d2d2d;color:#f8f8f2;padding:10px;overflow-x:auto;">{sql}</pre>')

        if status == "success":
            columns = q.get("columns", [])
            rows = q.get("rows", [])
            row_count = q.get("row_count", len(rows))
            parts.append(f'<p><b>结果</b> ({row_count} rows):</p>')
            if rows:
                parts.append('<table border="1" cellpadding="4" cellspacing="0" style="border-collapse:collapse;">')
                parts.append('<tr style="background:#f0f0f0;">')
                for col in columns:
                    parts.append(f'<th>{col}</th>')
                parts.append('</tr>')
                for row in rows[:20]:
                    parts.append('<tr>')
                    for cell in row:
                        parts.append(f'<td>{cell}</td>')
                    parts.append('</tr>')
                parts.append('</table>')
        else:
            error = q.get("error", "Unknown error")
            parts.append(f'<p style="color:red;"><b>错误</b>: {error}</p>')

        parts.append('</div>')

    parts.append('<p style="color:#666;font-size:11px;">此邮件由取数验证Agent自动发送。请直接回复本邮件。</p>')
    return '\n'.join(parts)


def main():
    today = datetime.now()
    today_str = today.strftime('%Y-%m-%d')
    today_mmdd = today.strftime('%m/%d')

    # Read state
    if not os.path.exists(STATE_FILE):
        print(json.dumps({"error": "state file not found"}, ensure_ascii=False))
        sys.exit(1)

    with open(STATE_FILE, 'r', encoding='utf-8') as f:
        state = json.load(f)

    try:
        questions = state["daily_runs"][today_str]["sent"]
    except KeyError:
        print(json.dumps({"error": f"No questions found for {today_str}"}, ensure_ascii=False))
        sys.exit(1)

    # Group by expert
    groups = {}
    for q in questions:
        email = q.get("expert_email", "")
        name = q.get("expert_name", "")
        if email not in groups:
            groups[email] = {"name": name, "questions": []}
        groups[email]["questions"].append(q)

    # Send emails (max 3 questions per email)
    mail = _SimpleMailClient()
    sent = []
    message_id_map = {}  # question_id → message_id for state update

    for email, group in groups.items():
        name = group["name"]
        qs = group["questions"]

        # Split if more than 3
        for chunk_start in range(0, len(qs), 3):
            chunk = qs[chunk_start:chunk_start + 3]
            html = _build_html(chunk, name, today_mmdd)

            batch_num = f" ({chunk_start//3 + 1})" if len(qs) > 3 else ""
            subject = f"【取数验证】{today_mmdd} 数据取数验证 - {name}{batch_num}"

            try:
                for addr in email.split(","):
                    addr = addr.strip()
                    result = mail.send_email(
                        to=addr,
                        subject=subject,
                        body=html,
                        content_type="html",
                        sender_name="取数验证Agent",
                    )
                    msg_id = result.get("message_id") if isinstance(result, dict) else None
                    if msg_id:
                        for q in chunk:
                            message_id_map[q["question_id"]] = msg_id
                sent.append({"email": email, "name": name, "questions": len(chunk)})
                print(f"[SENT] {email} ({name}): {len(chunk)} questions", file=sys.stderr)
            except Exception as e:
                print(f"[ERROR] {email}: {e}", file=sys.stderr)

    # Write message_ids back to state
    if message_id_map:
        state = json.loads(Path(STATE_FILE).read_text(encoding="utf-8"))
        for entry in state["daily_runs"][today_str]["sent"]:
            qid = entry.get("question_id")
            if qid in message_id_map:
                entry["message_id"] = message_id_map[qid]
        tmp = str(STATE_FILE) + ".tmp"
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        os.replace(tmp, STATE_FILE)

    print(json.dumps({"ok": True, "sent": len(sent), "to": [s["email"] for s in sent]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
