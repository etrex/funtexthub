#!/usr/bin/env python3
"""Per-topic acceptance check for one day's newly added items.

ADDED 2026-08-26. Every measurement the daily report asks for, made runnable
by the subagent that wrote the items. The 8/21+ record is consistent: a rule
written only in the report prose lands at ~0%, a rule written into the
subagent's acceptance checklist lands at 100%.

2026-08-27: rules are now read from daily-assignment.json instead of being
hardcoded per day, so the checker does NOT need editing mid-run (editing it
on 8/26 wasted four in-flight agents). New this day: register-furniture bans
(the 公文體 layer), reserved named terms, and label-stripped variation scans.

Usage:  python3 scripts/check_new_items.py --topic <slug> --date 2026-08-27
Exit code 0 = PASS, 1 = FAIL (fix and re-run until PASS).
"""
import json, os, re, sys, argparse, collections

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import metrics as M

# Skeletons and tics banned batch-wide. Six consecutive days of 不是X是Y at
# 0.0% were the product of an active ban, not a habit that stuck -- the day it
# was left out of the brief it returned at 7.1%.
BANNED_PHRASES = ['沒說出口的那句是', '沒講出口的那句是', '才肯承認', '丟了一句']

# Register furniture minted by the 8/26 H3 (公文/施工告示) frame. These are not
# style choices, they are mandatory parts of the institutional register, so
# they must be banned at brief time rather than harvested afterwards -- the
# rolling exclusion list can only ever block them starting the NEXT day.
REGISTER_FURNITURE = ['敬請見諒', '不便之處', '造成不便', '預計完工',
                      '施工期間', '施工告示', '即日起', '請多包涵',
                      '特此通知', '如有疑問', '請儘速', '逾期']


def load_assignment(date):
    a = json.load(open(os.path.join(HERE, 'daily-assignment.json')))
    return a if a.get('date') == date else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--topic', required=True)
    ap.add_argument('--date', required=True)
    a = ap.parse_args()

    path = os.path.join(HERE, '..', 'src', 'content', 'topics', a.topic + '.json')
    try:
        d = json.load(open(path))
    except Exception as e:
        print(f'FAIL  invalid JSON: {e}')
        return 1

    asg = load_assignment(a.date)
    spec = (asg or {}).get('topics', {}).get(a.topic, {})
    ordinal_allowed = set((asg or {}).get('ordinal_allowed', []))
    ordinal_quota = (asg or {}).get('ordinal_quota_per_topic', 1)
    named = (asg or {}).get('named_terms', {})
    inst_frames = set((asg or {}).get('institutional_frames', []))
    my_frame = spec.get('frame')

    new = [it for it in d['items'] if it.get('dateAdded') == a.date]
    fails, warns = [], []

    if not 3 <= len(new) <= 5:
        fails.append(f'item count {len(new)} not in 3-5')

    # Only terms harvested on EARLIER days may be enforced. The exclusion list
    # is regenerated after each daily batch from that batch's own >=3-hit rare
    # n-grams, so loading every term and checking it against the same batch is
    # circular: on 2026-08-26 that self-reference produced 100+ phantom FAILs
    # across 26 topics while the genuine prior-day collisions numbered 13.
    excl = [t['term'] for t in json.load(
        open(os.path.join(HERE, 'exclusion-list.json')))['terms']
        if t.get('date', '') < a.date]
    frozen_vocab = M.SCENES + M.WAITING + M.FORM_FIELDS

    ids = set()
    for it in new:
        iid = it.get('id', '?')
        if iid in ids:
            fails.append(f'{iid}: duplicate id')
        ids.add(iid)
        zh = it.get('i18n', {}).get('zh-tw', {})
        en = it.get('i18n', {}).get('en', {})
        c = zh.get('content', '')
        if not it.get('sourceUrl'):
            fails.append(f'{iid}: missing sourceUrl')
        if not en.get('content', '').strip():
            fails.append(f'{iid}: missing en content')
        if not zh.get('editorNote', '').strip():
            fails.append(f'{iid}: missing zh editorNote')
        if not en.get('editorNote', '').strip():
            fails.append(f'{iid}: missing en editorNote')
        if not it.get('tags'):
            fails.append(f'{iid}: missing tags')
        if not c.strip():
            fails.append(f'{iid}: empty zh content')
            continue

        # Scan variations as well as the body: on 2026-08-26 the body was
        # 0/168 clean on prior-day exclusion terms while 13 items carried one
        # in a variation -- the whole residue lived in the unscanned field.
        # The 「標籤：」 prefix is stripped first: it is site convention since
        # April (29.2% of 54,079 variations), NOT leaked brief text, and an
        # unstripped scan misreads the convention as a frame fingerprint.
        variants = [M.strip_label(v) for v in (zh.get('variations') or [])
                    if v and v.strip()]
        targets = [('', c)] + [(f' in zh variation {vi}', v)
                               for vi, v in enumerate(variants)]

        for label, text in targets:
            for p in BANNED_PHRASES:
                if p in text:
                    fails.append(f'{iid}: banned phrase 「{p}」{label}')
            for p in REGISTER_FURNITURE:
                if p in text:
                    fails.append(f'{iid}: register furniture 「{p}」{label}')
            if M.MARKERS['not_x_but_y'].search(text):
                fails.append(f'{iid}: banned skeleton 不是X是Y{label}')
            if M.MARKERS['not_x_just_y'].search(text):
                fails.append(f'{iid}: banned skeleton 不是X只是Y{label}')
            if M.MARKERS['six_frame'].search(text):
                fails.append(f'{iid}: banned 第一、第二 enumeration{label}')
            if M.is_ordinal_enum(text) and a.topic not in ordinal_allowed:
                fails.append(f'{iid}: ordinal 第一次…第二次/第三次 frame '
                             f'not allowed here{label}')
            for t in excl:
                if t in text:
                    fails.append(f'{iid}: exclusion-list term 「{t}」{label}')
            for w in frozen_vocab:
                if w in text:
                    fails.append(f'{iid}: frozen over-used vocab 「{w}」{label}')
            # 公文體 vocabulary is confined to the files assigned an
            # institutional frame. Same denominator error as 8/26: a word at
            # 2.4% of the batch was 25% inside its own frame.
            if my_frame not in inst_frames:
                for w in M.REGISTER_DOC:
                    if w in text:
                        fails.append(f'{iid}: 公文體 word 「{w}」 is confined to '
                                     f'{sorted(inst_frames)} files{label}')
            # reserved scene nouns: an assigned word leaks to other topics
            # unless the brief says "this file only" (8/26: 校車 hit 4 files).
            for term, owner in named.items():
                if term in text and a.topic != owner:
                    fails.append(f'{iid}: 「{term}」 is reserved for {owner}{label}')

        # sentence-count range clause (prose 3-5 sentences, list frames 5-8 lines)
        if M.is_list_frame_v2(c):
            lines = len([l for l in c.split('\n') if l.strip()])
            if not 5 <= lines <= 8:
                warns.append(f'{iid}: list frame has {lines} lines (want 5-8)')
        else:
            sc = M.sentence_count(c)
            if not 3 <= sc <= 5:
                warns.append(f'{iid}: prose has {sc} sentences (want 3-5)')

    # ordinal quota is ONE item per allowed topic (5 topics x 1 = 5 items =
    # 3.0% of a 168-item batch, which is the threshold). 2 each doubles it.
    if a.topic in ordinal_allowed:
        no = sum(1 for it in new
                 if M.is_ordinal_enum(it['i18n']['zh-tw'].get('content', '')))
        if no > ordinal_quota:
            fails.append(f'ordinal frame used in {no} items; '
                         f'quota is {ordinal_quota} for this topic')

    # openings must be distinct inside the file (all items, not just new)
    op = collections.Counter(M.opening_5(it['i18n']['zh-tw'].get('content', ''))
                             for it in d['items']
                             if it['i18n']['zh-tw'].get('content', '').strip())
    for it in new:
        o = M.opening_5(it['i18n']['zh-tw'].get('content', ''))
        if op[o] > 1:
            fails.append(f"{it.get('id')}: opening 「{o}」 collides inside this file")

    # assigned scene landed? (ADDED mid-run 2026-08-26: the checker verified the
    # named words but never the per-topic scene, so an agent could PASS while
    # silently dropping its scene -- caught by a subagent, not by us.)
    if spec:
        toks = spec.get('scene_tokens') or [spec['scene']]
        got = sum(1 for it in new
                  if any(t in it['i18n']['zh-tw'].get('content', '') for t in toks))
        need = asg.get('min_scene_items', 2)
        if got < need:
            fails.append(f'assigned scene 「{spec["scene"]}」 landed in {got} '
                         f'items, need >= {need}')

    # this topic's own reserved term must actually land
    for term, owner in named.items():
        if owner == a.topic and not any(
                term in i['i18n']['zh-tw'].get('content', '') for i in new):
            fails.append(f'reserved assignment 「{term}」 did not land')

    for w in warns:
        print('WARN  ' + w)
    for f in fails:
        print('FAIL  ' + f)
    if fails:
        print(f'\n{a.topic}: {len(fails)} FAIL, {len(warns)} warn -- fix and re-run')
        return 1
    print(f'\n{a.topic}: PASS ({len(new)} new items, {len(warns)} warn)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
