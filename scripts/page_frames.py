#!/usr/bin/env python3
"""逐檔「主導框」掃描——專門看 rare_ngram 家族看不見的那一塊。

為什麼需要另一支腳本（9/08 發現的結構性盲點）
------------------------------------------------
`metrics.py` 的 `rare_ngram_hits()` 只保留 **corpus doc-frequency <= RARE_DF_MAX
(=30)** 的 n-gram，而 `max_rare_ngram` / `frame_new_grams` / `build_exclusion`
三個偵測器全部建立在它之上。於是：

    一個框在 df <= 30 時被抓；跨過 30 之後就從所有偵測器裡永久消失。

**罕見度過濾器的靈敏度是反向的：框越成功，儀器越看不見它。**
所以「指標長期為 0」不等於「沒有主導框」，也可能是「框已經大到看不見」。

9/08 實測（17,164 則）：逐檔最高 4-gram 佔比排名前 12 名裡，**11 個的
corpus_df > 30**；全 42 檔裡有 **34 檔**的最高 gram 落在盲區。最大者是
`adulting-quotes` 的「初級大人」**160/461 = 34.7%**（corpus_df=168），
比 research-log 長期記載的「最大 holiday-jokes 43/443」大 **3.8 倍**——
那個舊讀數不是量錯，是**量不到**。

⚠️ 這支腳本本身不判斷缺陷
--------------------------
高佔比不必然是缺陷：`adulting-quotes` 的「初級大人／高級大人」是 4–7 月的
**正當體例存貨**（4 月 22 → 7 月 69 → 8 月 1 → 9 月 0，已停止成長）。
判斷要看**流量不是存量**：用 `--since` 看近期切片，存量大但近期為 0 的是
歷史存貨（不處置），近期仍在爬的才是活的漏。

report-only，永遠 exit 0，不接任何閘門。
"""
import argparse, collections, glob, json, os, re

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
TOPICS = 'src/content/topics/*.json'
CJK = re.compile(r'[^一-鿿]')
RARE_DF_MAX = 30   # 與 metrics.py 同值，僅用於標示盲區


def grams(s, n):
    s = CJK.sub('', s)
    return {s[i:i + n] for i in range(len(s) - n + 1)}


def main():
    a = argparse.ArgumentParser()
    a.add_argument('--lang', default='zh-tw', choices=['zh-tw', 'en'])
    a.add_argument('-n', type=int, default=4, help='n-gram 寬度（預設與 metrics.NGRAM_N 同）')
    a.add_argument('--since', default=None, help='只算 dateAdded >= 此日期的則（看流量而非存量）')
    a.add_argument('--top', type=int, default=15)
    a.add_argument('--per-file-top', type=int, default=1, help='每檔列出前幾個 gram')
    ns = a.parse_args()
    if ns.lang != 'zh-tw':
        print('（本掃描目前只對 CJK 有意義；英文側需改斷詞，見 9/05「不可繼承語言調校常數」）')
        return 0

    per = collections.defaultdict(list)
    for f in sorted(glob.glob(os.path.join(ROOT, TOPICS))):
        d = json.load(open(f, encoding='utf-8'))
        for it in d['items']:
            if ns.since and it.get('dateAdded', '') < ns.since:
                continue
            per[d['slug']].append((it['i18n'].get(ns.lang) or {}).get('content') or '')

    corpus = collections.Counter()
    total = 0
    for cs in per.values():
        for c in cs:
            total += 1
            for g in grams(c, ns.n):
                corpus[g] += 1
    if not total:
        print('（切片內無資料）')
        return 0

    rows = []
    for slug, cs in per.items():
        df = collections.Counter()
        for c in cs:
            for g in grams(c, ns.n):
                df[g] += 1
        for g, k in df.most_common(ns.per_file_top):
            rows.append((k / len(cs), slug, g, k, len(cs), corpus[g]))
    rows.sort(reverse=True)

    scope = f'（切片 dateAdded >= {ns.since}）' if ns.since else '（全語料存量）'
    print(f'{total} 則／{len(per)} 檔　{ns.n}-gram　lang={ns.lang} {scope}')
    print(f"{'檔案':26s}{'gram':>8s}  {'佔該檔':>16s}  corpus_df  儀器")
    for pct, slug, g, k, tot, cdf in rows[:ns.top]:
        blind = 'BLIND' if cdf > RARE_DF_MAX else 'visible'
        print(f'  {slug:24s} {g}  {k:4d}/{tot:<4d} = {pct*100:5.1f}%  {cdf:6d}   {blind}')
    nblind = sum(1 for r in rows if r[5] > RARE_DF_MAX)
    print(f'\n盲區（corpus_df > {RARE_DF_MAX}，rare_ngram 家族看不見）: {nblind}/{len(rows)}')
    print('⚠️ 高佔比 ≠ 缺陷。存量大而近期為 0 者為歷史體例；請加 --since 看流量再判斷。')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
