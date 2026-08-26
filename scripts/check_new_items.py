#!/usr/bin/env python3
"""Per-topic acceptance check for one day's newly added items.

ADDED 2026-08-26. Every measurement the daily report asks for, made runnable
by the subagent that wrote the items. The 8/21+ record is consistent: a rule
written only in the report prose lands at ~0%, a rule written into the
subagent's acceptance checklist lands at 100%.

Usage:  python3 scripts/check_new_items.py --topic <slug> --date 2026-08-26
Exit code 0 = PASS, 1 = FAIL (fix and re-run until PASS).
"""
import json, os, re, sys, argparse, collections

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import metrics as M

BANNED_PHRASES = ['沒說出口的那句是', '沒講出口的那句是', '才肯承認', '丟了一句']
ORDINAL_ALLOWED = {'diet-quotes', 'exam-quotes', 'insomnia-quotes',
                   'renting-quotes', 'stock-investor-quotes'}
E4_TERM, E4_TOPIC = '本宅住戶', 'holiday-jokes'
E3_TERM, E3_TOPIC = '對號座', 'concert-ticket-quotes'


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

    new = [it for it in d['items'] if it.get('dateAdded') == a.date]
    fails, warns = [], []

    if not 3 <= len(new) <= 5:
        fails.append(f'item count {len(new)} not in 3-5')

    excl = [t['term'] for t in json.load(
        open(os.path.join(HERE, 'exclusion-list.json')))['terms']]
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
        # scan zh variations too. A variation carries the same skeleton as the
        # body but lived outside the scan, so a banned construction could sit
        # in a variant and still report PASS.
        variants = [v for v in (zh.get('variations') or []) if v and v.strip()]
        for vi, v in enumerate(variants):
            for p_ in BANNED_PHRASES:
                if p_ in v:
                    fails.append(f'{iid}: banned phrase 「{p_}」 in zh variation {vi}')
            if M.MARKERS['not_x_but_y'].search(v):
                fails.append(f'{iid}: banned skeleton 不是X是Y in zh variation {vi}')
            if M.MARKERS['not_x_just_y'].search(v):
                fails.append(f'{iid}: banned skeleton 不是X只是Y in zh variation {vi}')
            if M.is_ordinal_enum(v) and a.topic not in ORDINAL_ALLOWED:
                fails.append(f'{iid}: ordinal frame in zh variation {vi}')

        for p in BANNED_PHRASES:
            if p in c:
                fails.append(f'{iid}: banned phrase 「{p}」')
        for t in excl:
            if t in c:
                fails.append(f'{iid}: exclusion-list term 「{t}」')
        for w in frozen_vocab:
            if w in c:
                fails.append(f'{iid}: frozen over-used vocab 「{w}」')
        if M.is_ordinal_enum(c) and a.topic not in ORDINAL_ALLOWED:
            fails.append(f'{iid}: ordinal 第一次…第二次/第三次 frame not allowed here')
        # batch-wide ban: the 不是X是Y / 不是X只是Y skeletons. Six consecutive days
        # at 0.0% were the product of an active ban, not a habit that stuck --
        # the moment the ban was left out of the brief it came back at 7.1%.
        if M.MARKERS['not_x_but_y'].search(c):
            fails.append(f'{iid}: banned skeleton 不是X是Y')
        if M.MARKERS['not_x_just_y'].search(c):
            fails.append(f'{iid}: banned skeleton 不是X只是Y')
        if E4_TERM in c and a.topic != E4_TOPIC:
            fails.append(f'{iid}: 「{E4_TERM}」 is reserved for {E4_TOPIC}')
        # sentence-count range clause (prose 3-5 sentences, list frames 5-8 lines)
        if M.is_list_frame_v2(c):
            lines = len([l for l in c.split('\n') if l.strip()])
            if not 5 <= lines <= 8:
                warns.append(f'{iid}: list frame has {lines} lines (want 5-8)')
        else:
            sc = M.sentence_count(c)
            if not 3 <= sc <= 5:
                warns.append(f'{iid}: prose has {sc} sentences (want 3-5)')

    # ordinal quota is ONE item per allowed topic (5 topics x 1 = 5 items = 3.0%
    # of a 168-item batch, which is the threshold). Allowing 2 each doubles it.
    if a.topic in ORDINAL_ALLOWED:
        no = sum(1 for it in new if M.is_ordinal_enum(it['i18n']['zh-tw'].get('content', '')))
        if no > 1:
            fails.append(f'ordinal frame used in {no} items; quota is 1 for this topic')

    # openings must be distinct inside the file (all items, not just new)
    op = collections.Counter(M.opening_5(it['i18n']['zh-tw'].get('content', ''))
                             for it in d['items']
                             if it['i18n']['zh-tw'].get('content', '').strip())
    for it in new:
        o = M.opening_5(it['i18n']['zh-tw'].get('content', ''))
        if op[o] > 1:
            fails.append(f"{it.get('id')}: opening 「{o}」 collides inside this file")

    # assigned scene landed? (ADDED mid-run 2026-08-26: the checker verified the
    # E3/E4 words but never the per-topic scene assignment, so an agent could
    # PASS while silently dropping its scene -- caught by a subagent, not by us.)
    try:
        asg = json.load(open(os.path.join(HERE, 'daily-assignment.json')))
    except Exception:
        asg = None
    if asg and asg.get('date') == a.date and a.topic in asg['topics']:
        spec = asg['topics'][a.topic]
        scene = spec['scene']
        toks = spec.get('scene_tokens') or [scene]
        got = sum(1 for it in new
                  if any(t in it['i18n']['zh-tw'].get('content', '') for t in toks))
        need = asg.get('min_scene_items', 2)
        if got < need:
            fails.append(f'assigned scene 「{scene}」 landed in {got} items, need >= {need}')

    # required assignment landed?
    if a.topic == E3_TOPIC and not any(E3_TERM in i['i18n']['zh-tw'].get('content', '')
                                       for i in new):
        fails.append(f'assignment E3 「{E3_TERM}」 did not land')
    if a.topic == E4_TOPIC and not any(E4_TERM in i['i18n']['zh-tw'].get('content', '')
                                       for i in new):
        fails.append(f'assignment E4 「{E4_TERM}」 did not land')

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
