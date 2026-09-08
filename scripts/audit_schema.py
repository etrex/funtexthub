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
