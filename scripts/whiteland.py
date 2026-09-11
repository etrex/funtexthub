#!/usr/bin/env python3
"""白地掃描（whiteland scan）— 以「讀者看得到的內容」為分子，不是 grep 原始 JSON。

用法:
    python3 scripts/whiteland.py 中秋 烤肉 洗烤肉網 土地公
    python3 scripts/whiteland.py --lang en pumpkin costume
    python3 scripts/whiteland.py --breakdown 長輩        # 顯示各欄位分布

為什麼要有這支（2026-09-07 發現，務必讀完再改）
------------------------------------------------------------------
在此之前，白地掃描一律用 `grep -o '詞' src/content/topics/*.json | wc -l`。
那個數字**不是**「有幾則內容寫過這個詞」，而是「這個詞在整個 JSON 檔裡出現幾次」，
因此把 `editorNote`（使用場景建議）、`tags`、`variations`、`en` 全部算進分子。

實測膨脹倍率（2026-09-07，17,048 則）：

    詞      grep 原始   zh content 則數   倍率
    衣櫃       161            76         2.1x
    老師       355           140         2.5x
    棉被       257            80         3.2x
    中秋       166            44         3.8x
    烤肉       114            27         4.2x
    連假       355            61         5.8x
    中元       141            15         9.4x
    長輩       510            47        10.9x

🔴 **倍率不是常數（2.1x–10.9x），所以跨詞比較也是錯的**，不只是絕對值偏高。
機制（逐欄位拆解，非猜測）：

    長輩 510 = zh.content 52 + editorNote 291 + variations 34 + tags 41 + sourceNote 92
    中元 141 = zh.content 15 + editorNote  22 + variations  3 + tags 52 + sourceNote 49

    （`raw` 欄與 `grep -o` 對得起來，±1 是 topic 層 title/description 的命中，
      可直接用來換算 research-log 的舊讀數。）

    ⚠️ 兩個容易混淆的單位：`則數` 是**有幾則命中**，breakdown 的 `content` 是
      **出現幾次**（一則寫兩次算兩次）。長輩 47 則／52 次即為此。

    → `editorNote` 是最大宗膨脹源（長輩佔 57%），因為它描述的是
      「**什麼時候用**這一則」，不是這一則寫了什麼。
    → `tags` 對節日詞是最大宗（中元的 tags 52 > content 15），因為
      標籤描述的是「這則**關於**什麼」，同樣不是它的文字。

⇒ 通則：**`editorNote` 與 `tags` 是後設資料，不是語料。** 分子只能取
  `i18n.<lang>.content`（`variations` 是同一則的改寫，會重複計入同一個意象，
  預設也不計；要看請加 `--variations`）。

🔴 這支修正**不對稱地**影響兩種結論：
  - 「這個詞是 0」→ **不受影響**。0 就是 0，多算欄位只會讓 0 變成非 0，
    不會讓非 0 變成 0。過去所有「白地」的正面發現都仍然成立。
  - 「這個主幹已飽和」→ **受影響很大**，而飽和判斷正是「禁用主幹」指令的依據。
    被此修正推翻的既有讀數見 research-log 2026-09-07。

🔴 第二個分子缺陷（2026-09-09 發現）— 比對的**方式**，不是欄位
------------------------------------------------------------------
9/07 修好了「分子取哪個欄位」，但沒有人查過「怎麼比對」。原本一律用
`term in text`（子字串），對中文沒問題（中文本來就沒有詞界），
**對拉丁字母的查詢詞則是災難**：

    ven   則數 5   raw 6953   倍率 1390.6x

    raw 的 6953 幾乎全部來自 `en` 欄位裡的 even / seven / given / oven /
    never…；而「則數 5」裡也有 2 則是誤判（cj-233 的 `seven`、
    sl-080 的 `event`）。真實讀數是 **3 則／3 檔**。

`ven` 不是假想例：它是 2026 年 Threads 上的現役迷因，正好是會被拿來當
指派 token 的那種詞。舊行為會把它報成 PARTIAL(5)，實際是 THIN(3)。

⇒ 修法：**查詢詞若全為 ASCII，改用「左詞界」比對**（詞前不得緊鄰
  `[A-Za-z0-9]`，詞尾不設限）；**含任何非 ASCII 字元者維持子字串**，
  因為中文沒有詞界，且這樣可保證所有既有中文查詢的輸出**逐字不變**（已實測）。
  含中英混寫的詞（如 `我再ven一次`）走子字串路徑，符合直覺。

  ⚠️ **左右都設詞界是錯的，已實測後否決**：那樣 `teacher` 會漏掉 `teachers`
  （83 → 80 則）、`costume` 漏掉 `costumes`（12 → 11 則）。白地掃描的錯誤
  成本是**不對稱**的——假陰性會讓人把已寫過的主幹當白地去派，假陽性只會
  讓人少派一個詞。所以只擋「查詢詞出現在別的字中間或字尾」這個主要
  失效模式（`seven`／`event`／`given`／`oven` 之於 `ven`），
  保留形態變化（複數、所有格、-ing）。殘留假陽性僅剩以查詢詞開頭的
  別字（`vent`／`venue`），量級遠小於原本的 1390x。

⚠️ 這一代與 9/07 那一代的差別值得記住：9/07 錯在**分子的來源**，
  這一代錯在**分子的判準**。修好前者不會順便修好後者，
  因為兩者在程式碼裡是不同的一行。

🔴 第三個缺陷（2026-09-11 發現）— 分子對了、判準對了，但**問錯了問題**
------------------------------------------------------------------
前兩代都在修「這個詞在語料裡出現幾次」。今天發現的是：那個數字回答不了
使用者真正要問的問題。白地掃描的用途是判斷「這個詞值不值得指派」，而
`THIN`（1–3 則）同時對應兩種完全相反的狀況：

    (甲) 真的沒人寫過 → 值得指派
    (乙) 幾個月前就報過、已經指派過、已經寫完了 → **不值得指派**

語料讀數**無法區分這兩者**，因為兩者在語料裡長得一模一樣（都是 1–3 則）。
實測（2026-09-11，把近三份報告當成「本週新見」報出的詞逐一回查）：

    詞         研究日誌首報    語料首次寫入    則數   近三報又報為新
    留友看      2026-04-21    2026-04-29     7      是
    真冰涼      2026-04-10    2026-04-29     1      是
    ven        2026-04-14    2026-05-11     5      是
    甘阿捏      2026-04-10    2026-05-17     4      是
    ㄅ級分      2026-05-11    2026-05-22     4      是
    陳皮糖      2026-05-19    2026-05-22     3      是
    從從容容     2026-09-10    2026-05-02     2      是
    與眾分      2026-08-24    2026-06-15     1      是

**8/8 都是乙**：全部由本日誌自己在 4–5 個月前首報、當時就指派、當時就寫完，
然後在 9/08、9/10 又被當成「本週新見」報一次。語料讀數（THIN）每一次都是
**正確的數字配上錯誤的標籤**。

⇒ 修法：多印一欄 **`首報`** ＝ 該詞在 `scripts/research-log.md` 首次出現所屬的
  報告日期。判讀規則：

    語料 WHITE ＋ 首報 —        → 🟢 真白地
    語料 THIN  ＋ 首報 —        → 🟢 白地（或剛落地的新指派）
    語料 THIN  ＋ 首報 數月前    → 🔴 **已結案，不是白地**
    語料 WHITE ＋ 首報 數月前    → ⚠️ 報過但沒寫成，查當時為何 SKIP

⚠️ 這一欄**不是**語料讀數，它是**流程讀數**。它回答的是「我以前報過嗎」，
  不是「讀者看過嗎」。兩者都要看。

🔴 **這一欄自己的分子也有限制，寫在這裡以免重蹈覆轍**：它取的是
  **在 research-log.md 任何一行的首次出現**，其中包含
  ⑴ 飽和度表格的讀數（`賞月 1`）、⑵ 節慶行事曆之類的背景資訊、
  ⑶ 禁用清單與「不指派」決議。**這些都不是推薦。**
  因此 `WHITE ＋ 首報數月前` **不能**逕自讀成「推薦過但沒執行」——
  實測（2026-09-11，以「出現在含『候選』字樣的行」為較嚴格的推薦定義，
  取 08-01 以後共 50 個候選詞）：**列為候選 ≥14 天而語料仍為 0 的有 0 個**，
  最舊的未執行候選僅 12 天（`紀念磁鐵`／`我再Ven一次`）。
  ⇒ **「推薦沒被執行」目前是陰性結論，不要據本欄反推。**
  本欄可靠的用途只有一個方向：**`n > 0` ＋ 首報數月前 ＝ 已結案**。

⚠️ 同時修好的上游原因：WebSearch 查詢**含年份**（「2026 流行語」）必然命中
  年度總整理型 listicle，那種文章每週回傳同一批詞、與搜尋時間無關。
  查詢改用時間詞（「這週」「本月」）而不用年份，當日即測得不同結果。

本腳本永遠 exit 0，report-only，不接任何閘門。
"""
import argparse
import glob
import json
import os
import re
import sys

TOPICS = "src/content/topics/*.json"


def load():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out = []
    for f in sorted(glob.glob(os.path.join(root, TOPICS))):
        out.append(json.load(open(f, encoding="utf-8")))
    return out


ASCII_ONLY = re.compile(r"^[\x00-\x7f]+$")


def _boundary(term):
    """ASCII 查詢詞用詞界；含非 ASCII 者回傳 None（走子字串路徑）。"""
    if not ASCII_ONLY.match(term):
        return None
    return re.compile(r"(?<![A-Za-z0-9])" + re.escape(term))


def hit(term, text, pat):
    return bool(pat.search(text)) if pat else (term in text)


def occ(term, text, pat):
    return len(pat.findall(text)) if pat else text.count(term)


def scan(data, term, lang, use_variations):
    """回傳 (則數, 檔數, 命中的檔名 set)。分子只取 content（可選加 variations）。"""
    n = 0
    files = set()
    pat = _boundary(term)
    for d in data:
        for it in d["items"]:
            block = it.get("i18n", {}).get(lang) or {}
            texts = [block.get("content") or ""]
            if use_variations:
                texts += list(block.get("variations") or [])
            if any(hit(term, t, pat) for t in texts):
                n += 1
                files.add(d["slug"])
    return n, len(files), files


def breakdown(data, term, lang):
    c = {"content": 0, "editorNote": 0, "variations": 0, "tags": 0,
         "sourceNote": 0, "other-lang": 0}
    other = "en" if lang != "en" else "zh-tw"
    pat = _boundary(term)
    for d in data:
        for it in d["items"]:
            b = it.get("i18n", {}).get(lang) or {}
            c["content"] += occ(term, b.get("content") or "", pat)
            c["editorNote"] += occ(term, b.get("editorNote") or "", pat)
            c["variations"] += sum(occ(term, v, pat) for v in (b.get("variations") or []))
            c["tags"] += sum(occ(term, x, pat) for x in (it.get("tags") or []))
            c["sourceNote"] += occ(term, it.get("sourceNote") or "", pat)
            c["sourceNote"] += occ(term, it.get("sourceUrl") or "", pat)
            c["other-lang"] += occ(term, json.dumps(
                it.get("i18n", {}).get(other) or {}, ensure_ascii=False), pat)
    return c


LOG_PATH = "scripts/research-log.md"
_HDR = re.compile(r"^## (\d{4}-\d{2}-\d{2}) Research Report")


def load_log_lines():
    """回傳 [(報告日期, 該行文字)]；讀不到就回傳空 list（本欄僅為 report-only）。"""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(root, LOG_PATH)
    try:
        raw = open(path, encoding="utf-8").read().split("\n")
    except OSError:
        return []
    out = []
    cur = "(pre-log)"
    for line in raw:
        m = _HDR.match(line)
        if m:
            cur = m.group(1)
        out.append((cur, line))
    return out


def first_report(term, log_lines):
    """該詞在 research-log.md 首次出現所屬的報告日期；沒出現過回傳 None。"""
    pat = _boundary(term)
    for date, line in log_lines:
        if hit(term, line, pat):
            return date
    return None


def verdict(n, nf, total_files):
    if n == 0:
        return "WHITE"
    if nf <= 2:
        return "THIN"
    if nf >= total_files * 0.4:
        return "SATURATED"
    return "PARTIAL"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("terms", nargs="+")
    ap.add_argument("--lang", default="zh-tw", choices=["zh-tw", "en"])
    ap.add_argument(
        "--variations",
        action="store_true",
        help="把 variations 也算進分子（預設不算：它是同一則的改寫）",
    )
    ap.add_argument("--breakdown", action="store_true", help="逐欄位拆解，用於解釋膨脹來源")
    ap.add_argument("--no-log", action="store_true",
                    help="不查 research-log.md 的首報日期（預設會查）")
    a = ap.parse_args()

    data = load()
    total_files = len(data)
    total_items = sum(len(d["items"]) for d in data)
    print(f"語料 {total_items} 則／{total_files} 檔　分子＝i18n.{a.lang}.content"
          + ("＋variations" if a.variations else ""))
    log_lines = [] if a.no_log else load_log_lines()
    head = f"{'詞':16s}{'則數':>7s}{'檔數':>7s}{'raw':>8s}{'倍率':>8s}  判定"
    print(head + ("" if a.no_log else f"{'':6s}首報（research-log）"))
    for t in a.terms:
        n, nf, fs = scan(data, t, a.lang, a.variations)
        b = breakdown(data, t, a.lang)
        raw = sum(b.values())
        ratio = raw / n if n else float("inf")
        rs = f"{ratio:.1f}x" if n else "—"
        v = verdict(n, nf, total_files)
        tail = ""
        if not a.no_log:
            fr = first_report(t, log_lines)
            tail = f"{'':4s}{fr or '—'}" + ("  🔴 已結案，不是白地"
                                            if fr and n else "")
        print(f"{t:16s}{n:>7d}{nf:>7d}{raw:>8d}{rs:>8s}  {v:11s}{tail}")
        if a.breakdown:
            print(f"{'':16s}  " + "  ".join(f"{k}={v}" for k, v in b.items()))
        if 0 < nf <= 4:
            print(f"{'':16s}  檔案: {', '.join(sorted(fs))}")
    print("\n（report-only，永遠 exit 0；WHITE 的 0 仍須通過防呆："
          "這個主題有沒有用別的名字被寫過？）")
    if not a.no_log:
        print("（`首報` 是流程讀數不是語料讀數：THIN ＋ 數月前首報 ＝ 已結案，"
              "不是白地。見 docstring 2026-09-11 節。）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
