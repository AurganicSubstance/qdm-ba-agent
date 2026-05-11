"""
Daily Report.
Generates a summary email to the user (梁晟) covering today's activity.
"""
import json
import os
from datetime import datetime

from agent.config import STATE_FILE, USER_EMAIL, USER_NAME, MAIL_CONFIG


def _load_state() -> dict:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def generate_daily_report() -> str:
    """Generate HTML report body for the daily summary email."""
    state = _load_state()
    today = datetime.now().strftime("%Y-%m-%d")

    # Gather stats from today and recent days
    today_run = state.get("daily_runs", {}).get(today, {})
    sent = today_run.get("sent", [])
    all_runs = state.get("daily_runs", {})

    total_ever_sent = sum(len(r.get("sent", [])) for r in all_runs.values())
    total_replied = sum(
        sum(1 for e in r.get("sent", []) if e.get("reply_status") != "pending")
        for r in all_runs.values()
    )
    total_correct = sum(
        sum(1 for e in r.get("sent", []) if e.get("reply_status") == "correct")
        for r in all_runs.values()
    )
    total_incorrect = sum(
        sum(1 for e in r.get("sent", []) if e.get("reply_status") == "incorrect")
        for r in all_runs.values()
    )
    total_unclear = sum(
        sum(1 for e in r.get("sent", []) if e.get("reply_status") == "unclear")
        for r in all_runs.values()
    )
    total_evolved = sum(
        sum(1 for e in r.get("sent", []) if e.get("evolved"))
        for r in all_runs.values()
    )

    today_sent = len(sent)
    today_replied = sum(1 for e in sent if e.get("reply_status") != "pending")
    today_correct = sum(1 for e in sent if e.get("reply_status") == "correct")
    today_incorrect = sum(1 for e in sent if e.get("reply_status") == "incorrect")
    today_evolved = sum(1 for e in sent if e.get("evolved"))

    # Build HTML
    html = f"""<h2>取数验证Agent — 每日汇总报告</h2>
<p><strong>日期</strong>: {today}</p>

<h3>今日概况</h3>
<table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse;">
<tr><th>指标</th><th>数值</th></tr>
<tr><td>今日发出问题</td><td style="text-align:center"><strong>{today_sent}</strong></td></tr>
<tr><td>今日已回复</td><td style="text-align:center">{today_replied}</td></tr>
<tr><td>✓ 正确</td><td style="text-align:center;color:green">{today_correct}</td></tr>
<tr><td>✗ 错误</td><td style="text-align:center;color:red">{today_incorrect}</td></tr>
<tr><td>🔧 已落地为skill</td><td style="text-align:center;color:blue">{today_evolved}</td></tr>
</table>

<h3>累计统计</h3>
<table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse;">
<tr><th>指标</th><th>数值</th></tr>
<tr><td>累计发出</td><td style="text-align:center">{total_ever_sent}</td></tr>
<tr><td>累计回复</td><td style="text-align:center">{total_replied}</td></tr>
<tr><td>累计正确</td><td style="text-align:center;color:green">{total_correct}</td></tr>
<tr><td>累计错误</td><td style="text-align:center;color:red">{total_incorrect}</td></tr>
<tr><td>累计不清楚</td><td style="text-align:center;color:orange">{total_unclear}</td></tr>
<tr><td>累计落地skill</td><td style="text-align:center;color:blue">{total_evolved}</td></tr>
</table>
"""

    # Today's question details
    if sent:
        html += "<h3>今日问题明细</h3><table border='1' cellpadding='4' cellspacing='0' style='border-collapse:collapse;font-size:12px;'>"
        html += "<tr><th>#</th><th>问题</th><th>领域</th><th>专家</th><th>状态</th></tr>"
        for i, e in enumerate(sent, 1):
            status_emoji = {"correct": "✓正确", "incorrect": "✗错误", "unclear": "?待追问", "pending": "⏳待回复"}
            status = status_emoji.get(e.get("reply_status", "pending"), e.get("reply_status", "?"))
            html += f"<tr><td>{i}</td><td>{e['question'][:60]}...</td><td>{e.get('domain','')}</td><td>{e.get('expert_name','')}</td><td>{status}</td></tr>"
        html += "</table>"

    # Recent evolutions
    if os.path.exists(os.path.join(os.path.dirname(STATE_FILE), "evolution_log.json")):
        with open(os.path.join(os.path.dirname(STATE_FILE), "evolution_log.json"), "r", encoding="utf-8") as f:
            evo_log = json.load(f)
        if evo_log:
            html += "<h3>最近Skill进化</h3><ul>"
            for evo in evo_log[-5:]:
                html += f"<li><strong>{evo['timestamp'][:10]}</strong>: {evo.get('description','')} ({evo.get('action','')})</li>"
            html += "</ul>"

    html += "<p style='color:#666;font-size:11px;'>取数验证Agent自动生成</p>"
    return html


def send_daily_report(dry_run: bool = False) -> bool:
    """Send the daily report email to the user."""
    body = generate_daily_report()

    if dry_run:
        print("[DRY RUN] Would send daily report:")
        # Safe ASCII print for Windows
        safe_body = body.encode('ascii', errors='replace').decode('ascii')
        print(safe_body[:1000])
        return True

    try:
        from agent.email_sender import _SimpleMailClient
        mail = _SimpleMailClient()
        mail.send_email(
            to=USER_EMAIL,
            subject=f"取数验证Agent 每日报告 - {datetime.now().strftime('%Y-%m-%d')}",
            body=body,
            content_type="html",
            sender_name=MAIL_CONFIG["sender_name"],
        )
        print(f"[OK] Daily report sent to {USER_EMAIL}")
        return True
    except Exception as e:
        print(f"[ERROR] Failed to send daily report: {e}")
        return False
