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

from agent.config import MAIL_CONFIG, STATE_FILE
from agent.llm_client import chat as llm_chat


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
    # Pre-check: strong signal that the reply is a detailed correction
    has_negative = bool(re.search(r'(不对|错了|不正确|有问题|错误)', reply_body))
    has_sql = bool(re.search(r'\b(SELECT|FROM|WHERE|JOIN|GROUP\s+BY)\b', reply_body, re.IGNORECASE))
    has_table = bool(re.search(r'(default_catalog|hive\.|ads_business_analysis|operation_center)', reply_body))
    chinese_chars = len(re.findall(r'[一-鿿]', reply_body))

    # If reply says "不对" AND contains SQL/table refs, it's a detailed correction — skip LLM
    if has_negative and (has_sql or has_table) and chinese_chars > 30:
        return "incorrect"

    prompt = f"""Classify this expert's reply to a data retrieval validation request.

Original question: {question_text}
SQL used (truncated): {sql[:300]}

Expert reply: {reply_body}

Classify as exactly one of:
- incorrect: expert says the data retrieval is wrong (words like "不对", "错了", "不正确") AND provides a specific correction (mentions tables, fields, SQL, filter conditions, or calculation logic)
- unclear: expert says it's wrong but does NOT give enough detail to fix the SQL (e.g. just "不对" or "再看看" without specifics)
- correct: expert confirms the data is right, or doesn't dispute it

IMPORTANT: if the reply contains SQL code (SELECT, FROM, WHERE), specific table names, or field names alongside a "不对", it is "incorrect" not "unclear".

Reply with just one word: correct, incorrect, or unclear."""

    try:
        result = llm_chat(
            system_prompt="You are a classification assistant. Reply with exactly one word.",
            user_message=prompt,
            temperature=0.1,
        ).strip().lower()
        if "incorrect" in result:
            return "incorrect"
        elif "unclear" in result:
            return "unclear"
        else:
            return "correct"
    except Exception:
        # If LLM fails, fall back to heuristic rather than defaulting to "unclear"
        if has_negative and chinese_chars > 50:
            return "incorrect"
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
               "unclear": 0, "followups_sent": 0, "actionable": [], "batch_date": None}

    state = _load_state()
    today = datetime.now().strftime("%Y-%m-%d")

    today_key = None
    for k in sorted(state.get("daily_runs", {}).keys(), reverse=True):
        run = state["daily_runs"].get(k, {})
        pending = [e for e in run.get("sent", [])
               if e.get("reply_status") == "pending"
               or (e.get("reply_status") == "incorrect" and not e.get("evolved"))]
        if pending:
            today_key = k
            break

    if not today_key:
        return summary

    summary["batch_date"] = today_key

    pending = [e for e in state["daily_runs"].get(today_key, {}).get("sent", [])
               if e.get("reply_status") == "pending"
               or (e.get("reply_status") == "incorrect" and not e.get("evolved"))]
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

    # ── Debug: print all fetched emails and pending questions ──
    print(f"\n[DETAIL] === IMAP fetched {len(emails)} email(s) in last 7 days ===", file=sys.stderr)
    for i, email_data in enumerate(emails):
        print(f"  EMAIL #{i}: subject='{email_data.get('subject', '')}'  from='{email_data.get('from_address', '')}'  in_reply_to='{email_data.get('in_reply_to', '')[:80]}'", file=sys.stderr)
    print(f"[DETAIL] === {len(pending)} pending question(s) in batch {today_key} ===", file=sys.stderr)
    for i, e in enumerate(pending):
        print(f"  Q#{i}: id={e.get('question_id') or e.get('id')}  domain={e.get('domain')}  expert={e.get('expert_email')}  msgid={'YES' if e.get('message_id') else 'NO'}  question='{e['question'][:80]}'", file=sys.stderr)
    print(f"[DETAIL] === Matching... ===", file=sys.stderr)

    for email_data in emails:
        in_reply_to = email_data.get("in_reply_to", "")
        from_addr = email_data.get("from_address", "")
        subject = email_data.get("subject", "")

        # Match reply to original message
        matched_entry = None
        match_method = None

        # Strategy 1: match by Message-ID header (most reliable, for post-fix emails)
        for msg_id, entry in message_id_map.items():
            if msg_id and msg_id.strip("<>") in in_reply_to:
                matched_entry = entry
                match_method = "message-id"
                break

        # Strategy 2: fallback — match reply to current batch by date + expert
        # Verification email subjects: 【取数验证】05/14 数据取数验证 - ExpertName
        # Expert replies contain: Re: 【取数验证】05/14 ... or 回复：【取数验证】05/14 ...
        if not matched_entry:
            batch_mmdd = today_key[5:]  # "2026-05-14" → "05-14"
            batch_mmdd_slash = batch_mmdd.replace("-", "/")  # "05/14"
            if ("取数验证" in subject and
                (batch_mmdd in subject or batch_mmdd_slash in subject)):
                # Reply belongs to this batch — narrow by expert email or name
                for entry in pending:
                    # Skip already-matched entries (but accept "incorrect" not yet evolved)
                    rs = entry.get("reply_status")
                    if rs != "pending" and not (rs == "incorrect" and not entry.get("evolved")):
                        continue
                    if entry.get("expert_email") and entry["expert_email"].lower() in from_addr.lower():
                        matched_entry = entry
                        match_method = "subject+expert"
                        break
                    if entry.get("expert_name") and entry["expert_name"] in subject:
                        matched_entry = entry
                        match_method = "subject+name"
                        break

        if not matched_entry:
            print(f"[DETAIL] UNMATCHED: subject='{subject}' from='{from_addr}'", file=sys.stderr)
            continue

        reply_body = email_data.get("body_text", "")
        if not reply_body.strip():
            print(f"[DETAIL] MATCHED but empty body: subject='{subject}' method={match_method}", file=sys.stderr)
            continue

        classification = _classify_reply(
            matched_entry["question"],
            matched_entry.get("sql", ""),
            reply_body,
        )

        qid = matched_entry.get("question_id") or matched_entry.get("id")
        print(f"[DETAIL] MATCHED: subject='{subject}' → Q={qid} method={match_method} classify={classification}", file=sys.stderr)

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
                summary["actionable"].append(matched_entry.get("question_id") or matched_entry.get("id"))
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

    if not dry_run:
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
