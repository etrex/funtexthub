#!/usr/bin/env python3
"""Orchestrator-level acceptance check for one day's whole batch.

ADDED 2026-08-27. There is a class of defect a per-file checker cannot see by
construction: on 2026-08-25 all 42 topics passed check_new_items.py while five
groups of files opened with the same five characters as each other. Every
check here needs the whole batch in one place.

Usage:  python3 scripts/check_batch.py --date 2026-08-27
Exit code 0 = PASS, 1 = FAIL.
"""
import json, os, sys, argparse, collections

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import metrics as M

EXPECTED_TOPICS = 42
EXPECTED_PER_TOPIC = 4
SCENE_CLASS_LIMIT = 10.0    # % of batch a single hypernym class may occupy


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--date', required=True)
    a = ap.parse_args()

    asg = json.load(open(os.path.join(HERE, 'daily-assignment.json')))
    if asg.get('date') != a.date:
        print(f'FAIL  daily-assignment.json is for {asg.get("date")}, not {a.date}')
        return 1

    all_rows = M.load()
    corpus_df = M.ngram_df(all_rows)
    rows = [r for r in all_rows if r[3].get('dateAdded') == a.date]
    if not rows:
        print(f'FAIL  no items dated {a.date}')
        return 1
    n = len(rows)
    fails, notes = [], []

    # -- coverage: every topic contributed, and contributed the same amount ---
    per = collections.Counter(r[0] for r in rows)
    if len(per) != EXPECTED_TOPICS:
        missing = sorted(set(asg['topics']) - set(per))
        fails.append(f'coverage {len(per)}/{EXPECTED_TOPICS}; missing: {missing}')
    off = {t: c for t, c in per.items() if c != EXPECTED_PER_TOPIC}
    if off:
        fails.append(f'item count != {EXPECTED_PER_TOPIC} in: {off}')
    notes.append(f'coverage {len(per)}/{EXPECTED_TOPICS}, n={n}, '
                 f'distribution {dict(collections.Counter(per.values()))}')

    # -- cross-file opening collisions (the 8/25 defect) ---------------------
    op = collections.defaultdict(list)
    for slug, iid, c, _ in rows:
        if c.strip():
            op[M.opening_5(c)].append(f'{slug}:{iid}')
    coll = {o: v for o, v in op.items() if len(v) > 1}
    if coll:
        for o, v in sorted(coll.items(), key=lambda kv: -len(kv[1]))[:10]:
            fails.append(f'opening 「{o}」 collides across files: {v}')
    distinct = round(len(op) / sum(len(v) for v in op.values()) * 100, 1)
    notes.append(f'distinct_open5_pct {distinct}%  (want 100.0)')

    # -- per-frame newly minted register furniture (the 8/26 defect) ---------
    frame_of = {t: v['frame'] for t, v in asg['topics'].items()}
    minted = M.frame_new_grams(rows, corpus_df, frame_of)
    for f in sorted(minted):
        k = len(minted[f])
        if k > M.FRAME_NEW_GRAM_LIMIT:
            terms = ', '.join(g for g, _ in minted[f].most_common(8))
            fails.append(f'frame {f}: {k} newly-minted rare 4-grams '
                         f'(limit {M.FRAME_NEW_GRAM_LIMIT}): {terms}')
    notes.append(f'frame_new_gram_count max '
                 f'{max((len(v) for v in minted.values()), default=0)} '
                 f'(limit {M.FRAME_NEW_GRAM_LIMIT})')

    # -- 公文體 confined to the institutional-frame files --------------------
    inst = set(asg.get('institutional_frames', []))
    inst_topics = {t for t, f in frame_of.items() if f in inst}
    reg_rows = [r for r in rows if any(w in r[2] for w in M.REGISTER_DOC)]
    reg_pct = round(len(reg_rows) / n * 100, 1)
    leaked = sorted({r[0] for r in reg_rows} - inst_topics)
    if reg_pct > M.REGISTER_DOC_LIMIT:
        fails.append(f'公文體 union {reg_pct}% > {M.REGISTER_DOC_LIMIT}%')
    if leaked:
        fails.append(f'公文體 leaked outside {sorted(inst)} files: {leaked}')
    notes.append(f'register_doc {reg_pct}% (limit {M.REGISTER_DOC_LIMIT}%), '
                 f'confined to {sorted(inst_topics)}')

    # -- scene hypernym class concentration (the 8/24 defect) ---------------
    cls_of = {t: v.get('scene_class') for t, v in asg['topics'].items()}
    cls_items = collections.Counter(cls_of.get(r[0]) for r in rows)
    for cls, c in cls_items.most_common(3):
        pct = round(c / n * 100, 1)
        if pct > SCENE_CLASS_LIMIT:
            fails.append(f'scene class 「{cls}」 {pct}% > {SCENE_CLASS_LIMIT}%')
    top = cls_items.most_common(1)[0]
    notes.append(f'max scene class 「{top[0]}」 {round(top[1]/n*100,1)}% '
                 f'(limit {SCENE_CLASS_LIMIT}%)')

    # -- ordinal quota -------------------------------------------------------
    ordt = sorted({r[0] for r in rows if M.is_ordinal_enum(r[2])})
    ordn = sum(1 for r in rows if M.is_ordinal_enum(r[2]))
    ordpct = round(ordn / n * 100, 1)
    allowed = set(asg.get('ordinal_allowed', []))
    if ordpct > M.ORDINAL_ENUM_LIMIT:
        fails.append(f'ordinal_enum {ordpct}% > {M.ORDINAL_ENUM_LIMIT}%')
    stray = sorted(set(ordt) - allowed)
    if stray:
        fails.append(f'ordinal frame in unassigned topics: {stray}')
    notes.append(f'ordinal_enum {ordpct}% in {ordt or "(none)"}')

    # -- frozen batch-wide skeletons and vocab ------------------------------
    for name in ('not_x_but_y', 'not_x_just_y', 'six_frame'):
        h = sum(1 for r in rows if M.MARKERS[name].search(r[2]))
        if h:
            fails.append(f'{name} appears in {h} items '
                         f'({sorted({r[0] for r in rows if M.MARKERS[name].search(r[2])})})')
        notes.append(f'{name} {round(h/n*100,1)}%')
    wait = sum(1 for r in rows if any(w in r[2] for w in M.WAITING))
    if round(wait / n * 100, 1) > 10.0:
        fails.append(f'waiting union {round(wait/n*100,1)}% > 10.0%')
    notes.append(f'waiting union {round(wait/n*100,1)}% (limit 10.0%)')

    # -- prior-day exclusion terms, body AND label-stripped variations ------
    excl = [t['term'] for t in json.load(open(os.path.join(HERE, 'exclusion-list.json')))
            ['terms'] if t.get('date', '') < a.date]
    hits = collections.Counter()
    for slug, iid, c, it in rows:
        for text in M.item_texts(it):
            for t in excl:
                if t in text:
                    hits[t] += 1
    if hits:
        fails.append(f'exclusion-list terms reused: {hits.most_common(10)}')
    notes.append(f'exclusion-list ({len(excl)} prior terms) hits {sum(hits.values())}')

    # -- rare n-gram fingerprint --------------------------------------------
    rare = M.ngram_families(M.rare_ngram_hits(rows, corpus_df))
    if rare:
        g, c = rare.most_common(1)[0]
        pct = round(c / n * 100, 1)
        if pct > M.MAX_RARE_NGRAM_LIMIT:
            fails.append(f'max_rare_ngram {pct}% ({g}) > {M.MAX_RARE_NGRAM_LIMIT}%')
        notes.append(f'max_family_ngram {pct}% ({g})')

    # -- reserved named terms: present in owner, absent everywhere else -----
    for term, owner in asg.get('named_terms', {}).items():
        holders = sorted({r[0] for r in rows if term in r[2]})
        if owner not in holders:
            fails.append(f'reserved term 「{term}」 did not land in {owner}')
        extra = [h for h in holders if h != owner]
        if extra:
            fails.append(f'reserved term 「{term}」 leaked to {extra}')
        notes.append(f'named 「{term}」 -> {holders}')

    # -- integrity -----------------------------------------------------------
    for field, fn in (('sourceUrl', lambda it: it.get('sourceUrl')),
                      ('en content', lambda it: it['i18n'].get('en', {}).get('content', '').strip()),
                      ('zh editorNote', lambda it: it['i18n']['zh-tw'].get('editorNote', '').strip())):
        miss = [f'{r[0]}:{r[1]}' for r in rows if not fn(r[3])]
        if miss:
            fails.append(f'missing {field}: {miss[:10]}')
        notes.append(f'missing {field}: {len(miss)}')

    # -- cross-language line parity (the 8/28 defect) -----------------------
    mm = [r for r in rows if M.line_parity_mismatch(r[3])]
    coll = [r for r in rows if M.en_collapsed(r[3])]
    lp_pct = round(len(mm) / n * 100, 2)
    if lp_pct > M.LINE_PARITY_LIMIT:
        by = collections.Counter(r[0] for r in mm).most_common(6)
        fails.append(f'line_parity_mismatch {lp_pct}% > {M.LINE_PARITY_LIMIT}% '
                     f'({len(mm)} items, worst: {by})')
    if len(coll) > M.EN_COLLAPSED_LIMIT:
        fails.append(f'en_collapsed_to_1 = {len(coll)} > {M.EN_COLLAPSED_LIMIT}: '
                     f'{[f"{r[0]}:{r[1]}" for r in coll][:10]}')
    notes.append(f'line_parity_mismatch {lp_pct}% (limit {M.LINE_PARITY_LIMIT}%), '
                 f'en_collapsed_to_1 {len(coll)} (limit {M.EN_COLLAPSED_LIMIT})')

    for x in notes:
        print(f'  {x}')
    print()
    for f in fails:
        print('FAIL  ' + f)
    if fails:
        print(f'\nbatch {a.date}: {len(fails)} FAIL')
        return 1
    print(f'batch {a.date}: PASS ({n} items, {len(per)} topics)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
