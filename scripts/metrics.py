#!/usr/bin/env python3
"""FunTextHub frozen content metrics.

FROZEN DETECTOR -- do not redefine the measurements below.
Cross-day comparisons are only valid if the definitions never move.
If a measurement genuinely must change, add a NEW named metric and keep
the old one intact, so historical readings stay comparable.

Usage:
  python3 scripts/metrics.py                # whole corpus
  python3 scripts/metrics.py --date 2026-08-21   # one day's batch
  python3 scripts/metrics.py --json         # machine-readable
"""
import json, glob, re, argparse, collections, sys, os

TOPICS = os.path.join(os.path.dirname(__file__), '..', 'src', 'content', 'topics', '*.json')

# --- frozen marker definitions -------------------------------------------
MARKERS = {
    'not_x_but_y':   re.compile(r'不是.{1,12}[，,]?\s*(?:而是|是)'),
    # added 2026-08-22: the "不是X，只是Y" variant escapes not_x_but_y.
    # NOT a redefinition -- not_x_but_y above is unchanged and stays comparable.
    'not_x_just_y':  re.compile(r'不是.{1,12}[，,]?\s*只是'),
    'mind_mouth':    re.compile(r'(?:嘴上|嘴巴).{0,10}(?:心裡|心底)|(?:心裡|心底).{0,10}(?:嘴上|嘴巴)'),
    'six_frame':     re.compile(r'第[一二三四五六]\s*[、.]'),
    'list_style':    re.compile(r'^\s*(?:[-–—•*]|\d+[.、)])\s', re.M),
    'unruled_quote': re.compile(r'[「『"][^」』"]{1,40}[」』"]'),
    'receipt':       re.compile(r'(?:收據|明細|帳單|品項|小計|合計|總計)'),
}

# frozen scene vocabulary (locations that showed over-concentration)
SCENES = ['自助洗衣店', '樓梯間', '洗衣機', '陽台', '便利商店', '公車站', '電梯',
          '頂樓', '廚房', '浴室', '捷運', '停車場', '樓下', '巷口']

CJK = re.compile(r'[一-鿿]')


def load(date=None):
    rows = []
    for f in sorted(glob.glob(TOPICS)):
        d = json.load(open(f))
        for it in d['items']:
            if date and it.get('dateAdded') != date:
                continue
            rows.append((d['slug'], it['id'], it['i18n']['zh-tw'].get('content', ''), it))
    return rows


def opening(text, n=6):
    """First n CJK chars of the first line -- frozen definition."""
    first = text.split('\n')[0]
    return ''.join(CJK.findall(first))[:n]


def sentence_count(text):
    return len([s for s in re.split(r'[。！？!?]', text) if s.strip()])


def is_list_frame(text):
    return bool(MARKERS['list_style'].search(text) or MARKERS['receipt'].search(text))


# --- v2 frame classifier (ADDED 2026-08-22) ---------------------------------
# Does NOT replace is_list_frame() above -- that stays frozen and comparable.
# Rationale: label-colon frames (工單/說明書/廣播稿/成就解鎖/田野紀錄) and pure
# dialogue carry no periods by design, so the frozen classifier filed them as
# prose and made prose_4sent_pct read artificially low.
LABEL_LINE = re.compile(r'^\s*[^\s：:]{1,14}[：:]')
DIALOG_LINE = re.compile(r'^\s*[「『]')


def is_list_frame_v2(text):
    if is_list_frame(text):
        return True
    lines = [l for l in text.split('\n') if l.strip()]
    if len(lines) < 4:
        return False
    labelled = sum(1 for l in lines if LABEL_LINE.match(l))
    spoken = sum(1 for l in lines if DIALOG_LINE.match(l))
    return labelled >= 3 or spoken >= 3


def report(rows, label):
    n = len(rows)
    if not n:
        print(f'no items for {label}')
        return {}
    out = {'label': label, 'n': n}
    print(f'=== {label}  (n={n}) ===')

    print('\n-- marker share --')
    for name, rx in MARKERS.items():
        hits = sum(1 for _, _, c, _ in rows if rx.search(c))
        out[name] = round(hits / n * 100, 1)
        print(f'  {name:<14} {hits:>5}  {hits/n*100:5.1f}%')

    print('\n-- scene concentration (top 10) --')
    sc = collections.Counter()
    for _, _, c, _ in rows:
        for s in SCENES:
            if s in c:
                sc[s] += 1
    out['scenes'] = sc.most_common(10)
    for s, v in sc.most_common(10):
        print(f'  {s:<10} {v:>4}  {v/n*100:5.1f}%')

    print('\n-- top openings (first 6 CJK chars, top 12) --')
    op = collections.Counter(opening(c) for _, _, c, _ in rows if c.strip())
    out['top_openings'] = op.most_common(12)
    for o, v in op.most_common(12):
        print(f'  {o:<8} {v:>4}  {v/n*100:5.1f}%')

    print('\n-- length / shape --')
    lens = [len(c) for _, _, c, _ in rows]
    out['mean_len'] = round(sum(lens) / n, 1)
    ml = sum(1 for _, _, c, _ in rows if '\n' in c)
    out['multiline_pct'] = round(ml / n * 100, 1)
    print(f'  mean zh-tw length   {out["mean_len"]}')
    print(f'  multi-line share    {out["multiline_pct"]}%')

    print('\n-- sentence count (range clause: prose 4, list frames 5-8 lines) --')
    prose = [c for _, _, c, _ in rows if not is_list_frame(c)]
    lists = [c for _, _, c, _ in rows if is_list_frame(c)]
    p4 = sum(1 for c in prose if sentence_count(c) == 4)
    lok = sum(1 for c in lists if 5 <= len([l for l in c.split('\n') if l.strip()]) <= 8)
    out['prose_n'], out['list_n'] = len(prose), len(lists)
    out['prose_4sent_pct'] = round(p4 / len(prose) * 100, 1) if prose else None
    out['list_inrange_pct'] = round(lok / len(lists) * 100, 1) if lists else None
    print(f'  prose items {len(prose):>5}   exactly 4 sentences: {out["prose_4sent_pct"]}%')
    print(f'  list  items {len(lists):>5}   5-8 lines:           {out["list_inrange_pct"]}%')

    print('\n-- v2 frame split (added 2026-08-22; metrics above unchanged) --')
    prose2 = [c for _, _, c, _ in rows if not is_list_frame_v2(c)]
    lists2 = [c for _, _, c, _ in rows if is_list_frame_v2(c)]
    p2 = sum(1 for c in prose2 if 3 <= sentence_count(c) <= 5)
    l2 = sum(1 for c in lists2 if 5 <= len([l for l in c.split('\n') if l.strip()]) <= 8)
    out['prose_v2_n'], out['list_v2_n'] = len(prose2), len(lists2)
    out['prose_v2_3to5sent_pct'] = round(p2 / len(prose2) * 100, 1) if prose2 else None
    out['list_v2_inrange_pct'] = round(l2 / len(lists2) * 100, 1) if lists2 else None
    print(f'  prose_v2 {len(prose2):>5}   3-5 sentences: {out["prose_v2_3to5sent_pct"]}%')
    print(f'  list_v2  {len(lists2):>5}   5-8 lines:     {out["list_v2_inrange_pct"]}%')

    print('\n-- integrity --')
    nosrc = sum(1 for _, _, _, it in rows if not it.get('sourceUrl'))
    noten = sum(1 for _, _, _, it in rows
                if not it['i18n'].get('en', {}).get('content', '').strip())
    nonote = sum(1 for _, _, _, it in rows
                 if not it['i18n']['zh-tw'].get('editorNote', '').strip())
    out['missing_sourceurl'] = nosrc
    out['missing_en'] = noten
    out['missing_editornote'] = nonote
    print(f'  missing sourceUrl   {nosrc}')
    print(f'  missing en content  {noten}')
    print(f'  missing editorNote  {nonote}')
    return out


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--date')
    ap.add_argument('--json', action='store_true')
    a = ap.parse_args()
    rows = load(a.date)
    res = report(rows, a.date or 'whole corpus')
    if a.json:
        print('\nJSON:', json.dumps(res, ensure_ascii=False))
