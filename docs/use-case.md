# MBG Use Case: Collecting and Analyzing Indonesian News on Makan Bergizi Gratis

This guide walks the public workflow — from collection through aggregate
analysis — for the *Makan Bergizi Gratis* (MBG) policy research corpus
covering **2025-01-05 through 2026-07-12**, using the `newswatch` registry
exactly as it is currently configured. It is the companion to
`practical-guide.md`; it does not duplicate installation, configuration, or
troubleshooting content.

## Background: Announcement vs. Operations

- **5 January 2025** — The Badan Gizi Nasional (BGN) announced the launch of
  the MBG program. Use this date as the *earliest possible news hook*.
  Announcement coverage on and around 5 Jan 2025 is largely about the policy
  itself, governance, and rollout intent.
- **6 January 2025** — Operations began. Coverage from this date forward
  includes implementation, beneficiaries, kitchens (SPPG), regional rollouts,
  incidents, audits, and parliamentary oversight.

Cite the policy with BGN's primary announcement:

- <https://www.bgn.go.id/news/artikel/bgn-akan-memulai-program-mbg-secara-bertahap>

When narrating the program, distinguish the announcement (5 Jan) from the
first operational day (6 Jan); the corpus window starts on 5 Jan to retain
announcement framing while the bulk of records describes the operational
period.

## Collection Command

Run the search-capable subset of the registry against the MBG keyword for the
declared window. `--scrapers all` means every registry entry that declares
`supports_search=True`, not all 72 registered sources.

```bash
uv run newswatch \
  --method search \
  --keywords "makan bergizi gratis,program MBG,satuan pelayanan pemenuhan gizi,SPPG,badan gizi nasional" \
  --start_date "2025-01-05" \
  --time-range "2025-01-05T00:00:00/2026-07-12T23:59:59" \
  --scrapers all \
  --scraper-timeout 180 \
  --output_format jsonl \
  --output_path mbg-all.jsonl \
  --progress
```

What `--scrapers all` resolves to in this repo:

- 72 registry entries total.
- 67 declare `supports_search=True` and are resolved by `--scrapers all`.
- 5 declare `supports_latest=True` only and are skipped by search runs:
  `aljazeera`, `balipost`, `dandapala`, `hukumonline`, and `independen`. They are
  inapplicable to this use case because the window is bounded by date, not recency.

Verify the search-capable registry count yourself at runtime:

```bash
uv run python -c "import sys; sys.path.insert(0,'src'); \
  from newswatch.registry import SCRAPERS; \
  print(sum(entry.supports_search for entry in SCRAPERS.values()))"
# -> 67
```

## Quality Gates

Run these before declaring the corpus usable. They live as a small pandas
script and are intentionally dependency-free apart from pandas (already in
the root project). Run from the repo root:

```python
# scripts-style snippet — paste into a Python session or .py file
import json
from pathlib import Path
import re
from collections import Counter
import pandas as pd

RAW = Path("mbg-all.jsonl")
rows = [json.loads(l) for l in RAW.read_text().splitlines() if l.strip()]
df  = pd.DataFrame(rows)

# 1. Schema audit — every row has the required keys
required = {"title", "publish_date", "content", "link", "source"}
assert required.issubset(df.columns), df.columns.tolist()

# 2. Window enforcement — drop anything outside 2025-01-05 .. 2026-07-12
df["publish_date"] = pd.to_datetime(df["publish_date"], errors="coerce")
df = df[df["publish_date"].between("2025-01-05", "2026-07-12 23:59:59")]
# 3. Relevance filter — title or content mentions any of the retrieved
# keywords (matches what the collection command searched for)
KEYWORDS = ["MBG", "Makan Bergizi Gratis", "Program MBG",
            "satuan pelayanan pemenuhan gizi", "SPPG",
            "Badan Gizi Nasional", "BGN"]
pattern = "|".join(re.escape(k) for k in KEYWORDS)
kw = df["title"].fillna("") + "\n" + df["content"].fillna("")
mask = kw.str.contains(pattern, case=False, regex=True)
df = df[mask]

# 4. URL dedup
df = df.drop_duplicates(subset=["link"])

# 5. Normalized-title dedup (collapse re-posts)
df["_title_norm"] = (
    df["title"].str.lower()
      .str.replace(r"\s+", " ", regex=True)
      .str.strip()
)
df = df.drop_duplicates(subset=["_title_norm"])

# 6. Coverage report — only ever surface aggregates, never rows
print("sources          :", df["source"].nunique())
print("months           :", df["publish_date"].dt.to_period("M").nunique())
top_sources = df["source"].value_counts().head(10)
top_months  = df["publish_date"].dt.to_period("M").value_counts().sort_index()
top_kw     = Counter(
    w.lower()
    for text in df["title"].fillna("") + " " + df["content"].fillna("")
    for w in text.split()
    if w.isalpha() and len(w) > 4
).most_common(20)
```

Inspect the actual numbers in each run; do not treat one retrieval as a fixed
benchmark. The run documented here yielded 9,967 well-formed records
before cleaning, then 7,610 after relevance filtering, 3,989 after URL
deduplication, and 3,970 after normalized-title deduplication. It covered 34
sources and all 19 calendar months in the window. These are one run's retrieval
counts, not estimates of article production.

## Aggregate Analysis

The run documented above — **3,970 cleaned documents**, **34 sources**,
and all **19 calendar months** in the window — supports the aggregate topic
and entity figures below. Topic labels and named entities are **provisional**:
they are auto-generated from term statistics and surface-form resolution,
and should be treated as working labels pending manual review before being
cited as facts.

### Topic landscape and prevalence

The cleaned corpus resolves to **14 substantive topics plus an outlier class**.
The substantive topics cover operations, beneficiaries, regional rollouts,
incidents, audits, and parliamentary oversight; the outlier class captures
documents that do not cluster cleanly with any dominant theme.

![Two-dimensional UMAP scatter of the 3,970 cleaned documents colored by topic; five large substantive topics are directly labelled and unassigned outliers are shown in grey](assets/mbg/umap_scatter.png)

A two-dimensional UMAP projection of the cleaned documents, colored by
topic. Each point is one document. The five largest substantive topics are
labelled directly, while grey points show documents left unassigned by the
clustering model. Separation and overlap are diagnostic patterns, not proof
that the generated labels are definitive categories.

![Per-topic document counts ranked largest to smallest; the top three topics together account for 2,229 of 3,970 cleaned documents (56.1 percent)](assets/mbg/topic_size_bar.png)

Topic-size distribution ordered largest to smallest, including the outlier
class. The three largest topics account for **2,229 of 3,970 cleaned documents
(56.1%)**; the remainder is spread across the other 11 substantive topics and
the outlier class, confirming that program coverage is not a single narrative.

![Topic prevalence over the 19 calendar months from January 2025 through July 2026, with the largest topics tracked as separate lines](assets/mbg/topic_trendline.png)

Per-topic volume over the 19 calendar months in the window. The three largest
topics rise sharply in June 2026, when they total 684 documents — about 3.6
times their previous combined monthly peak. The pattern describes this
retrieved corpus and should not be extrapolated beyond 2026-07-12.

### Named entities and SPPG kitchens

Provisional entity extraction surfaces the most-mentioned people, event
locations, and SPPG/Dapur kitchen references in the corpus. The figures
below are aggregate counts; surface-form resolution is provisional.

![Top-mentioned people across the 3,970 cleaned documents; provisional extraction yields 23,465 mentions resolved to 3,421 unique surface forms](assets/mbg/person_top_bar.png)

Top-mentioned people across the corpus. Provisional extraction yields
**23,465 mentions resolved to 3,421 unique surface forms**. Ranks describe
prominence in this retrieved corpus, not policy importance. Audited aliases
reduce obvious name fragments, but shared or incomplete names can still split
or merge identities.

![Top event locations; counts exclude publisher datelines and general geographic framing, with 745 mentions resolving to 312 unique places](assets/mbg/place_top_bar.png)

Top event locations: **745 mentions resolving to 312 unique places**.
These counts **exclude publisher datelines and general geographic
framing** — only locations anchored to a described event (visit, launch,
incident, audit) are counted. As a result, this chart under-represents
places that appear only as byline cities or background geography.

![Top SPPG/Dapur (satuan pelayanan pemenuhan gizi) kitchen references; 769 mentions resolve to 461 unique kitchen surfaces](assets/mbg/sppg_top_bar.png)

Top SPPG/Dapur (*satuan pelayanan pemenuhan gizi*) kitchen references:
**769 mentions resolving to 461 unique kitchen surfaces**. Unit numbers are
preserved where available, while strict normalization excludes regional
collectives and malformed identifiers. These automated identifiers remain
provisional until reconciled against operational records.

## Collection Limitations

Be explicit about what this corpus can and cannot support.

- **Retrieval coverage.** The registry contains 67 search-capable sources;
  34 sources contributed documents retained after cleaning. Five latest-only
  sources (`aljazeera`, `balipost`, `dandapala`, `hukumonline`, and
  `independen`) cannot participate in keyword search. Sources outside the
  registry are not searched.
- **Keyword recall.** Retrieval uses five related queries: `makan bergizi
  gratis`, `program MBG`, `satuan pelayanan pemenuhan gizi`, `SPPG`, and
  `badan gizi nasional`. Articles that discuss implementation without any
  of those terms can still be missed.
- **Completeness.** A finished corpus is bounded by what each scraper's
  search endpoint exposes. Some sources cap depth, return only top-N, or
  paginate inconsistently. Re-running with a tighter window or
  source-by-source will not necessarily close those gaps.
- **Copyright.** Each row is a *news article record*: title, link,
  publish date, author, and a content excerpt as returned by the source's
  own feed/page. The corpus is suitable for aggregate analysis, citation,
  and downstream modeling within fair-use research bounds; it is not a
  redistribution of full article text. Honor each publisher's terms.
