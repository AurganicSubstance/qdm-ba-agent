"""
CLI tool: Read/write agent_state.json.
Usage:
  python -m agent.tools.manage_state --get [key]        # read state
  python -m agent.tools.manage_state --set "key" '...'  # write value at key
  python -m agent.tools.manage_state --append "array_key" '...'  # append to array
Output: JSON to stdout.
"""
import sys
import json
import os
import shutil
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from agent.config import STATE_FILE


def _load():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"version": 2, "daily_runs": {}}


def _save(state: dict):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    os.replace(tmp, STATE_FILE)


def _navigate(state, path: str):
    """Navigate dot-notation path. Empty string returns root."""
    if not path:
        return state
    parts = path.split(".")
    current = state
    for part in parts:
        if isinstance(current, list):
            idx = int(part)
            current = current[idx]
        elif isinstance(current, dict):
            current = current[part]
        else:
            raise KeyError(f"Cannot navigate into {type(current)} at {part}")
    return current


def main():
    args = sys.argv[1:]
    if not args:
        print(json.dumps(_load(), ensure_ascii=False))
        return

    action = args[0]

    if action == "--get":
        key = args[1] if len(args) > 1 else ""
        state = _load()
        try:
            val = _navigate(state, key)
            print(json.dumps(val, ensure_ascii=False))
        except (KeyError, IndexError):
            print("null")

    elif action == "--set":
        if len(args) < 3:
            print(json.dumps({"error": "usage: --set key value"}, ensure_ascii=False))
            sys.exit(1)
        key = args[1]
        val_str = args[2]
        val = json.loads(val_str)
        state = _load()
        parts = key.split(".")
        container = state
        for part in parts[:-1]:
            if isinstance(container, list):
                idx = int(part)
                container = container[idx]
            else:
                if part not in container:
                    container[part] = {}
                container = container[part]
        container[parts[-1]] = val
        _save(state)
        print(json.dumps({"ok": True}, ensure_ascii=False))

    elif action == "--append":
        if len(args) < 3:
            print(json.dumps({"error": "usage: --append array_key value"}, ensure_ascii=False))
            sys.exit(1)
        key = args[1]
        val = json.loads(args[2])
        state = _load()
        arr = _navigate(state, key)
        if not isinstance(arr, list):
            print(json.dumps({"error": f"{key} is not an array"}, ensure_ascii=False))
            sys.exit(1)
        arr.append(val)
        _save(state)
        print(json.dumps({"ok": True, "index": len(arr) - 1}, ensure_ascii=False))

    elif action == "--merge":
        if len(args) < 3:
            print(json.dumps({"error": "usage: --merge key value"}, ensure_ascii=False))
            sys.exit(1)
        key = args[1]
        val = json.loads(args[2])
        state = _load()
        target = _navigate(state, key)
        if isinstance(target, dict) and isinstance(val, dict):
            target.update(val)
        else:
            print(json.dumps({"error": "merge requires dict targets"}, ensure_ascii=False))
            sys.exit(1)
        _save(state)
        print(json.dumps({"ok": True}, ensure_ascii=False))

    else:
        print(json.dumps({"error": f"Unknown action: {action}"}, ensure_ascii=False))
        sys.exit(1)


if __name__ == "__main__":
    main()
