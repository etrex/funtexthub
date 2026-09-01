#!/usr/bin/env python3
"""Orchestrator-side append-only + gate verification for one day's topics.

Usage: python3 scripts/verify_batch.py <baseline-commit> <date> <slug> [slug...]
Independent of the subagents' self-reports: re-reads the files, diffs each
against the pre-run commit, and re-runs the per-topic gate itself.
"""
import json, subprocess, sys, os

HERE = os.path.dirname(os.path.abspath(__file__))
base, date, slugs = sys.argv[1], sys.argv[2], sys.argv[3:]
ok = True
for slug in slugs:
    p = f'src/content/topics/{slug}.json'
    try:
        new = json.load(open(os.path.join(HERE, '..', p)))
    except Exception as e:
        print(f'{slug:26s} BROKEN JSON: {e}'); ok = False; continue
    old = json.loads(subprocess.run(['git', 'show', f'{base}:{p}'],
                                    capture_output=True, text=True, cwd=os.path.join(HERE, '..')).stdout)
    o, n = old['items'], new['items']
    added = n[len(o):]
    probs = []
    if n[:len(o)] != o:
        probs.append('EXISTING ITEMS MODIFIED')
    if len(added) != 4:
        probs.append(f'added {len(added)} not 4')
    if any(i.get('dateAdded') != date for i in added):
        probs.append('wrong dateAdded on an appended item')
    g = subprocess.run(['python3', os.path.join(HERE, 'check_new_items.py'),
                        '--topic', slug, '--date', date],
                       capture_output=True, text=True)
    if g.returncode != 0:
        probs.append('GATE FAIL: ' + g.stdout.strip().replace('\n', ' | ')[:200])
    status = 'OK  ' if not probs else 'BAD '
    if probs: ok = False
    print(f'{status}{slug:26s} +{len(added)} {[i["id"] for i in added]}')
    for x in probs:
        print(f'      -> {x}')
sys.exit(0 if ok else 1)
