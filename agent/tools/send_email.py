"""
CLI tool: Send HTML email via SMTP.
Usage:
  python -m agent.tools.send_email \
    --to "a@b.com,c@b.com" \
    --subject "Subject" \
    --body-file /tmp/body.html \
    [--cc "cc@b.com"] \
    [--sender-name "Name"]
Output: {"status": "ok", "message_id": "..."} or {"error": "..."}
"""
import sys
import json
import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from agent.email_sender import _SimpleMailClient


def main():
    parser = argparse.ArgumentParser(description="Send HTML email via SMTP")
    parser.add_argument("--to", required=True, help="Recipient(s), comma-separated")
    parser.add_argument("--subject", required=True, help="Email subject")
    parser.add_argument("--body-file", required=True, help="Path to HTML body file")
    parser.add_argument("--cc", default=None, help="CC recipient(s)")
    parser.add_argument("--sender-name", default="取数验证Agent", help="Sender display name")
    args = parser.parse_args()

    try:
        body_text = Path(args.body_file).read_text(encoding="utf-8")
    except FileNotFoundError:
        print(json.dumps({"error": f"Body file not found: {args.body_file}"}, ensure_ascii=False))
        sys.exit(1)

    results = []
    mail = _SimpleMailClient()
    for addr in args.to.split(","):
        addr = addr.strip()
        if not addr:
            continue
        try:
            mail.send_email(
                to=addr,
                subject=args.subject,
                body=body_text,
                cc=args.cc,
                content_type="html",
                sender_name=args.sender_name,
            )
            results.append({"to": addr, "status": "sent"})
        except Exception as e:
            results.append({"to": addr, "status": "error", "error": str(e)})

    ok = all(r["status"] == "sent" for r in results)
    print(json.dumps({"ok": ok, "results": results}, ensure_ascii=False))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
