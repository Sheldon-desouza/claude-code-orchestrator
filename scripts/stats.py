#!/usr/bin/env python3
"""Summarize the orchestrator metrics log.

Usage:
    python3 scripts/stats.py [path]

Default path: ~/.claude/orchestrator/metrics.jsonl (written by the hooks;
disable collection with ORCH_METRICS=0).
"""
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone


def records(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except ValueError:
                continue


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.expanduser("~"), ".claude", "orchestrator", "metrics.jsonl")
    if not os.path.isfile(path):
        print(f"no metrics yet: {path}")
        return

    per_day = defaultdict(Counter)
    events = Counter()
    profiles = Counter()
    ledgers = Counter()
    swarm_reaped = 0
    panes_reaped = 0
    by_tier = Counter()        # every allowed spawn, by the tier it ran on
    by_class = Counter()       # over-threshold spawns, by class tag
    route_denies = Counter()   # route guard denials, by reason
    switch_fires = Counter()   # profile changes delivered as a full core, by fire

    for rec in records(path):
        event = rec.get("event") or "?"
        events[event] += 1
        try:
            day = datetime.fromtimestamp(
                float(rec.get("ts") or 0), tz=timezone.utc).strftime("%Y-%m-%d")
        except (ValueError, OSError, OverflowError):
            day = "?"
        per_day[day][event] += 1
        if event == "inject":
            profiles[rec.get("profile") or rec.get("model") or "?"] += 1
        if event == "stop_block":
            ledgers[rec.get("ledger") or "?"] += 1
        if event == "budget_count":
            by_tier[rec.get("tier") or "?"] += 1
        if event == "route_pass":
            by_class[f"{rec.get('cls') or '?'} on {rec.get('tier') or '?'}"] += 1
        if event == "route_deny":
            route_denies[rec.get("reason") or "?"] += 1
        if event == "inject" and rec.get("from_profile"):
            switch_fires[f"{rec.get('from_profile')}->{rec.get('profile')} on {rec.get('fire') or '?'}"] += 1
        if event == "cleanup":
            try:
                swarm_reaped += int(rec.get("swarm_own") or 0)
                swarm_reaped += int(rec.get("swarm_stale") or 0)
            except (TypeError, ValueError):
                pass
        if event == "teammate_reap":
            try:
                panes_reaped += int(rec.get("killed") or 0)
            except (TypeError, ValueError):
                pass

    print(f"metrics: {path}\n")
    print("== events per day ==")
    for day in sorted(per_day):
        parts = ", ".join(f"{k}={v}" for k, v in sorted(per_day[day].items()))
        print(f"{day}  {parts}")

    print("\n== totals ==")
    for name, count in sorted(events.items()):
        print(f"{name:26} {count}")

    if profiles:
        print("\n== sessions by profile/model (inject events) ==")
        for name, count in profiles.most_common():
            print(f"{name:8} {count}")

    denies = events.get("spawn_deny", 0)
    cdenies = events.get("clarify_deny", 0)
    passes = events.get("spawn_pass_over_threshold", 0)
    if denies or passes or cdenies:
        # Both deny kinds share this line on purpose: a spawn blocked
        # for a missing `## Clarified` record is still an over-threshold
        # spawn, and leaving it out reported zero denies on a session
        # that was blocked.
        print(f"\nover-threshold spawns: {passes} passed the gates, "
              f"{denies} denied for a missing or stale ledger, "
              f"{cdenies} denied by the clarify gate (`## Clarified` missing or incomplete)")

    tdenies = events.get("tasks_deny", 0)
    tcdenies = events.get("tasks_clarify_deny", 0)
    tsupp = events.get("tasks_suppressed", 0)
    if tdenies or tsupp or tcdenies:
        print(f"\nsolo multi-phase nudges: {tdenies} denied for the ledger, "
              f"{tcdenies} denied for clarification, "
              f"{tsupp} further tasks after a reminder")

    switches = events.get("inject_switch", 0)
    if switches:
        # Deliberately NOT folded into the profile counter above: that
        # one counts sessions, and a switch is the same session moving
        # tiers mid-flight.
        print(f"\nmid-session profile switches: {switches} "
              f"(short delta injected, not the full core)")

    if by_tier:
        total = sum(by_tier.values())
        print(f"\n== where the spawns ran ({total} allowed spawns) ==")
        for name in ("cheap", "bulk", "heavy", "chair"):
            n = by_tier.get(name, 0)
            print(f"{name:6} {n:6}  {100 * n / total:5.1f}%")
        pricey = by_tier.get("heavy", 0) + by_tier.get("chair", 0)
        if total and pricey / total > 0.35:
            print(f"  note: {100 * pricey / total:.0f}% of spawns ran on heavy or the chair. "
                  "Verify and implement belong on bulk, scans on cheap.")
        if total and by_tier.get("cheap", 0) == 0:
            print("  note: the cheap tier never ran. Send grep/fetch/count work to orch-scout.")

    if by_class:
        print("\n== routed spawns by class and tier (over the threshold) ==")
        for name, count in by_class.most_common():
            print(f"{count:6}  {name}")

    if route_denies:
        print("\n== route guard denials by reason ==")
        for name, count in route_denies.most_common():
            print(f"{count:6}  {name}")

    solo = events.get("solo_deny", 0)
    unnamed = events.get("unnamed_spawn_deny", 0)
    if solo or unnamed:
        print(f"\nchair nudges: {solo} solo-edit denies (chair editing with no worker), "
              f"{unnamed} unnamed-spawn denies")

    bwarn = events.get("budget_warn", 0)
    bcap = events.get("budget_cap", 0)
    if bwarn or bcap:
        print(f"\nbudget: {bwarn} checkpoints hit, {bcap} spawns stopped at a cap")

    if switch_fires:
        print("\n== profile changes delivered as a full core ==")
        for name, count in switch_fires.most_common():
            print(f"{count:6}  {name}")

    if swarm_reaped:
        print(f"\ntmux teammate servers reaped: {swarm_reaped}")
    if panes_reaped:
        print(f"idle teammate panes reaped: {panes_reaped}")

    if ledgers:
        print("\n== stop blocks by ledger ==")
        for name, count in ledgers.most_common(5):
            print(f"{count:5}  {name}")


if __name__ == "__main__":
    main()
