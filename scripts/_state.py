#!/usr/bin/env python3
"""Per-session sidecar state shared by the solo guard and the budget
governor: a temp-dir JSON file per (prefix, session), updated under an
exclusive lock so parallel PreToolUse hooks never lose or double a count.

Both helpers fail soft: no session id, an unwritable temp dir, or a
corrupt file yields None, and the caller then stays out of the way. A
hook must never block a tool call because its bookkeeping broke.
"""
import json
import os
import tempfile

try:
    import fcntl
except ImportError:  # non-POSIX: run unlocked, best effort
    fcntl = None


def tmp_json(prefix, session_id):
    """<tmp>/<prefix>-<session>.json, or None without a session id. The
    `orch-` prefix keeps it inside the SessionEnd cleanup and 96h sweep."""
    if not session_id:
        return None
    safe = "".join(c for c in str(session_id) if c.isalnum() or c in "-_")
    return os.path.join(tempfile.gettempdir(), f"{prefix}-{safe}.json")


def update_state(path, mutate):
    """Read-modify-write `path` under an exclusive lock.

    `mutate(state_dict)` returns (new_state, result); the new state is
    written back and `result` returned. Missing, corrupt or wrong-typed
    content starts from {}. Returns None when the file cannot be used.
    """
    if not path:
        return None
    try:
        f = open(path, "a+", encoding="utf-8")
    except OSError:
        return None
    try:
        if fcntl is not None:
            try:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            except OSError:
                pass
        f.seek(0)
        try:
            state = json.load(f)
        except Exception:
            state = {}
        if not isinstance(state, dict):
            state = {}
        state, result = mutate(state)
        try:
            f.seek(0)
            f.truncate()
            json.dump(state, f)
            f.flush()
        except (OSError, ValueError):
            pass
        return result
    finally:
        f.close()


def env_int(name, default):
    """Integer env var; unparseable falls back to the default, negatives clamp to 0."""
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return default
    try:
        return max(0, int(raw))
    except ValueError:
        return default


def env_off(name):
    return (os.environ.get(name) or "").strip() == "0"
