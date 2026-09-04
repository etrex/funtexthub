#!/usr/bin/env python3
"""Structural-form mix / monoculture detector  (added 2026-09-03)

Frozen instrument for the "form monoculture" axis: within one (topic file, date)
cell, do all N items share the same structural form?

Existing gates are blind to this axis by construction — `max_within_file_gram`
and `distinct_open5_pct` compare CHARACTERS, and four items can be four
different sentences that are all, structurally, the same shape.

Forms
  oneline   single non-blank line
  dialogue  first line opens with 「 AND >=75% of lines open with 「
  list      >=3 lines, >=60% short (<=18 chars), >=50% without terminal 。！？…
  prose     everything else

Reader-visible collapse (added 2026-09-04)
  `oneline` and `prose` differ only by whether the paragraph carries line breaks;
  in the rotation era 100% of `oneline` items are multi-sentence, so a reader
  experiences them as the same shape. Any rule written against the raw four
  categories can therefore be satisfied invisibly, by unwrapping one prose item.
  So both readings are reported side by side, and neither replaces the other:
    raw       prose / oneline / list / dialogue   (what the rule was written against)
    collapsed prose* (= prose+oneline) / list / dialogue   (what a reader sees)
  On 2026-09-03 the two readings differed by 4.3x: 16.7% single-form raw vs
  71.4% collapsed. Exit status still follows the RAW reading, unchanged.

Null model: per file, draw each item independently from THAT file's own form
distribution since the rotation era. P(all 4 same) = sum(p_f^4). The ratio
observed/expected is the real signal — a topic that is naturally 95% prose is
not "monoculture" for writing prose.

Usage
  python3 scripts/form_mix.py                 # corpus summary, rotation era
  python3 scripts/form_mix.py --date 2026-09-03   # one batch, per-file detail
  python3 scripts/form_mix.py --since 2026-08-01
"""
import argparse, collections, glob, json, os, sys

ERA = '2026-08-01'          # rotation era start
TOPICS = os.path.join(os.path.dirname(__file__), '..', 'src', 'content', 'topics', '*.json')


def form(txt):
    lines = [l.strip() for l in txt.split('\n') if l.strip()]
    n = len(lines)
    if n == 0:
        return 'empty'
    if n == 1:
        return 'oneline'
    if lines[0][:1] == '「' and sum(1 for l in lines if l[:1] == '「') / n >= 0.75:
        return 'dialogue'
    if n >= 3:
        short = sum(1 for l in lines if len(l) <= 18) / n
        noend = sum(1 for l in lines if l[-1:] not in ('。', '！', '？', '…')) / n
        if short >= 0.6 and noend >= 0.5:
            return 'list'
    return 'prose'


READER_COLLAPSE = {'oneline': 'prose*', 'prose': 'prose*'}


def collapsed(fm):
    """Form as a reader distinguishes it: line-breaking alone is not a form."""
    return READER_COLLAPSE.get(fm, fm)


def load(since):
    cells = collections.defaultdict(list)      # (slug, date) -> [(form, id)]
    filemix = collections.defaultdict(collections.Counter)
    for f in sorted(glob.glob(TOPICS)):
        slug = os.path.basename(f)[:-5]
        for it in json.load(open(f))['items']:
            d = it.get('dateAdded', '?')
            fm = form(it['i18n']['zh-tw']['content'])
            cells[(slug, d)].append((fm, it['id']))
            if d >= since:
                filemix[slug][fm] += 1
    return cells, filemix


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--date', help='report one batch in detail')
    ap.add_argument('--since', default=ERA)
    ap.add_argument('--min-distinct', type=int, default=2,
                    help='required distinct forms per (file,date) cell')
    a = ap.parse_args()
    cells, filemix = load(a.since)

    if a.date:
        bad = []
        print(f'-- form mix {a.date} --')
        for (slug, d), items in sorted(cells.items()):
            if d != a.date:
                continue
            fs = [x[0] for x in items]
            k = len(set(fs))
            flag = 'MONO' if k < a.min_distinct else '    '
            if k < a.min_distinct:
                bad.append(slug)
            print(f'  {flag} {slug:26s} {",".join(fs)}')
        n = sum(1 for (s, d) in cells if d == a.date)
        if not n:
            print('  (no items on that date)')
            return 0
        cbad = [s for (s, d), its in cells.items() if d == a.date
                and len({collapsed(f) for f, _ in its}) < a.min_distinct]
        print(f'\n  single-form cells {len(bad)}/{n} ({len(bad)/n*100:.1f}%)'
              f'   want < {a.min_distinct} distinct: 0')
        print(f'  reader-visible    {len(cbad)}/{n} ({len(cbad)/n*100:.1f}%)'
              f'   (prose+oneline collapsed; reported, not gated)')
        mix = collections.Counter(f for (s, d), its in cells.items() if d == a.date
                                  for f, _ in its)
        t = sum(mix.values())
        print('  batch mix: ' + '  '.join(f'{k} {v/t*100:.1f}%' for k, v in mix.most_common()))
        return 1 if bad else 0

    obs = exp = tot = cobs = cexp = 0.0
    monoform = collections.Counter()
    cfilemix = collections.defaultdict(collections.Counter)
    for slug, m in filemix.items():
        for f, v in m.items():
            cfilemix[slug][collapsed(f)] += v
    for (slug, d), items in cells.items():
        if d < a.since or len(items) != 4:
            continue
        tot += 1
        fs = [x[0] for x in items]
        if len(set(fs)) == 1:
            obs += 1
            monoform[fs[0]] += 1
        if len({collapsed(f) for f in fs}) == 1:
            cobs += 1
        m = filemix[slug]
        n = sum(m.values())
        exp += sum((v / n) ** 4 for v in m.values())
        cm = cfilemix[slug]
        cn = sum(cm.values())
        cexp += sum((v / cn) ** 4 for v in cm.values())
    print(f'-- form monoculture (since {a.since}) --')
    print(f'  cells (n=4)            {int(tot)}')
    print(f'  observed single-form   {int(obs)}  ({obs/tot*100:.1f}%)')
    print(f'  expected (per-file H0) {exp:.1f}  ({exp/tot*100:.1f}%)')
    print(f'  over-concentration     {obs/exp:.2f}x')
    print('  mono by form: ' + ', '.join(f'{k} {v}' for k, v in monoform.most_common()))
    print(f'  -- reader-visible (prose+oneline collapsed; reported, not gated) --')
    print(f'  observed single-form   {int(cobs)}  ({cobs/tot*100:.1f}%)')
    print(f'  expected (per-file H0) {cexp:.1f}  ({cexp/tot*100:.1f}%)')
    print(f'  over-concentration     {cobs/cexp:.2f}x')
    mix = collections.Counter(f for (s, d), its in cells.items() if d >= a.since
                              for f, _ in its)
    t = sum(mix.values())
    print('  corpus mix:   ' + '  '.join(f'{k} {v/t*100:.1f}%' for k, v in mix.most_common()))
    return 0


if __name__ == '__main__':
    sys.exit(main())
