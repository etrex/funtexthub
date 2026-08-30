# 待人工套用：`funtexthub-daily-update/SKILL.md` 修補提案

**狀態**：未套用。orchestrator（本任務）**沒有修改自己任務定義的權限**，
故只能把改法寫成可直接複製的提案。研究報告 8/29、8/30 連續兩日列為 HIGHEST，
兩日皆零落地，原因已查明為**權責缺口**（`~/.claude/scheduled-tasks/*/SKILL.md`
不在四支 funtexthub 排程任務任何一支的權責內），不是優先級問題。

目標檔案：`~/.claude/scheduled-tasks/funtexthub-daily-update/SKILL.md`

---

## 1. 修掉兩個久存缺陷

- 第 30 行寫死 `Today's date is 2026-04-18` — **已錯 134 天**，靠子代理讀到後面
  括號裡的「use `date +%Y-%m-%d`」才沒出事。改成只留指令，不要留死日期。
- Quality rules 寫「3–5 new items per topic per day」，實際連日**恰為 4 則**。
  真正的則數規則在 `scripts/daily-brief.md`。把 SKILL.md 這行改成
  「則數以 `scripts/daily-brief.md` 為準」。

## 2. 把耐久層與運作層轉正（最關鍵的一條）

現況是顛倒的：`SKILL.md` 跨日不變但**不含任何真規則**；frame／scene 指派、
排除清單、句數範圍、跨語言對齊、`check_new_items.py` 驗收全部只存在於
`scripts/daily-brief.md`，而該檔**由每天那一次執行自己重寫**。
8/24 死在第 3.5 分鐘、8/28 死在第 7 分鐘——**兩次都死在簡報寫出來的前後**。

在 Steps 第 1 步之前插入：

```
### 0. 確認今日簡報存在
讀 `scripts/daily-brief.md` 與 `scripts/daily-assignment.json`。
若其中的日期不是今天：先依 `scripts/research-log.md` 末筆重建兩者
（frame 整批輪替、scene 全換新語域詞、排除清單先 `python3 scripts/metrics.py --exclude`
重建），再開工。簡報是**被讀的輸入**，不是本次執行的副產品。
```

## 3. 強制 backoff 重試

在 Steps 中加入：任何 `API Error` / 529 / `ENOTFOUND` / 連線類錯誤，
**至少重試 3 次，間隔 60 / 300 / 900 秒，每次重試前先 `git pull`**
（本 repo 有併發的維護任務會 commit）。

## 4. 可續跑

每完成一檔即記錄進度；啟動時先讀「當日已完成檔清單」，**只補缺口**，
不要整批重跑。

## 5. 收尾斷言，不得靜默結束

deploy 前必須：

```bash
python3 scripts/check_batch.py --date $(date +%Y-%m-%d)   # 必須 exit 0
```

並斷言**當日 `dateAdded` 的檔數 ＝ 42**。不足即重跑缺口檔，
**不得靜默結束、不得在缺檔狀態下 deploy**。
