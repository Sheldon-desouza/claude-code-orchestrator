#!/usr/bin/env python3
"""Tier map + routing table: the plugin's only knowledge of model names.

Every hook that needs to know "which tier is this model" or "which tier
does this task class demand" imports this module. Nothing else in the
repo names a model; `config/tiers.json` does, and a per-machine override
at ~/.claude/orchestrator/tiers.json (or $ORCH_CONFIG_DIR/tiers.json)
can replace any subset of it. Same for `config/routing.json`.

Failure policy is FAIL OPEN with defaults: a missing, unreadable, or
malformed override falls back to the shipped file, and a broken shipped
file falls back to the built-in DEFAULT_TIERS — a hook must never deny
a tool call because a JSON file has a stray comma.

Also usable from the command line for `/orch-doctor` and the tests:

    python3 scripts/tiers.py            # print the effective tier map
    python3 scripts/tiers.py <model>    # print the tier a model resolves to
"""
import json
import os
import re
import sys

PLUGIN_ROOT = os.environ.get("CLAUDE_PLUGIN_ROOT") or os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))

DEFAULT_TIERS = {
    "chair": {"model": "fable", "match": ["fable"], "fallbacks": ["opus", "sonnet"]},
    "heavy": {"model": "opus", "match": ["opus"], "fallbacks": ["fable", "sonnet"]},
    "bulk": {"model": "sonnet", "match": ["sonnet"], "fallbacks": ["opus"]},
    "cheap": {"model": "haiku", "match": ["haiku"], "fallbacks": ["sonnet"]},
}
DEFAULT_ORDER = ["cheap", "bulk", "heavy", "chair"]
DEFAULT_CLASSES = {
    "scan": {"min_tier": "cheap", "max_tier": "bulk", "effort": "low", "agent": "orch-scout"},
    "research": {"min_tier": "bulk", "max_tier": "bulk", "effort": "medium", "agent": "orch-researcher"},
    "implement": {"min_tier": "bulk", "max_tier": "heavy", "effort": "high", "agent": "orch-implementer"},
    "review": {"min_tier": "bulk", "max_tier": "heavy", "effort": "high", "agent": "orch-reviewer"},
    "hard": {"min_tier": "heavy", "max_tier": "heavy", "effort": "max", "agent": "orch-hard-slice"},
    "security": {"min_tier": "heavy", "max_tier": "heavy", "effort": "max", "agent": "orch-security"},
    "verify": {"min_tier": "heavy", "max_tier": "heavy", "effort": "high", "agent": "orch-verifier"},
    "chair-only": {"min_tier": "chair", "max_tier": "chair", "effort": "max", "agent": None},
}

# `Class: implement` on the first non-blank line of a spawn prompt.
# Case-insensitive, tolerant of a leading bullet/marker and of
# `class=`/`class -`; the class name is letters, digits, dashes.
CLASS_TAG_RE = re.compile(r"^\s*(?:[-*>#]+\s*)?class\s*[:=\-]\s*([a-z0-9][a-z0-9\-]*)",
                          re.IGNORECASE)


def config_dir():
    """Where per-machine overrides live."""
    override = (os.environ.get("ORCH_CONFIG_DIR") or "").strip()
    if override:
        return os.path.expanduser(override)
    base = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(
        os.path.expanduser("~"), ".claude")
    return os.path.join(base, "orchestrator")


def _read_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _valid_tier(entry):
    return (isinstance(entry, dict)
            and isinstance(entry.get("model"), str) and entry["model"].strip()
            and isinstance(entry.get("match"), list)
            and all(isinstance(m, str) and m.strip() for m in entry["match"]))


def load_tiers():
    """Effective tier map: shipped config, then the per-machine override
    merged in per tier. Returns {tier: {model, match, fallbacks, role}}."""
    tiers = {k: dict(v) for k, v in DEFAULT_TIERS.items()}
    for path in (os.path.join(PLUGIN_ROOT, "config", "tiers.json"),
                 os.path.join(config_dir(), "tiers.json")):
        data = _read_json(path)
        if not data:
            continue
        found = data.get("tiers")
        if not isinstance(found, dict):
            continue
        for name, entry in found.items():
            if _valid_tier(entry):
                merged = dict(tiers.get(name, {}))
                merged.update(entry)
                merged.setdefault("fallbacks", [])
                tiers[name] = merged
    return tiers


def load_routing():
    """Effective routing table: {order: [...], default_class, classes: {...}}."""
    routing = {"order": list(DEFAULT_ORDER), "default_class": "implement",
               "classes": {k: dict(v) for k, v in DEFAULT_CLASSES.items()}}
    for path in (os.path.join(PLUGIN_ROOT, "config", "routing.json"),
                 os.path.join(config_dir(), "routing.json")):
        data = _read_json(path)
        if not data:
            continue
        if isinstance(data.get("order"), list) and data["order"]:
            routing["order"] = [str(t) for t in data["order"]]
        if isinstance(data.get("default_class"), str):
            routing["default_class"] = data["default_class"]
        classes = data.get("classes")
        if isinstance(classes, dict):
            for name, entry in classes.items():
                if isinstance(entry, dict) and entry.get("min_tier"):
                    merged = dict(routing["classes"].get(name, {}))
                    merged.update(entry)
                    routing["classes"][name] = merged
    return routing


def tier_of(model, tiers=None):
    """Tier name for a model string, or None when nothing matches.

    Word-bounded on the left and on the right against LETTERS only, so a
    version or a bracket can follow: `claude-opus-5`, `opus5`, `opus[1m]`,
    `Opus 5 (1M context)` all resolve to the tier matching "opus", while
    `claude-octopus-1` and `opusculum` do not. Exact match against the
    tier's own `model` alias wins first.
    """
    text = str(model or "").strip()
    if not text:
        return None
    tiers = tiers or load_tiers()
    low = text.lower()
    for name, entry in tiers.items():
        if low == str(entry.get("model", "")).lower():
            return name
    for name, entry in tiers.items():
        for needle in entry.get("match", []):
            if re.search(r"(?<![a-z])" + re.escape(needle.lower()) + r"(?![a-z])", low):
                return name
    return None


def rank(tier, order=None):
    """Position of a tier in the cheap->chair order; -1 if unknown."""
    order = order or DEFAULT_ORDER
    try:
        return order.index(tier)
    except ValueError:
        return -1


def class_of_prompt(prompt):
    """The `Class:` tag on the first non-blank line of a spawn prompt, lowercased,
    or None when the prompt is untagged."""
    for line in str(prompt or "").splitlines():
        if not line.strip():
            continue
        m = CLASS_TAG_RE.match(line)
        return m.group(1).lower() if m else None
    return None


def effective_chair(session_model, tiers=None):
    """('chair'|'fallback', model_string) — is the configured chair model in the
    chair, or is a fallback tier holding it? Unknown models count as the
    chair: a brand-new model name is more likely the top tier than not, and
    the safe side is to hand it the full profile."""
    tiers = tiers or load_tiers()
    t = tier_of(session_model, tiers)
    if t is None or t == "chair":
        return "chair", (session_model or tiers["chair"]["model"])
    return "fallback", session_model


if __name__ == "__main__":
    if len(sys.argv) > 1:
        print(tier_of(" ".join(sys.argv[1:])) or "unknown")
    else:
        print(json.dumps({"config_dir": config_dir(), "tiers": load_tiers(),
                          "routing": load_routing()}, indent=2))
