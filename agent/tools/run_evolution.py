"""
CLI tool: Run the full heartbeat/evolution pipeline.
Usage: python -m agent.tools.run_evolution [--dry-run]

Flow:
1. Backup current skill files (local safety net)
2. Collect + classify feedback via feedback_collector.collect_feedback()
3. Snapshot evolvable file mtimess
4. For each actionable (incorrect + detailed) reply:
   a. Build prompt with expert feedback + file paths
   b. Call OpenCode subprocess (with tool access) to evolve skill files
   c. Detect which files changed
5. Send notification email ONLY if files changed
"""
import sys
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from agent.config import STATE_FILE, EVOLUTION_LOG, PROJECT_ROOT, MAIL_CONFIG, USER_EMAIL, USER_NAME

SKILL_DIR = PROJECT_ROOT / ".claude" / "skills" / "dataqueryplus"

EVOLVABLE_FILES = {
    "sql_templates": SKILL_DIR / "references" / "sql_templates.md",
    "data_dictionary": SKILL_DIR / "references" / "data_dictionary.md",
    "claude_md": PROJECT_ROOT / "CLAUDE.md",
}

BACKUP_DIR = PROJECT_ROOT / "backups" / "skills"


# ── Layer A: Direct Script ────────────────────────────────────────────

def _backup_skills():
    """Copy current skill files to timestamped backup folder (local safety net)."""
    ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    dest = BACKUP_DIR / ts
    dest.mkdir(parents=True, exist_ok=True)
    for key, path in EVOLVABLE_FILES.items():
        if path.exists():
            shutil.copy2(path, dest / path.name)
    return dest


def _snapshot_files():
    """Record mtime of each evolvable file. Returns {key: mtime_or_None}."""
    snap = {}
    for key, path in EVOLVABLE_FILES.items():
        try:
            snap[key] = path.stat().st_mtime
        except FileNotFoundError:
            snap[key] = None
    return snap


def _detect_changes(before: dict) -> list:
    """Compare current mtimess to snapshot. Returns list of changed file keys."""
    changed = []
    for key, path in EVOLVABLE_FILES.items():
        try:
            current = path.stat().st_mtime
        except FileNotFoundError:
            current = None
        if before.get(key) != current:
            changed.append(key)
    return changed


def _send_notification(evolutions: list):
    """Send notification email to USER_EMAIL listing what changed, who reported it, and the diff."""
    from agent.email_sender import _SimpleMailClient

    now = datetime.now()
    ts = now.strftime("%m/%d %H:%M")

    items = ""
    for ev in evolutions:
        expert = ev.get("expert_name", "?")
        expert_email = ev.get("expert_email", "")
        reply_excerpt = ev.get("reply_body", "")[:200]
        diff_excerpt = ev.get("diff", "")[:800]

        items += f"""
<li style="margin-bottom:20px;">
  <b>问题</b>: {ev['question'][:80]}...<br>
  <b>专家</b>: {expert} ({expert_email})<br>
  <b>反馈</b>: {reply_excerpt}<br>
  <b>修改文件</b>: {ev['target_file']}<br>
  <b>说明</b>: {ev['description']}<br>
  <pre style="background:#2d2d2d;color:#f8f8f2;padding:8px;font-size:10px;overflow-x:auto;max-height:200px;">{diff_excerpt}</pre>
</li>"""

    body = f"""<h2>取数Agent 技能进化</h2>
<p><b>{ts}</b> — 专家验证触发了以下技能文件更新：</p>
<ul>{items}</ul>
<p style='color:#666;font-size:11px;'>此邮件由取数验证Agent自动发送。</p>"""

    mail = _SimpleMailClient()
    mail.send_email(
        to=USER_EMAIL,
        subject=f"取数Agent 技能进化 — {ts}",
        body=body,
        content_type="html",
        sender_name="取数验证Agent",
    )


# ── Layer B: OpenCode Harness ─────────────────────────────────────────

def _call_opencode(prompt: str, timeout: int = 600) -> str:
    """Call OpenCode (or Claude Code as fallback) to evolve skill files."""
    if shutil.which("opencode"):
        cmd = ["opencode", "run", "--model", "deepseek/deepseek-v4-pro", prompt]
    elif shutil.which("claude"):
        cmd = ["claude", "-p", prompt, "--print"]
    else:
        raise RuntimeError("No LLM CLI found (tried opencode, claude)")

    result = subprocess.run(
        cmd,
        capture_output=True, text=True,
        encoding="utf-8", errors="replace",
        cwd=str(PROJECT_ROOT),
        env=os.environ.copy(),
        timeout=timeout,
    )
    if result.returncode != 0:
        stderr = result.stderr.strip() if result.stderr else ""
        raise RuntimeError(f"LLM CLI exited {result.returncode}: {stderr[:200]}")
    return (result.stdout or "").strip()


def _build_evolution_prompt(entry: dict, today_str: str, batch_date: str) -> str:
    """Build the prompt for OpenCode with expert feedback + file paths + instructions.
    today_str: used for evolution date stamps (header date)
    batch_date: used for state key (the batch this evolution belongs to)"""

    question_text = entry.get("question", "")
    domain = entry.get("domain", "")
    sql = entry.get("sql", "")
    expert_name = entry.get("expert_name", "")
    expert_email = entry.get("expert_email", "")
    reply_body = (entry.get("reply_body", "") or "").replace("&nbsp;", " ").replace("&gt;", ">").replace("&lt;", "<").replace("&amp;", "&")
    # Truncate to keep prompt size manageable for DeepSeek latency
    if len(reply_body) > 2000:
        reply_body = reply_body[:2000] + "...(truncated)"

    sql_templates_path = EVOLVABLE_FILES["sql_templates"]
    data_dict_path = EVOLVABLE_FILES["data_dictionary"]
    claude_md_path = EVOLVABLE_FILES["claude_md"]
    skill_md_path = SKILL_DIR / "SKILL.md"

    return f"""You are evolving the QDM BA Agent data retrieval knowledge base. An expert has reviewed a data query and found an error. Your job is to update the skill files so the same mistake won't happen again.

=== EXPERT FEEDBACK ===

Question: {question_text}
Domain: {domain}
SQL that was used:
```sql
{sql}
```

Expert reply from {expert_name} ({expert_email}):
{reply_body}

=== YOUR TASK ===

1. Read these skill files to understand the current knowledge state:
   - {sql_templates_path}
   - {data_dict_path}
   - {claude_md_path}

   Also read {skill_md_path} for context on how the system works
   (but do NOT modify SKILL.md — it's the operating manual, not a knowledge file).

2. Decide which of the 3 files need updating based on the error type:
   - Wrong SQL pattern/template → {sql_templates_path}
   - Wrong field meaning/usage → {data_dict_path}
   - Missing general retrieval rule → {claude_md_path}
   - If the feedback is too vague to act on → do nothing, just explain why

3. Update the chosen file(s). You can restructure, rewrite, or reorganise as needed.
   Be thoughtful — a good edit makes the skill file more useful for future queries.
   Each correction should reference the expert's feedback so readers know the source.
   Use today's date ({today_str}) for any dated entries.

4. SCOPE: You may ONLY edit these 3 files. Do NOT touch .py, .sh, .env, state files,
   or any other files in the project. Use manage_state for state records (see below).

5. After evolving, record it in state under the batch that was sent:
   python -m agent.tools.manage_state --append "daily_runs.{batch_date}.evolved" '{{"question_id":"{question_id}","action":"<which_file>","description":"<one-line Chinese summary>"}}'"""


def _parse_evolution_summary(stdout: str) -> dict:
    """Try to extract a summary of what OpenCode did from its stdout.
    Returns {{action, description}} or empty dict on failure."""
    # OpenCode may output its reasoning. Try to find a summary line.
    # Look for manage_state call which contains the description
    m = re.search(r'"description"\s*:\s*"([^"]+)"', stdout)
    if m:
        return {"description": m.group(1)}
    return {}


# ── Main Orchestration ─────────────────────────────────────────────────

def main():
    dry_run = "--dry-run" in sys.argv
    today_str = datetime.now().strftime("%Y-%m-%d")

    # 1. Backup current skill files (always, even in dry-run — it's read-only)
    backup_path = _backup_skills()
    print(f"[BACKUP] Skills saved to {backup_path}", file=sys.stderr)

    # 2. Collect and classify feedback
    from agent.feedback_collector import collect_feedback

    print("[FEEDBACK] Checking for expert replies...", file=sys.stderr)
    summary = collect_feedback(dry_run=dry_run)

    print(f"[FEEDBACK] Total: {summary['total_sent']}, "
          f"Replied: {summary['replied']}, "
          f"Correct: {summary['correct']}, "
          f"Incorrect: {summary['incorrect']}, "
          f"Unclear: {summary['unclear']}, "
          f"Follow-ups: {summary['followups_sent']}, "
          f"Actionable: {len(summary['actionable'])}", file=sys.stderr)

    if not summary["actionable"]:
        print("[EVOLVE] Nothing actionable — exiting silently", file=sys.stderr)
        print(json.dumps({"ok": True, "actionable": 0, "evolved": 0, "evolutions": []}, ensure_ascii=False))
        return

    # 3. Snapshot evolvable files before OpenCode touches them
    before_snapshot = _snapshot_files()

    # 4. Process each actionable reply
    evolutions = []
    changed_files = set()

    # Reload state (collect_feedback already saved it with updated reply_status etc.)
    with open(STATE_FILE, 'r', encoding='utf-8') as f:
        state = json.load(f)

    batch_dates = summary.get("batch_dates") or [today_str]
    # Build combined sent entries, qid→entry lookup, and qid→batch lookup
    all_sent_entries = []
    qid_to_batch = {}
    for bd in batch_dates:
        entries = state.get("daily_runs", {}).get(bd, {}).get("sent", [])
        all_sent_entries.extend(entries)
        for e in entries:
            qid_to_batch[e.get("question_id") or e.get("id")] = bd
    entry_by_qid = {e.get("question_id") or e.get("id"): e for e in all_sent_entries}

    print("=" * 60, file=sys.stderr)
    print(f"BATCHES: {', '.join(batch_dates)} | {len(summary['actionable'])} actionable reply(s)", file=sys.stderr)
    print("=" * 60, file=sys.stderr)

    for question_id in summary["actionable"]:
        entry = entry_by_qid.get(question_id)
        if not entry:
            print(f"[WARN] Question {question_id} not found in batches {batch_dates}", file=sys.stderr)
            continue

        # ── Print detailed context ──
        print(f"\n{'─' * 50}", file=sys.stderr)
        print(f"QUESTION: {entry['question']}", file=sys.stderr)
        print(f"DOMAIN:   {entry.get('domain', '?')}", file=sys.stderr)
        print(f"EXPERT:   {entry.get('expert_name', '?')} ({entry.get('expert_email', '?')})", file=sys.stderr)
        print(f"REPLY:    {entry.get('reply_body', '')[:300]}", file=sys.stderr)
        print(f"{'─' * 50}", file=sys.stderr)

        prompt = _build_evolution_prompt(entry, today_str, qid_to_batch.get(question_id, today_str))

        if dry_run:
            print(f"[DRY-RUN] Would call OpenCode with prompt ({len(prompt)} chars)", file=sys.stderr)
            continue

        # ── Call OpenCode ──
        try:
            stdout = _call_opencode(prompt)
        except RuntimeError as e:
            print(f"[ERROR] OpenCode call failed: {e}", file=sys.stderr)
            continue

        # ── Detect what changed ──
        new_changes = _detect_changes(before_snapshot)
        parsed = _parse_evolution_summary(stdout)

        for key in new_changes:
            changed_files.add(key)
            path = EVOLVABLE_FILES[key]

            # Show git diff of what OpenCode actually changed
            try:
                diff_result = subprocess.run(
                    ["git", "diff", str(path)],
                    capture_output=True, text=True,
                    encoding="utf-8", errors="replace",
                    cwd=str(PROJECT_ROOT),
                    timeout=10,
                )
                diff_text = diff_result.stdout.strip()
            except Exception:
                diff_text = "(git diff unavailable)"

            print(f"\n[EVOLVED] {path.name}", file=sys.stderr)
            if parsed.get("description"):
                print(f"  DESCRIPTION: {parsed['description']}", file=sys.stderr)
            if diff_text:
                # Show first 40 lines of diff for readability
                diff_lines = diff_text.split("\n")
                print(f"  DIFF ({len(diff_lines)} lines):", file=sys.stderr)
                for line in diff_lines[:40]:
                    print(f"    {line}", file=sys.stderr)
                if len(diff_lines) > 40:
                    print(f"    ... ({len(diff_lines) - 40} more lines)", file=sys.stderr)

            evolutions.append({
                "question_id": question_id,
                "question": entry["question"],
                "expert_name": entry.get("expert_name", ""),
                "expert_email": entry.get("expert_email", ""),
                "reply_body": entry.get("reply_body", "")[:300],
                "target_file": key,
                "description": parsed.get("description", f"Updated {key}"),
                "diff": diff_text[:2000] if diff_text else "",
            })
            before_snapshot[key] = path.stat().st_mtime

        if not new_changes:
            print(f"[EVOLVE] No files changed — feedback may not be actionable", file=sys.stderr)

    # 5. Print evolution summary
    if evolutions:
        print(f"\n{'=' * 60}", file=sys.stderr)
        print(f"EVOLUTION COMPLETE — {len(evolutions)} file(s) changed", file=sys.stderr)
        for ev in evolutions:
            print(f"  → {ev['target_file']}: {ev['description']}", file=sys.stderr)
        print(f"{'=' * 60}", file=sys.stderr)

    # 6. Save state with evolution records (if not dry-run and files changed)
    if not dry_run and evolutions:
        # Reload state again in case manage_state was called by OpenCode
        with open(STATE_FILE, 'r', encoding='utf-8') as f:
            state = json.load(f)

        for ev in evolutions:
            entry = None
            for bd in batch_dates:
                entry = next(
                    (e for e in state.get("daily_runs", {}).get(bd, {}).get("sent", [])
                     if e.get("question_id") == ev["question_id"]),
                    None,
                )
                if entry:
                    break
            if entry:
                entry["evolved"] = True
                entry["evolution_target"] = ev["target_file"]
                entry["evolution_description"] = ev["description"]

        tmp = str(STATE_FILE) + ".tmp"
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        os.replace(tmp, STATE_FILE)

    # 7. Notify if files changed
    if evolutions:
        if dry_run:
            print(f"[DRY-RUN] Would notify {USER_EMAIL} about {len(evolutions)} evolution(s)", file=sys.stderr)
        else:
            print(f"[NOTIFY] Sending evolution notification to {USER_EMAIL}", file=sys.stderr)
            _send_notification(evolutions)
    else:
        print("[EVOLVE] No evolutions — exiting silently", file=sys.stderr)

    print(json.dumps({
        "ok": True,
        "total_replied": summary["replied"],
        "actionable": len(summary["actionable"]),
        "evolved": len(evolutions),
        "evolutions": [{"question_id": e["question_id"], "target_file": e["target_file"], "description": e["description"]} for e in evolutions],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
