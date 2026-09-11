#!/usr/bin/env python3
"""Schema / format / internal-consistency audit for all topic JSON files.

WHY THIS EXISTS
---------------
The existence-level checks (does the field exist? is it non-empty?) have read 0
for a long time. The 2026-09-07 lesson was that shipping defects come from
UPGRADING an existence check into a format / internal-consistency check:
  "which field have I only ever verified the existence of?"
That escalation found 3 real defect classes on 09-07 (tags self-duplicating,
trailing \n in content, sourceUrl holding a non-URL string).

This script freezes BOTH levels so the escalation is not re-derived by hand
each day. Report-only sections are marked; the gate only fails on real defects.

NEGATIVE RESULTS (do not re-litigate — these were checked and are clean/benign):
  * 2026-09-08: all 12 format/consistency checks below read 0 on 17,332 items.
    The 09-07 escalation heuristic is now itself saturated on these axes.
  * Tag typo detection via CJK edit distance is 100% ineffective — do not add it.
  * Tags containing punctuation are legitimate literals (console.log, "1.78元").
  * 977 items legitimately lack sourceUrl (pre-policy back catalogue).
    NEVER fabricate one to close the gap; it is reported, not gated.
  * 2026-09-11: four MORE escalations added below, all read 0 on 17,656 items
    (cross-language identical content, zero-latin en field, zero-CJK zh content,
    variations count parity, editorNote reuse corpus-wide). Two of these had
    ALREADY been hand-run on 09-07 and re-derived by hand today because they
    only ever lived in prose -> that is why they are frozen here now.
    The "upgrade an existence check into a format check" heuristic has now
    produced 0 for three consecutive days; it is saturated. Look at a different
    LAYER (semantics / frame / scene / traffic), not another field.
  * "en field CONTAINS CJK" is a 100% false positive (glossing is house style,
    confirmed 6x). Its sharp form -- "en field has ZERO latin letters" -- keeps
    the true positives and drops the FPs. General lesson: when a detector is too
    noisy, try its extreme form (contains -> consists entirely of / none at all)
    before abandoning it.
  * en near-dup clusters live in dedup_scan.py, not here. The 5 standing
    clusters were eyeballed 2026-09-08 and are benign (shared source idiom,
    genuinely distinct quotes). Never bulk-delete a whole union-find cluster.

Usage:  python3 scripts/audit_schema.py [--verbose]
Exit 0 = no gated defects.  Exit 1 = real defects found.
"""
import json, glob, os, re, sys, collections, unicodedata, datetime

VERBOSE = "--verbose" in sys.argv
ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "src", "content", "topics")
CATEGORIES = {"Humor", "Romance", "Motivation", "Social", "Lifestyle"}
LATIN = re.compile(r"[A-Za-z]")
CJK = re.compile(r"[\u4e00-\u9fff]")
TODAY = datetime.date.today().isoformat()

gated = collections.OrderedDict()   # name -> list of offenders (fails build)
report = collections.OrderedDict()  # name -> list (informational only)

def G(name): return gated.setdefault(name, [])
def R(name): return report.setdefault(name, [])

files = sorted(glob.glob(os.path.join(ROOT, "*.json")))
total = 0
tag_counts = collections.Counter()

for path in files:
    base = os.path.basename(path)[:-5]
    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)

    # --- topic level ---
    if doc.get("slug") != base:
        G("slug != filename").append((base, doc.get("slug")))
    if doc.get("category") not in CATEGORIES:
        G("category not in allowed list").append((base, doc.get("category")))
    prev_num = None
    prev_date = None
    for lang in ("zh-tw", "en"):
        o = doc.get("i18n", {}).get(lang, {}) or {}
        if not (o.get("title") or "").strip() or not (o.get("description") or "").strip():
            G("topic i18n title/description missing").append((base, lang))

    seen_ids = set()
    seen_content = collections.defaultdict(list)
    prefixes = set()

    for it in doc.get("items", []):
        total += 1
        iid = it.get("id", "")

        # --- id ---
        if iid in seen_ids:
            G("duplicate id within file").append((base, iid))
        seen_ids.add(iid)
        m = re.fullmatch(r"([a-z0-9]+(?:-[a-z0-9]+)*)-(\d{3,})", iid)
        if not m:
            G("bad id format").append((base, iid))
        else:
            prefixes.add(m.group(1))

        # --- dateAdded ---
        da = str(it.get("dateAdded", ""))
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", da):
            G("bad dateAdded format").append((base, iid, da))
        elif da > TODAY:
            G("dateAdded in the future").append((base, iid, da))

        # --- tags ---
        for t in it.get("tags", []):
            if not isinstance(t, str) or not t.strip():
                G("empty / non-string tag").append((base, iid, repr(t)))
                continue
            if t != t.strip():
                G("tag with leading/trailing whitespace").append((base, iid, repr(t)))
            tag_counts[t] += 1
        tl = [t for t in it.get("tags", []) if isinstance(t, str)]
        if len(tl) != len(set(tl)):
            G("tags array self-duplicating").append((base, iid, tl))

        # --- sourceUrl ---
        su = it.get("sourceUrl")
        if su is None or not str(su).strip():
            R("missing sourceUrl (back catalogue — DO NOT fabricate)").append((base, iid))
        elif not str(su).startswith(("http://", "https://")):
            G("sourceUrl is not a URL").append((base, iid, su))

        # --- per language body ---
        for lang in ("zh-tw", "en"):
            o = it.get("i18n", {}).get(lang, {}) or {}
            c = o.get("content") or ""
            n = o.get("editorNote") or ""
            if not c.strip():
                G("missing content").append((base, iid, lang))
            if not n.strip():
                G("missing editorNote").append((base, iid, lang))
            if c != c.strip():
                G("content has leading/trailing whitespace").append((base, iid, lang))
            if c.strip() and c.strip() == n.strip():
                G("editorNote identical to content").append((base, iid, lang))

            vs = o.get("variations")
            if vs is not None:
                if not isinstance(vs, list):
                    G("variations is not a list").append((base, iid, lang))
                else:
                    sv = [str(x).strip() for x in vs]
                    if any(not x for x in sv):
                        G("blank entry in variations").append((base, iid, lang))
                    if len(sv) != len(set(sv)) and sv:
                        G("variations self-duplicating").append((base, iid, lang))
                    if c.strip() and c.strip() in sv:
                        G("variation identical to content").append((base, iid, lang))

            if lang == "zh-tw" and c.strip():
                seen_content[c.strip()].append(iid)

        # --- cross-language consistency (2026-09-11 escalation; all read 0) ---
        zo = it.get("i18n", {}).get("zh-tw", {}) or {}
        eo = it.get("i18n", {}).get("en", {}) or {}
        zc, ec = (zo.get("content") or "").strip(), (eo.get("content") or "").strip()
        if zc and zc == ec:
            G("en content identical to zh content (untranslated)").append((base, iid))
        # Sharp form of the untranslated check. "en field CONTAINS CJK" is a known
        # 100% false positive (glossing is house style, confirmed 6x) — but "en field
        # has ZERO latin letters" keeps every true positive and drops the FPs, since a
        # gloss always carries English around the CJK term.
        for fld in ("content", "editorNote"):
            v = (eo.get(fld) or "").strip()
            if v and not LATIN.search(v):
                G("en field has zero latin letters (untranslated)").append((base, iid, fld, v[:40]))
        if zc and not CJK.search(zc):
            G("zh content has zero CJK chars (untranslated)").append((base, iid, zc[:40]))
        if len(zo.get("variations") or []) != len(eo.get("variations") or []):
            G("variations count differs between zh and en").append(
                (base, iid, len(zo.get("variations") or []), len(eo.get("variations") or [])))

        # report-only: append-only files should run forward in id/date order.
        # Known standing hit: fdq-069/070 sit after fdq-071..074. Cosmetic only —
        # the site does not sort items, but reordering an append-only file is noise.
        try:
            num = int(str(iid).rsplit("-", 1)[1])
        except (ValueError, IndexError):
            num = None
        if prev_num is not None and num is not None and num < prev_num:
            R("id/date runs backwards inside file (cosmetic, append-only)").append((base, iid))
        elif prev_date and da and da < prev_date:
            R("id/date runs backwards inside file (cosmetic, append-only)").append((base, iid, prev_date, da))
        prev_num, prev_date = num, da

    if len(prefixes) > 1:
        G("more than one id prefix in file").append((base, sorted(prefixes)))
    for c, ids in seen_content.items():
        if len(ids) > 1:
            G("exact duplicate zh content within file").append((base, ids, c[:50]))

# --- cross-file exact duplicates + tag normalization (corpus wide) ---
cross = collections.defaultdict(list)
for path in files:
    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)
    for it in doc.get("items", []):
        for lang in ("zh-tw", "en"):
            c = ((it.get("i18n", {}).get(lang, {}) or {}).get("content") or "").strip()
            if c:
                cross[(lang, c)].append((doc["slug"], it.get("id")))
for (lang, c), where in cross.items():
    if len(where) > 1:
        G("exact duplicate content across files").append((lang, c[:50], where))

# editorNote reuse across the corpus. 17,656/17,656 were distinct on 2026-09-11,
# so any hit is worth a look — but REPORT-ONLY: two unrelated items could plausibly
# share a short usage note, and a false gate would block the daily pipeline.
notes = collections.defaultdict(list)
for path in files:
    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)
    for it in doc.get("items", []):
        for lang in ("zh-tw", "en"):
            n = ((it.get("i18n", {}).get(lang, {}) or {}).get("editorNote") or "").strip()
            if n:
                notes[(lang, n)].append((doc["slug"], it.get("id")))
for (lang, n), where in notes.items():
    if len(where) > 1:
        R("editorNote reused across items (eyeball before treating as defect)").append(
            (lang, n[:40], where))

norm = collections.defaultdict(set)
for t in tag_counts:
    k = unicodedata.normalize("NFKC", t).casefold().replace(" ", "").replace("-", "").replace("_", "")
    norm[k].add(t)
for k, v in norm.items():
    if len(v) > 1:
        G("tag normalization collision (case/fullwidth/separator)").append(sorted(v))

# --- output ---
print(f"audit_schema: {len(files)} topics, {total} items, {len(tag_counts)} distinct tags")
print()
fails = 0
for name, offenders in gated.items():
    if offenders:
        fails += len(offenders)
        print(f"  DEFECT  {name}: {len(offenders)}")
        for o in offenders[:10]:
            print(f"            {o}")
if not fails:
    print("  all gated checks: 0")
print()
for name, offenders in report.items():
    print(f"  report-only  {name}: {len(offenders)}")
    if VERBOSE:
        for o in offenders[:20]:
            print(f"                 {o}")

print()
print(f"RESULT: {'FAIL' if fails else 'PASS'} ({fails} gated defects)")
sys.exit(1 if fails else 0)
