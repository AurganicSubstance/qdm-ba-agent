"""
Main Orchestrator.
Coordinates the daily agent pipeline: generate questions → retrieve data →
send to experts → collect feedback → evolve skills → report.
"""
import argparse
import sys
import os
from datetime import datetime
from agent.config import USER_EMAIL, USER_NAME, MAIL_CONFIG


def run_morning(dry_run: bool = False):
    """Step 1-3: Generate questions, execute data retrieval, send emails."""
    print(f"[{datetime.now()}] === MORNING PHASE ===")

    # Step 1: Generate questions
    print("[1/3] Generating questions from KnowledgeBase...")
    from agent.question_generator import generate_questions
    questions = generate_questions(dry_run=dry_run)
    print(f"  Generated {len(questions)} questions:")
    for q in questions:
        print(f"    [{q['domain']}] {q['question'][:80]}... → {q['expert_name']}")

    # Step 2: Execute data retrieval
    print("[2/3] Executing data retrieval...")
    from agent.data_retriever import execute_question
    results = []
    for i, q in enumerate(questions, 1):
        print(f"  [{i}/{len(questions)}] {q['question'][:60]}...")
        if dry_run:
            results.append({
                "question_id": q["id"], "status": "success",
                "sql": "-- DRY RUN SQL", "columns": ["col1", "col2"],
                "rows": [["val1", "val2"]], "row_count": 2, "error": None,
            })
        else:
            r = execute_question(q)
            results.append(r)
            status = "OK" if r["status"] == "success" else f"FAIL: {r.get('error','')[:50]}"
            print(f"    → {status} ({r['row_count']} rows)")

    # Step 3: Send emails to experts
    print("[3/3] Sending verification emails to experts...")
    if dry_run:
        print("  [DRY RUN] Would send emails to:")
        for q in questions:
            print(f"    → {q['expert_name']} <{q['expert_email']}>: {q['question'][:50]}...")
        tracking = {}
    else:
        from agent.email_sender import send_questions_to_experts
        tracking = send_questions_to_experts(questions, results)
        sent_count = sum(1 for v in tracking.values() if v is not None)
        print(f"  Sent {sent_count}/{len(tracking)} emails")

    return questions, results


def run_heartbeat(dry_run: bool = False):
    """Hourly check: collect feedback, evolve if possible, notify only on changes."""
    print(f"[{datetime.now()}] === HEARTBEAT ===")

    # Collect feedback
    print("[check] Checking for expert replies...")
    from agent.feedback_collector import collect_feedback
    summary = collect_feedback(dry_run=dry_run)
    print(f"  Replied: {summary['replied']} | Correct: {summary['correct']} | "
          f"Incorrect: {summary['incorrect']} | Unclear: {summary['unclear']} | "
          f"Follow-ups: {summary['followups_sent']}")

    if not summary.get("actionable"):
        print("  Nothing actionable — silent exit")
        return summary

    # Evolve skills from actionable feedback
    print("[evolve] Evolving skills from expert feedback...")
    from agent.skill_evolver import evolve_from_feedback
    evolutions = []
    for question_id in summary["actionable"]:
        action = evolve_from_feedback(question_id, dry_run=dry_run)
        if action.get("action") != "none":
            evolutions.append(action)
            print(f"  Evolved: {question_id} → {action['action']}: {action['description'][:80]}")

    print(f"  Skills evolved: {len(evolutions)}")

    if not evolutions:
        print("  No evolutions — silent exit")
        return summary

    # Notify user of evolutions
    if not dry_run:
        _notify_evolutions(evolutions)
    else:
        print(f"  [DRY RUN] Would notify user of {len(evolutions)} evolutions")

    return summary


def run_evening(dry_run: bool = False):
    """End-of-day: collect feedback, evolve, send full daily report."""
    print(f"[{datetime.now()}] === EVENING PHASE ===")

    # Collect + evolve (same as heartbeat)
    summary = run_heartbeat(dry_run=dry_run)

    # Always send daily report at end of day
    print("[report] Sending daily report...")
    from agent.daily_report import send_daily_report
    send_daily_report(dry_run=dry_run)

    return summary


def run_full(dry_run: bool = False):
    """Run the complete pipeline."""
    run_morning(dry_run=dry_run)
    print()
    run_evening(dry_run=dry_run)


def _notify_evolutions(evolutions: list):
    """Send a brief notification about skill evolutions to the user."""
    from agent.email_sender import _SimpleMailClient

    items = ""
    for evo in evolutions:
        items += f"<li><strong>{evo['action']}</strong>: {evo['description']}</li>"

    body = f"""<h2>取数Agent 技能进化通知</h2>
<p>以下取数规则已根据专家反馈自动更新：</p>
<ul>{items}</ul>
<p style='color:#666;font-size:11px;'>取数验证Agent自动发送</p>"""

    mail = _SimpleMailClient()
    mail.send_email(
        to=USER_EMAIL,
        subject=f"取数Agent 技能进化 - {datetime.now().strftime('%m/%d %H:%M')}",
        body=body,
        content_type="html",
        sender_name=MAIL_CONFIG["sender_name"],
    )
    print(f"  [notify] Evolution notification sent to {USER_EMAIL}")


def main():
    parser = argparse.ArgumentParser(description="取数验证Agent 调度器")
    parser.add_argument("--phase", choices=["morning", "heartbeat", "evening", "full"], default="full",
                        help="Which phase to run")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview without sending emails or modifying files")
    args = parser.parse_args()

    if args.phase == "morning":
        run_morning(dry_run=args.dry_run)
    elif args.phase == "heartbeat":
        run_heartbeat(dry_run=args.dry_run)
    elif args.phase == "evening":
        run_evening(dry_run=args.dry_run)
    else:
        run_full(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
