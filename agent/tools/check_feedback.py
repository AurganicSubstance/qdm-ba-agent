"""
CLI tool: Check IMAP for expert replies.
Usage:
  python -m agent.tools.check_feedback [--hours 24]
Output: JSON with raw replies (no LLM classification — Claude Code does that).
"""
import sys
import json
import argparse
from pathlib import Path
from datetime import datetime, timedelta

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from agent.feedback_collector import _get_imap_client


def main():
    parser = argparse.ArgumentParser(description="Check IMAP for expert replies")
    parser.add_argument("--hours", type=int, default=24, help="Look back N hours (default 24)")
    args = parser.parse_args()

    mail = _get_imap_client()
    if not mail:
        print(json.dumps({"error": "IMAP client unavailable (missing email_bot module)"}, ensure_ascii=False))
        sys.exit(1)

    try:
        since = (datetime.now() - timedelta(hours=args.hours)).strftime("%d-%b-%Y")
        emails = mail.fetch_since(since)
    except Exception as e:
        print(json.dumps({"error": f"IMAP fetch failed: {e}"}, ensure_ascii=False))
        sys.exit(1)

    replies = []
    for em in emails:
        replies.append({
            "subject": em.get("subject", ""),
            "from": em.get("from_address", ""),
            "in_reply_to": em.get("in_reply_to", ""),
            "body": em.get("body_text", "")[:2000],
            "date": str(em.get("date", "")),
        })

    print(json.dumps({"replies": replies, "count": len(replies)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
