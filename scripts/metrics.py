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

# form-field vocabulary (ADDED 2026-08-23). The 8/22 batch scored 0 hits on
# SCENES while concentrating 20-90x on document fields instead -- the defect
# layer migrated from physical space to paperwork. SCENES is NOT modified.
FORM_FIELDS = ['備註', '單號', '編號', '案號', '品名', '規格', '狀態', '期限',
               '申請人', '受理']

CJK = re.compile(r'[一-鿿]')

# --- ordinal enumeration frame (ADDED 2026-08-26) --------------------------
# The 8/25 batch put a 第一次…第二次/第三次 progression in 14/168 items = 8.3%,
# spread over 14 unrelated topics, against a corpus baseline of 0.3% (24x).
# max_rare_ngram read 3.6% and passed, because it is blind to this by
# construction: the frame's surface form changes with a single character
# (第一次我 / 第一次是 / 第一次沖 / 第一次陪), so a character 4-gram splits one
# skeleton into fragments that each sit under the limit. max_rare_ngram
# measures a repeated WORD; this measures a repeated SKELETON.
# Nothing above is modified. The progression is a good device -- the correct
# remedy is a quota, not deletion.
ORDINAL_FIRST = re.compile(r'第一次')
ORDINAL_LATER = re.compile(r'第[二三]次')
ORDINAL_ENUM_LIMIT = 3.0   # batch share %; above this = skeleton reuse to act on


def is_ordinal_enum(text):
    """Item carries 第一次 AND 第二次/第三次 -- the ordinal progression frame."""
    return bool(ORDINAL_FIRST.search(text) and ORDINAL_LATER.search(text))


# --- waiting/service-queue vocabulary (ADDED 2026-08-24) --------------------
# The 8/23 batch scored low on SCENES and FORM_FIELDS while concentrating on
# service-queue locations instead (櫃檯 alone hit 10.7%, twice the 陽台 reading
# that was ruled a defect on 8/20). Measured as a HYPERNYM union, because a
# per-word cap of ~5% each still lets the class total reach ~19%.
# SCENES and FORM_FIELDS are NOT modified.
WAITING = ['櫃檯', '候診', '號碼牌', '叫號', '排隊', '等候']

# --- rare n-gram fingerprint (ADDED 2026-08-24) ----------------------------
# Character-overlap similarity reads 0 pairs on a batch where one frame was
# reused 8 times across 8 unrelated topics, because each retelling used a
# different scene and only the frame NAME survives verbatim. A 4-char CJK
# n-gram that is rare corpus-wide but repeats within a single batch is exactly
# that surviving fingerprint. Frozen definition; threshold is advisory.
NGRAM_N = 4
RARE_DF_MAX = 30        # corpus doc-frequency at or below this counts as rare
MAX_RARE_NGRAM_LIMIT = 5.0   # batch share %; >limit = frame reuse to act on
EXCLUDE_MIN_HITS = 3    # a rare n-gram seen this many times in a day is banned
EXCLUDE_WINDOW_DAYS = 7


def cjk_ngrams(text, n=NGRAM_N):
    """Set of n-char CJK n-grams in text (punctuation/latin stripped first)."""
    s = ''.join(CJK.findall(text))
    return {s[i:i + n] for i in range(len(s) - n + 1)}


def ngram_df(rows, n=NGRAM_N):
    """Document frequency of every n-gram across rows."""
    df = collections.Counter()
    for _, _, c, _ in rows:
        df.update(cjk_ngrams(c, n))
    return df


def rare_ngram_hits(rows, corpus_df, rare_df_max=RARE_DF_MAX):
    """n-grams repeating inside `rows` that are rare in the corpus at large.

    Returns Counter of ngram -> how many items in `rows` contain it, keeping
    only n-grams whose corpus-wide document frequency is <= rare_df_max.
    """
    batch = ngram_df(rows)
    return collections.Counter({
        g: c for g, c in batch.items()
        if c > 1 and corpus_df.get(g, 0) <= rare_df_max
    })


DEDUP_CANDIDATE_LIMIT = 800


def redundant_ngrams(hits, limit=DEDUP_CANDIDATE_LIMIT):
    """Drop n-grams fully contained in a longer/equal-count sibling.

    "借還登記" and "還登記簿" are the same fingerprint seen through a sliding
    window; report the family once instead of four times.

    The containment pass is quadratic, so only the `limit` highest-count
    candidates are folded. A single day's batch never approaches that cap;
    it exists so a whole-corpus run stays tractable. Ordering is
    (-count, term), so the cut is deterministic and never drops a term that
    outranks a surviving one.
    """
    ranked = sorted(hits.items(), key=lambda kv: (-kv[1], kv[0]))[:limit]
    keep = {}
    for g, c in ranked:
        if any(c <= kc and (g in k or k in g) for k, kc in keep.items()):
            continue
        keep[g] = c
    return collections.Counter(keep)


NGRAM_FAMILY_MIN_OVERLAP = 3


def _overlaps(a, b, min_overlap=NGRAM_FAMILY_MIN_OVERLAP):
    """True if a and b are windows onto the same longer phrase."""
    if a in b or b in a:
        return True
    for k in range(1, len(a) - min_overlap + 1):
        if a[k:] == b[:len(a) - k]:
            return True
        if b[k:] == a[:len(b) - k]:
            return True
    return False


def ngram_families(hits, limit=DEDUP_CANDIDATE_LIMIT):
    """Fold sliding-window fragments of one long phrase into a single family.

    ADDED 2026-08-26. redundant_ngrams() folds on containment only, which is
    correct for a fixed-length word (借還登記 / 還登記簿) but fails on a long
    sentence skeleton: 「沒說出口的那句是」 surfaced as four separate entries
    (出口的那 x6 / 口的那句 x5 / 的那句是 x5 / 出口的是 x4) because no fragment
    contains another, so a 5-item family under-reported as scattered noise.
    Two n-grams join a family when they share >= NGRAM_FAMILY_MIN_OVERLAP
    characters as a prefix/suffix overlap. A family's count is its largest
    member's, so max_rare_ngram-style readings stay on the same scale.

    redundant_ngrams() and max_rare_ngram are NOT modified -- this is a second,
    additional view reported alongside them.
    """
    ranked = sorted(hits.items(), key=lambda kv: (-kv[1], kv[0]))[:limit]
    terms = [g for g, _ in ranked]
    parent = {g: g for g in terms}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i, a in enumerate(terms):
        for b in terms[i + 1:]:
            if _overlaps(a, b):
                ra, rb = find(a), find(b)
                if ra != rb:
                    parent[rb] = ra

    fams = collections.defaultdict(list)
    for g, c in ranked:
        fams[find(g)].append((g, c))
    out = {}
    for members in fams.values():
        members.sort(key=lambda kv: (-kv[1], kv[0]))
        head, cnt = members[0]
        label = head if len(members) == 1 else f'{head}+{len(members) - 1}'
        out[label] = cnt
    return collections.Counter(out)


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


def opening_5(text):
    """ADDED 2026-08-23. Same rule as opening() but 5 chars.

    opening() strips non-CJK before slicing, so an opener carrying an
    alphanumeric token ("報修單編號 A-2261|...") shifts a later character into
    the 6-char window and reads as a distinct opening. 5 chars catches the
    cross-file collisions 6 chars misses. opening() is unchanged.
    """
    return opening(text, 5)


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


def report(rows, label, corpus_df=None):
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

    print('\n-- form-field concentration (added 2026-08-23) --')
    ff = collections.Counter()
    for _, _, c, _ in rows:
        for w in FORM_FIELDS:
            if w in c:
                ff[w] += 1
    out['form_fields'] = ff.most_common(10)
    out['form_field_any_pct'] = round(
        sum(1 for _, _, c, _ in rows if any(w in c for w in FORM_FIELDS)) / n * 100, 1)
    for w, v in ff.most_common(10):
        print(f'  {w:<10} {v:>4}  {v/n*100:5.1f}%')
    print(f'  any form field      {out["form_field_any_pct"]}%')

    print('\n-- top openings (first 6 CJK chars, top 12) --')
    op = collections.Counter(opening(c) for _, _, c, _ in rows if c.strip())
    out['top_openings'] = op.most_common(12)
    for o, v in op.most_common(12):
        print(f'  {o:<8} {v:>4}  {v/n*100:5.1f}%')

    print('\n-- top openings, 5-char variant (added 2026-08-23) --')
    op5 = collections.Counter(opening_5(c) for _, _, c, _ in rows if c.strip())
    out['top_openings_5'] = op5.most_common(8)
    out['max_repeat_open5'] = op5.most_common(1)[0][1] if op5 else 0
    out['distinct_open5_pct'] = round(len(op5) / sum(op5.values()) * 100, 1) if op5 else None
    for o, v in op5.most_common(8):
        print(f'  {o:<8} {v:>4}  {v/n*100:5.1f}%')
    print(f'  max repeat {out["max_repeat_open5"]}   distinct {out["distinct_open5_pct"]}%')

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

    print('\n-- waiting-scene concentration (added 2026-08-24) --')
    wt = collections.Counter()
    for _, _, c, _ in rows:
        for w in WAITING:
            if w in c:
                wt[w] += 1
    out['waiting'] = wt.most_common(10)
    out['waiting_any_pct'] = round(
        sum(1 for _, _, c, _ in rows if any(w in c for w in WAITING)) / n * 100, 1)
    for w, v in wt.most_common(10):
        print(f'  {w:<10} {v:>4}  {v/n*100:5.1f}%')
    print(f'  any waiting word    {out["waiting_any_pct"]}%   (hypernym union)')

    print('\n-- rare n-gram fingerprint (added 2026-08-24) --')
    if corpus_df is None:
        corpus_df = ngram_df(load())
    hits = redundant_ngrams(rare_ngram_hits(rows, corpus_df))
    out['rare_ngrams'] = hits.most_common(10)
    if hits:
        top_g, top_c = hits.most_common(1)[0]
        out['max_rare_ngram'] = round(top_c / n * 100, 1)
        out['max_rare_ngram_term'] = top_g
        out['max_rare_ngram_count'] = top_c
    else:
        out['max_rare_ngram'] = 0.0
        out['max_rare_ngram_term'] = None
        out['max_rare_ngram_count'] = 0
    for g, v in hits.most_common(10):
        print(f'  {g:<10} {v:>4}  {v/n*100:5.1f}%')
    verdict = 'PASS' if out['max_rare_ngram'] <= MAX_RARE_NGRAM_LIMIT else 'OVER'
    print(f'  max_rare_ngram      {out["max_rare_ngram"]}%'
          f'  ({out["max_rare_ngram_term"]} x{out["max_rare_ngram_count"]})'
          f'  limit {MAX_RARE_NGRAM_LIMIT}%  [{verdict}]')

    print('\n-- n-gram families (added 2026-08-26; view above unchanged) --')
    fams = ngram_families(rare_ngram_hits(rows, corpus_df))
    out['ngram_families'] = fams.most_common(10)
    if fams:
        fg, fc = fams.most_common(1)[0]
        out['max_family_ngram'] = round(fc / n * 100, 1)
        out['max_family_ngram_term'] = fg
    else:
        out['max_family_ngram'] = 0.0
        out['max_family_ngram_term'] = None
    for g, v in fams.most_common(10):
        print(f'  {g:<14} {v:>4}  {v/n*100:5.1f}%')
    print(f'  max_family_ngram    {out["max_family_ngram"]}%  ({out["max_family_ngram_term"]})')

    print('\n-- ordinal enumeration frame (added 2026-08-26) --')
    oe = sum(1 for _, _, c, _ in rows if is_ordinal_enum(c))
    out['ordinal_enum_pct'] = round(oe / n * 100, 1)
    out['ordinal_enum_n'] = oe
    out['ordinal_enum_topics'] = sorted({s for s, _, c, _ in rows if is_ordinal_enum(c)})
    ov = 'PASS' if out['ordinal_enum_pct'] <= ORDINAL_ENUM_LIMIT else 'OVER'
    print(f'  ordinal_enum        {oe:>4}  {out["ordinal_enum_pct"]:5.1f}%'
          f'  limit {ORDINAL_ENUM_LIMIT}%  [{ov}]')
    print(f'  topics: {", ".join(out["ordinal_enum_topics"]) or "(none)"}')

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


# --- rolling exclusion list (ADDED 2026-08-24) ------------------------------
# The ban list handed to generators was previously derived from the frozen
# SCENES/FORM_FIELDS vocabularies, so it could only ever exclude words someone
# had already thought of. Terms the batch actually over-used (二手書店 x6 on
# 8/21) were never on it and came back untouched two days later. This builds
# the list from what was measured, over a rolling window.
EXCLUDE_PATH = os.path.join(os.path.dirname(__file__), 'exclusion-list.json')


def recent_dates(rows, days=EXCLUDE_WINDOW_DAYS):
    ds = sorted({it.get('dateAdded') for _, _, _, it in rows if it.get('dateAdded')})
    return ds[-days:]


def build_exclusion(all_rows, days=EXCLUDE_WINDOW_DAYS,
                    min_hits=EXCLUDE_MIN_HITS):
    corpus_df = ngram_df(all_rows)
    by_date = collections.defaultdict(list)
    for r in all_rows:
        by_date[r[3].get('dateAdded')].append(r)
    terms = {}
    for d in recent_dates(all_rows, days):
        raw = rare_ngram_hits(by_date[d], corpus_df)
        hits = redundant_ngrams(
            collections.Counter({g: c for g, c in raw.items() if c >= min_hits}))
        for g, c in hits.items():
            if c > terms.get(g, (0, ''))[0]:
                terms[g] = (c, d)
    words = sorted(terms.items(), key=lambda kv: (-kv[1][0], kv[0]))
    return {
        'generated_from': recent_dates(all_rows, days),
        'window_days': days,
        'min_hits': min_hits,
        'terms': [{'term': g, 'hits': c, 'date': d} for g, (c, d) in words],
    }


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--date')
    ap.add_argument('--json', action='store_true')
    ap.add_argument('--exclude', action='store_true',
                    help='rebuild the rolling rare-term exclusion list')
    a = ap.parse_args()

    if a.exclude:
        data = build_exclusion(load())
        with open(EXCLUDE_PATH, 'w', encoding='utf-8') as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
            fh.write('\n')
        print(f'exclusion list -> {EXCLUDE_PATH}')
        print(f'  window {data["generated_from"][0]}..{data["generated_from"][-1]}'
              f'  ({data["window_days"]} days, >={data["min_hits"]} hits)')
        print(f'  {len(data["terms"])} banned terms')
        for t in data['terms'][:20]:
            print(f'    {t["term"]:<10} x{t["hits"]}  ({t["date"]})')
        sys.exit(0)

    all_rows = load()
    corpus_df = ngram_df(all_rows)
    rows = load(a.date) if a.date else all_rows
    res = report(rows, a.date or 'whole corpus', corpus_df=corpus_df)
    if a.json:
        print('\nJSON:', json.dumps(res, ensure_ascii=False))
