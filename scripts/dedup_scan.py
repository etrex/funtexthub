#!/usr/bin/env python3
"""FunTextHub semantic near-duplicate cluster scan.

FROZEN DETECTOR -- do not redefine the similarity below.
Pairwise scanning UNDER-REPORTS clustering by ~3x: on 2026-08-23 a pairwise
scan at 0.45 showed healing-quotes as "4 unrelated pairs" when it was in fact
one 20-item cluster all retelling the same line. Union-find at 0.38 is what
surfaced it. Keep both the threshold and the transitive closure.

Usage:
  python3 scripts/dedup_scan.py                    # whole corpus
  python3 scripts/dedup_scan.py --date 2026-08-25  # one batch vs whole corpus
  python3 scripts/dedup_scan.py --min-size 8       # only large clusters
  python3 scripts/dedup_scan.py --lang en          # ENGLISH side (see below)

ENGLISH SIDE -- added 2026-09-04. The zh-tw detector above is BLIND to English
duplicates and its "0 clusters" was a false all-clear: on 2026-09-04 a scan of
the en field found 49 clusters / 107 items that the zh scan scored 0.00-0.32,
all of them genuine duplicates in BOTH languages (four copies of the "I love
deadlines / whooshing sound" line across three topics; four of the dark-mode
"light attracts bugs" joke). Chinese rewording drops char-bigram Jaccard below
0.38 even when the joke is identical, so zh alone can never see them.

Do NOT score English with the zh shingles: English char-bigrams saturate
(unrelated 100-word items score 0.66) and word-trigrams are too strict (a
reworded joke scores 0.05). Content-word Jaccard (stopwords dropped, len>2)
separates cleanly -- measured on 2026-09-04: real duplicates 0.22-0.73,
unrelated pairs 0.05-0.13.
"""
import json, glob, re, argparse, os, sys, collections

TOPICS = os.path.join(os.path.dirname(__file__), '..', 'src', 'content', 'topics', '*.json')
THRESHOLD = 0.38
EN_THRESHOLD = 0.40
CJK_PUNCT = re.compile(r'[\s，。！？、；：「」『』（）\-—…,.!?;:"\'()]+')

# Stopwords only -- deliberately not stemmed, so the score stays inspectable.
EN_STOP = set("""a an the and or but so if then than that this these those there here it its
is are was were be been being am i you he she they we me him her them us my your his their our
to of in on at for with without from by as into onto about over under up down out off just only
very really too also not no nor do does did done doing have has had having will would can could
should shall may might must get got gets getting what when where who whom which why how all any
some each every both few more most other another such own same don isn aren won
after again against because before between during while""".split())


def en_words(text):
    """Content words of an English item: the unit the en detector compares."""
    return {w for w in re.findall(r'[a-z]+', (text or '').lower())
            if w not in EN_STOP and len(w) > 2}


def shingles(text, n=2):
    t = CJK_PUNCT.sub('', text or '')
    return {t[i:i + n] for i in range(len(t) - n + 1)}


def jaccard(a, b):
    if not a or not b:
        return 0.0
    inter = len(a & b)
    return inter / (len(a) + len(b) - inter)


def load(lang='zh-tw'):
    rows = []
    for f in sorted(glob.glob(TOPICS)):
        j = json.load(open(f))
        for it in j['items']:
            rows.append({
                'file': os.path.basename(f),
                'slug': j['slug'],
                'id': it['id'],
                'date': it.get('dateAdded', '?'),
                'text': (it.get('i18n', {}).get(lang, {}) or {}).get('content', ''),
            })
    return rows


class UF:
    def __init__(self, n):
        self.p = list(range(n))

    def find(self, x):
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[rb] = ra


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--date')
    ap.add_argument('--min-size', type=int, default=2)
    ap.add_argument('--threshold', type=float, default=THRESHOLD)
    ap.add_argument('--json', action='store_true')
    ap.add_argument('--lang', default='zh-tw', choices=['zh-tw', 'en'])
    a = ap.parse_args()

    if a.lang == 'en' and a.threshold == THRESHOLD:
        a.threshold = EN_THRESHOLD          # zh default would over-report on en

    rows = load(a.lang)
    sh = [en_words(r['text']) if a.lang == 'en' else shingles(r['text']) for r in rows]
    n = len(rows)

    # inverted index keeps this O(candidate pairs), not O(n^2). For en the index
    # is on content words, so the cap drops genuinely common words rather than
    # the near-universal bigrams it drops for zh.
    df = collections.Counter()
    for s in sh:
        df.update(s)
    inv = collections.defaultdict(list)
    for i, s in enumerate(sh):
        for g in s:
            if a.lang == 'en' and df[g] > 400:
                continue
            inv[g].append(i)

    uf = UF(n)
    seen = set()
    for g, idxs in inv.items():
        if len(idxs) > 400:      # ultra-common bigram: no signal, skip
            continue
        for x in range(len(idxs)):
            for y in range(x + 1, len(idxs)):
                p = (idxs[x], idxs[y])
                if p in seen:
                    continue
                seen.add(p)
                if jaccard(sh[p[0]], sh[p[1]]) >= a.threshold:
                    uf.union(p[0], p[1])

    groups = collections.defaultdict(list)
    for i in range(n):
        groups[uf.find(i)].append(i)
    clusters = [v for v in groups.values() if len(v) >= max(2, a.min_size)]
    clusters.sort(key=len, reverse=True)

    if a.date:
        clusters = [c for c in clusters if any(rows[i]['date'] == a.date for i in c)]

    total = sum(len(c) for c in clusters)
    if a.json:
        print(json.dumps([[rows[i] for i in c] for c in clusters], ensure_ascii=False, indent=1))
        return
    print(f'corpus={n}  lang={a.lang}  threshold={a.threshold}  '
          f'clusters={len(clusters)}  items_in_clusters={total}')
    for c in clusters:
        by_slug = collections.Counter(rows[i]['slug'] for i in c)
        tag = 'SAME-TOPIC' if len(by_slug) == 1 else f'CROSS-{len(by_slug)}'
        print(f'\n--- cluster size={len(c)} [{tag}] {dict(by_slug)}')
        for i in c:
            print(f"  {rows[i]['id']:<12} {rows[i]['date']} {rows[i]['slug'][:22]:<22} {rows[i]['text'][:52]}")


if __name__ == '__main__':
    main()
