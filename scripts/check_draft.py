#!/usr/bin/env python3
"""Pre-flight check for a day's draft items BEFORE they are appended.

ADDED 2026-08-31. Same rule set as check_new_items.py, but reads the 4 new
items from a standalone draft JSON file (a list of item objects) instead of
from the topic file. 2026-08-30's batch showed that agents which drafted in
the scratchpad and pre-checked there passed check_new_items.py on the first
run; agents that edited first spent several rounds fixing the real file.

Usage:
  python3 scripts/check_draft.py --topic <slug> --date 2026-08-31 \
      --draft /path/to/<slug>-draft.json
Exit 0 = clean, 1 = problems (fix the draft, re-run, only then Edit).
"""
import json, os, sys, argparse, collections

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import metrics as M
from check_new_items import BANNED_PHRASES, REGISTER_FURNITURE


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--topic', required=True)
    ap.add_argument('--date', required=True)
    ap.add_argument('--draft', required=True)
    a = ap.parse_args()

    try:
        new = json.load(open(a.draft, encoding='utf-8'))
    except Exception as e:
        print(f'FAIL  draft is not valid JSON: {e}')
        return 1
    if isinstance(new, dict):
        new = new.get('items', [])
    if not isinstance(new, list):
        print('FAIL  draft must be a JSON list of item objects')
        return 1

    topic_path = os.path.join(HERE, '..', 'src', 'content', 'topics',
                              a.topic + '.json')
    existing = json.load(open(topic_path, encoding='utf-8'))['items']

    asg = json.load(open(os.path.join(HERE, 'daily-assignment.json')))
    asg = asg if asg.get('date') == a.date else {}
    spec = asg.get('topics', {}).get(a.topic, {})
    ordinal_allowed = set(asg.get('ordinal_allowed', []))
    named = asg.get('named_terms', {})
    inst_frames = set(asg.get('institutional_frames', []))
    my_frame = spec.get('frame')

    excl = [t['term'] for t in json.load(
        open(os.path.join(HERE, 'exclusion-list.json')))['terms']
        if t.get('date', '') < a.date]
    frozen_vocab = M.SCENES + M.WAITING + M.FORM_FIELDS

    fails, warns = [], []
    if len(new) != 4:
        fails.append(f'item count {len(new)} (want 4)')

    old_ids = {it.get('id') for it in existing}
    old_open = collections.Counter(
        M.opening_5(it['i18n']['zh-tw'].get('content', '')) for it in existing
        if it['i18n']['zh-tw'].get('content', '').strip())

    seen = set()
    for it in new:
        iid = it.get('id', '?')
        if iid in old_ids:
            fails.append(f'{iid}: id already exists in the topic file')
        if iid in seen:
            fails.append(f'{iid}: duplicate id inside the draft')
        seen.add(iid)
        if it.get('dateAdded') != a.date:
            fails.append(f'{iid}: dateAdded is {it.get("dateAdded")!r}, want {a.date}')
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
        zl, el = M.line_counts(it)
        if zl != el:
            fails.append(f'{iid}: zh content has {zl} line(s) but en has {el} '
                         f'-- en must break at the SAME points as zh')
        if not c.strip():
            fails.append(f'{iid}: empty zh content')
            continue

        variants = [M.strip_label(v) for v in (zh.get('variations') or [])
                    if v and v.strip()]
        for label, text in [('', c)] + [(f' in zh variation {i}', v)
                                        for i, v in enumerate(variants)]:
            for p in BANNED_PHRASES:
                if p in text:
                    fails.append(f'{iid}: banned phrase 「{p}」{label}')
            for p in REGISTER_FURNITURE:
                if p in text:
                    fails.append(f'{iid}: register furniture 「{p}」{label}')
            for key, msg in (('not_x_but_y', '不是X是Y'),
                             ('not_x_just_y', '不是X只是Y'),
                             ('six_frame', '第一、第二 enumeration')):
                if M.MARKERS[key].search(text):
                    fails.append(f'{iid}: banned skeleton {msg}{label}')
            if M.is_ordinal_enum(text) and a.topic not in ordinal_allowed:
                fails.append(f'{iid}: ordinal frame not allowed here{label}')
            for t in excl:
                if t in text:
                    fails.append(f'{iid}: exclusion-list term 「{t}」{label}')
            for w in frozen_vocab:
                if w in text:
                    fails.append(f'{iid}: frozen over-used vocab 「{w}」{label}')
            if my_frame not in inst_frames:
                for w in M.REGISTER_DOC:
                    if w in text:
                        fails.append(f'{iid}: 公文體 word 「{w}」 is confined to '
                                     f'{sorted(inst_frames)} files{label}')
            for term, owner in named.items():
                if term in text and a.topic != owner:
                    fails.append(f'{iid}: 「{term}」 is reserved for {owner}{label}')

        if M.is_list_frame_v2(c):
            lines = len([l for l in c.split('\n') if l.strip()])
            if not 5 <= lines <= 8:
                warns.append(f'{iid}: list frame has {lines} lines (want 5-8)')
        else:
            sc = M.sentence_count(c)
            if not 3 <= sc <= 5:
                warns.append(f'{iid}: prose has {sc} sentences (want 3-5)')

    draft_open = collections.Counter(
        M.opening_5(it.get('i18n', {}).get('zh-tw', {}).get('content', ''))
        for it in new)
    for o, n in draft_open.items():
        if n > 1 or old_open.get(o):
            fails.append(f'opening 「{o}」 collides '
                         f'({"inside the draft" if n > 1 else "with an existing item"})')

    if spec:
        toks = spec.get('scene_tokens') or [spec['scene']]
        got = sum(1 for it in new
                  if any(t in it.get('i18n', {}).get('zh-tw', {}).get('content', '')
                         for t in toks))
        need = asg.get('min_scene_items', 2)
        if got < need:
            fails.append(f'assigned scene 「{spec["scene"]}」 landed in {got} '
                         f'items, need >= {need}')
    for term, owner in named.items():
        if owner == a.topic and not any(
                term in i.get('i18n', {}).get('zh-tw', {}).get('content', '')
                for i in new):
            fails.append(f'reserved assignment 「{term}」 did not land')

    for w in warns:
        print('WARN  ' + w)
    for f in fails:
        print('FAIL  ' + f)
    if fails:
        print(f'\ndraft {a.topic}: {len(fails)} FAIL, {len(warns)} warn '
              f'-- fix the DRAFT and re-run before editing the topic file')
        return 1
    print(f'\ndraft {a.topic}: CLEAN ({len(new)} items, {len(warns)} warn) '
          f'-- safe to append')
    return 0


if __name__ == '__main__':
    sys.exit(main())
