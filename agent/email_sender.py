"""
Email Sender.
Sends question + SQL + result table to the appropriate human expert.
Reuses the MailClient from the BAKnowledgeBase3.1 email_bot.
"""
import sys
import os
import json
import smtplib
import ssl
import uuid
import time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import Header
from email.utils import formataddr
from datetime import datetime
from typing import Optional

# Add email_bot path
_KB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "BAKnowledgeBase3.1")
if os.path.isdir(_KB_PATH):
    sys.path.insert(0, _KB_PATH)

from agent.config import MAIL_CONFIG, STATE_FILE


def _get_mail_client():
    """Lazy-import MailClient from email_bot."""
    try:
        from qwen_md_grader.email_bot.mail_client import MailClient
    except ImportError:
        # Fallback: use standalone simplified client
        return _SimpleMailClient()
    return MailClient(
        imap_host=MAIL_CONFIG["imap_host"],
        imap_port=MAIL_CONFIG["imap_port"],
        smtp_host=MAIL_CONFIG["smtp_host"],
        smtp_port=MAIL_CONFIG["smtp_port"],
        username=MAIL_CONFIG["username"],
        password=MAIL_CONFIG["password"],
    )


class _SimpleMailClient:
    """Standalone SMTP-only mail client (no IMAP needed for sending)."""

    def send_email(self, to, subject, body, cc=None, content_type="html", sender_name=""):
        domain = MAIL_CONFIG["username"].split("@")[1]
        message_id = "<{}.{}@{}>".format(uuid.uuid4().hex, int(time.time()), domain)

        msg = MIMEMultipart()
        msg["From"] = formataddr((sender_name or MAIL_CONFIG["sender_name"], MAIL_CONFIG["username"]))
        msg["To"] = to
        msg["Subject"] = Header(subject, "utf-8")
        msg["Message-ID"] = message_id
        msg["Reply-To"] = MAIL_CONFIG["username"]
        if cc:
            msg["Cc"] = ", ".join(cc)

        msg.attach(MIMEText(body, content_type, "utf-8"))

        try:
            ctx = ssl.create_default_context()
            server = smtplib.SMTP_SSL(MAIL_CONFIG["smtp_host"], MAIL_CONFIG["smtp_port"], context=ctx)
            server.login(MAIL_CONFIG["username"], MAIL_CONFIG["password"])
            recipients = [to] + (cc or [])
            server.sendmail(MAIL_CONFIG["username"], recipients, msg.as_bytes())
            server.quit()
        except Exception as e:
            raise RuntimeError(f"SMTP send failed: {e}")

        return {"to": to, "subject": subject, "message_id": message_id}


def _format_result_table(columns: list, rows: list, max_rows: int = 20) -> str:
    """Format query result as an HTML table."""
    if not columns or not rows:
        return "<p><em>(查询无返回数据)</em></p>"

    display_rows = rows[:max_rows]
    html = '<table border="1" cellpadding="4" cellspacing="0" style="border-collapse:collapse; font-size:12px;">\n'
    html += "<tr>" + "".join(f'<th style="background:#eee">{c}</th>' for c in columns) + "</tr>\n"
    for row in display_rows:
        html += "<tr>" + "".join(f"<td>{v if v is not None else ''}</td>" for v in row) + "</tr>\n"
    html += "</table>"

    if len(rows) > max_rows:
        html += f'<p><em>（仅显示前 {max_rows} 行，共 {len(rows)} 行）</em></p>'
    return html


def send_questions_to_experts(questions: list[dict], results: list[dict]) -> dict:
    """
    Send each question + its result to the appropriate expert.
    Groups 2-3 questions per email to avoid spamming.

    Returns: {question_id: message_id}
    """
    mail = _SimpleMailClient()
    tracking = {}

    # Group questions by expert email
    by_expert = {}
    for q, r in zip(questions, results):
        expert_email = q.get("expert_email", MAIL_CONFIG["username"])
        by_expert.setdefault(expert_email, []).append((q, r))

    for expert_email, items in by_expert.items():
        for batch_start in range(0, len(items), 3):
            batch = items[batch_start:batch_start + 3]
            expert_name = batch[0][0].get("expert_name", "专家")

            # Build email body
            body_parts = [
                "<h2>取数验证请求</h2>",
                f"<p>{expert_name} 您好，以下是今天需要验证的取数问题，请逐一检查<strong>SQL逻辑</strong>和<strong>取数结果</strong>是否正确。</p>",
                "<p>如正确请回复<strong>「正确」</strong>；如错误请说明<strong>具体哪错了、正确口径是什么</strong>。</p>",
                "<hr>",
            ]

            for qi, (q, r) in enumerate(batch, 1):
                body_parts.append(f"<h3>问题 {qi}: {q['question']}</h3>")
                body_parts.append(f"<p><strong>领域</strong>: {q.get('domain', 'N/A')}</p>")
                body_parts.append(f"<p><strong>涉及表</strong>: {q.get('tables_hint', 'N/A')}</p>")
                body_parts.append(f"<p><strong>预期输出</strong>: {q.get('expected_output_type', 'N/A')}</p>")
                body_parts.append(f"<h4>SQL</h4><pre style='background:#f5f5f5;padding:8px;font-size:11px;'>{r.get('sql', 'N/A')}</pre>")

                if r["status"] == "success":
                    body_parts.append(f"<h4>结果 ({r['row_count']} 行)</h4>")
                    body_parts.append(_format_result_table(r["columns"], r["rows"]))
                else:
                    body_parts.append(f"<h4>取数失败</h4><p style='color:red'>{r.get('error', 'Unknown error')}</p>")

                body_parts.append("<hr>")

            body_parts.append("<p style='color:#666;font-size:11px;'>此邮件由取数验证Agent自动发送。请直接回复本邮件。</p>")

            subject = f"【取数验证】{datetime.now().strftime('%m/%d')} 数据取数验证 - {expert_name}"
            try:
                sent = mail.send_email(
                    to=expert_email,
                    subject=subject,
                    body="\n".join(body_parts),
                    content_type="html",
                    sender_name=MAIL_CONFIG["sender_name"],
                )
                for q, r in batch:
                    tracking[q["id"]] = sent["message_id"]
                    r["message_id"] = sent["message_id"]
            except Exception as e:
                print(f"[ERROR] Failed to send email to {expert_email}: {e}")
                for q, r in batch:
                    tracking[q["id"]] = None

    # Save tracking info to state
    _update_state(tracking, questions, results)

    return tracking


def _update_state(tracking: dict, questions: list[dict], results: list[dict]):
    """Update the agent state file with newly sent questions."""
    state = _load_state()
    today = datetime.now().strftime("%Y-%m-%d")

    if "daily_runs" not in state:
        state["daily_runs"] = {}
    if today not in state["daily_runs"]:
        state["daily_runs"][today] = {"sent": [], "replied": [], "correct": [], "incorrect": [], "evolved": []}

    for q, r in zip(questions, results):
        entry = {
            "question_id": q["id"],
            "question": q["question"],
            "domain": q.get("domain", ""),
            "expert_name": q.get("expert_name", ""),
            "expert_email": q.get("expert_email", ""),
            "sql": r.get("sql", ""),
            "status": r["status"],
            "error": r.get("error"),
            "message_id": tracking.get(q["id"]),
            "sent_at": datetime.now().isoformat(),
            "reply_status": "pending",
        }
        state["daily_runs"][today]["sent"].append(entry)

    _save_state(state)


def _load_state() -> dict:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_state(state: dict):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
