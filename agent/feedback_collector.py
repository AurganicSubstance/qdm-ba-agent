"""
Feedback Collector.
Pulls expert email replies via IMAP → LLM classifies as correct/incorrect/unclear →
If unclear, sends follow-up asking for clarification.
"""
import sys
import os
import json
import re
from datetime import datetime, timedelta
from typing import Optional

# Add email_bot path
_KB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "BAKnowledgeBase3.1")
if os.path.isdir(_KB_PATH):
    sys.path.insert(0, _KB_PATH)

from agent.config import MAIL_CONFIG, DASHSCOPE_CONFIG, STATE_FILE
import requests


def _get_imap_client():
    """Get IMAP client for reading replies."""
    try:
        from qwen_md_grader.email_bot.mail_client import MailClient
        return MailClient(
            imap_host=MAIL_CONFIG["imap_host"],
            imap_port=MAIL_CONFIG["imap_port"],
            smtp_host=MAIL_CONFIG["smtp_host"],
            smtp_port=MAIL_CONFIG["smtp_port"],
            username=MAIL_CONFIG["username"],
            password=MAIL_CONFIG["password"],
        )
    except ImportError:
        print("[WARN] Cannot import MailClient from email_bot, IMAP unavailable")
        return None


def _classify_reply(question_text: str, sql: str, reply_body: str) -> str:
    """Use LLM to classify expert reply as: correct, incorrect, unclear."""
    prompt = f"""Classify this expert's reply to a data retrieval validation request.

Original question: {question_text}
SQL used: {sql}

Expert reply: {reply_body[:1500]}

Classify as exactly one of:
- correct: expert confirms the data retrieval is correct (words like "对", "正确", "没问题", "可以")
- incorrect: expert says the data is wrong AND explains what's wrong (words like "不对", "错了", + specific correction)
- unclear: expert says it's wrong but does NOT explain clearly what the correct approach is

Reply with just one word: correct, incorrect, or unclear."""

    try:
        resp = requests.post(
            "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {DASHSCOPE_CONFIG['api_key']}",
                "Content-Type": "application/json",
            },
            json={
                "model": DASHSCOPE_CONFIG["model"],
                "messages": [
                    {"role": "system", "content": "You are a classification assistant. Reply with exactly one word."},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.1,
            },
            timeout=60,
        )
        result = resp.json()["choices"][0]["message"]["content"].strip().lower()
        if "incorrect" in result:
            return "incorrect"
        elif "unclear" in result:
            return "unclear"
        else:
            return "correct"
    except Exception:
        return "unclear"


def _send_followup(original_message_id: str, expert_email: str, expert_name: str,
                   question_text: str, reply_body: str) -> bool:
    """Send a follow-up email asking the expert to clarify what's wrong."""
    try:
        from agent.email_sender import _SimpleMailClient
        mail = _SimpleMailClient()
        body = f"""<h2>请帮忙进一步说明</h2>
<p>{expert_name} 您好，感谢您的回复。您对以下取数问题的反馈我们收到了，但还需要您进一步说明：</p>

<p><strong>原始问题</strong>: {question_text}</p>

<p><strong>您的回复</strong>: {reply_body[:500]}</p>

<hr>
<p>能否请您详细说明：</p>
<ol>
  <li><strong>具体哪里取错了？</strong>（是字段选错了、口径不对、还是表用错了？）</li>
  <li><strong>正确取数口径是什么？</strong>（应该用什么字段、加什么筛选条件？）</li>
</ol>
<p>我们收到您的说明后会立即修正取数逻辑，后续同类问题就不会再错了。谢谢！</p>
<p style='color:#666;font-size:11px;'>此邮件由取数验证Agent自动发送。</p>"""
        mail.send_email(
            to=expert_email,
            subject=f"Re: 【取数验证】请帮忙澄清取数错误细节",
            body=body,
            content_type="html",
            sender_name=MAIL_CONFIG["sender_name"],
        )
        return True
    except Exception as e:
        print(f"[ERROR] Failed to send follow-up: {e}")
        return False


def collect_feedback(dry_run: bool = False) -> dict:
    """
    Collect expert replies and classify them.

    Returns summary: {
        "total_sent": int,
        "replied": int,
        "correct": int,
        "incorrect": int,
        "unclear": int,
        "followups_sent": int,
        "actionable": [list of question_ids with clear incorrect feedback],
    }
    """
    summary = {"total_sent": 0, "replied": 0, "correct": 0, "incorrect": 0,
               "unclear": 0, "followups_sent": 0, "actionable": []}

    state = _load_state()
    today = datetime.now().strftime("%Y-%m-%d")

    today_key = None
    for k in sorted(state.get("daily_runs", {}).keys(), reverse=True):
        run = state["daily_runs"].get(k, {})
        pending = [e for e in run.get("sent", []) if e.get("reply_status") == "pending"]
        if pending:
            today_key = k
            break

    if not today_key:
        return summary

    pending = [e for e in state["daily_runs"].get(today_key, {}).get("sent", [])
               if e.get("reply_status") == "pending"]
    if not pending:
        return summary

    summary["total_sent"] = len(pending)
    message_id_map = {e["message_id"]: e for e in pending if e.get("message_id")}

    mail = _get_imap_client()
    if not mail:
        return summary

    try:
        since = (datetime.now() - timedelta(days=7)).strftime("%d-%b-%Y")
        emails = mail.fetch_since(since)
    except Exception as e:
        print(f"[ERROR] IMAP fetch failed: {e}")
        return summary

    for email_data in emails:
        in_reply_to = email_data.get("in_reply_to", "")
        # Match reply to original message
        matched_entry = None
        for msg_id, entry in message_id_map.items():
            if msg_id and msg_id.strip("<>") in in_reply_to:
                matched_entry = entry
                break

        if not matched_entry:
            continue

        reply_body = email_data.get("body_text", "")
        if not reply_body.strip():
            continue

        classification = _classify_reply(
            matched_entry["question"],
            matched_entry.get("sql", ""),
            reply_body,
        )

        summary["replied"] += 1
        matched_entry["reply_status"] = classification
        matched_entry["reply_body"] = reply_body[:1000]
        matched_entry["reply_from"] = email_data.get("from_address", "")
        matched_entry["replied_at"] = datetime.now().isoformat()

        if classification == "correct":
            summary["correct"] += 1
        elif classification == "incorrect":
            summary["incorrect"] += 1
            # Check if explanation is detailed enough for skill evolution
            if _is_explanation_detailed(reply_body):
                summary["actionable"].append(matched_entry["question_id"])
        elif classification == "unclear":
            summary["unclear"] += 1
            # Send follow-up
            if not dry_run:
                sent = _send_followup(
                    matched_entry.get("message_id", ""),
                    matched_entry.get("expert_email", ""),
                    matched_entry.get("expert_name", ""),
                    matched_entry["question"],
                    reply_body,
                )
                if sent:
                    summary["followups_sent"] += 1
                    matched_entry["followup_sent"] = True

    _save_state(state)
    return summary


def _is_explanation_detailed(reply_body: str) -> bool:
    """Check if the expert's reply contains enough detail for skill evolution."""
    # Heuristic: more than 20 Chinese characters suggest a detailed explanation
    chinese_chars = len(re.findall(r'[一-鿿]', reply_body))
    has_specific = bool(re.search(r'(字段|表|口径|WHERE|SELECT|条件|应该|用|改成)', reply_body))
    return chinese_chars > 20 and has_specific


def _load_state() -> dict:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_state(state: dict):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
