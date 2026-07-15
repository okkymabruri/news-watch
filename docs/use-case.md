# MBG Use Case: Collecting and Analyzing Indonesian News on Makan Bergizi Gratis

This guide walks the public workflow — from collection through aggregate
analysis — for the *Makan Bergizi Gratis* (MBG) policy research corpus
covering **2025-01-05 through 2026-07-14**, using the `newswatch` registry
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

Run the stable, search-capable registry subset against the MBG keywords for the
declared window. `--scrapers all` resolves every stable entry with
`supports_search=True`, not all 72 registered sources.

```bash
uv run newswatch \
  --method search \
  --keywords "makan bergizi gratis,program MBG,satuan pelayanan pemenuhan gizi,SPPG,badan gizi nasional" \
  --start_date "2025-01-05" \
  --daterange "2025-01-05/2026-07-14" \
  --scrapers all \
  --scraper-timeout 180 \
  --output_format jsonl \
  --output_path mbg-all.jsonl \
  --progress
```

What `--scrapers all` resolves to in this repo:

- 72 registry entries total.
- 66 stable entries support search and are resolved by `--scrapers all`.
- Banten News supports search but remains `investigating`, so the stable CLI
  resolver excludes it; its two retained 13–14 July records were collected in
  a separate bounded pass.
- 5 entries support latest collection only and are skipped by search runs:
  `aljazeera`, `balipost`, `dandapala`, `hukumonline`, and `independen`.

Verify the search-capable registry count yourself at runtime:

```bash
uv run python -c "import sys; sys.path.insert(0,'src'); \
  from newswatch.registry import get_search_scrapers; \
  print(len(get_search_scrapers()))"
# -> 66
```

## Corpus Validation

Validate each collection before analysis; retrieval totals are evidence about
that run, not fixed properties of the news ecosystem.

1. **Check the schema.** Require `title`, `publish_date`, `content`, `link`, and
   `source` on every record. Reject malformed rows rather than filling missing
   evidence with inferred values.
2. **Enforce the study window.** Parse publication timestamps and retain only
   records from 2025-01-05 through 2026-07-14 inclusive of both full calendar days (i.e. 2025-01-05 00:00:00 through 2026-07-14 23:59:59.999999). Report
   unparseable and out-of-window rows separately.
3. **Confirm relevance.** Keep a record only when its title or content contains
   at least one retrieval term: `MBG`, `Makan Bergizi Gratis`, `Program MBG`,
   `satuan pelayanan pemenuhan gizi`, `SPPG`, `Badan Gizi Nasional`, or `BGN`.
   Matching is case-insensitive.
4. **Remove duplicates in order.** Deduplicate exact article links first, then
   lowercase and collapse whitespace in titles before removing repeated titles.
   Preserve the number removed at each step so the final corpus is auditable.
5. **Publish aggregates only.** Reconcile retained records by source and calendar
   month, but keep article text, titles, URLs, and document-level outputs in the
   private research workspace.

Inspect the actual numbers in each run; do not treat one retrieval as a fixed
benchmark. The run documented here yielded 9,973 well-formed records
before cleaning, then 7,621 after relevance filtering, 3,995 after URL
deduplication, and 3,976 after normalized-title deduplication. It covered 34
sources and all 19 calendar months in the window. These are one run's retrieval
counts, not estimates of article production.

## Aggregate Analysis

The run documented above — **3,976 cleaned documents**, **34 sources**,
and all **19 calendar months** in the window — supports the aggregate topic
and entity figures below. Topic annotations are **provisional English summaries**
derived from auto-generated Indonesian term statistics; named entities retain
their source-language proper names. Treat both as working labels pending manual
review before citing them as facts.

### Topic landscape and prevalence

The cleaned corpus resolves to **14 substantive topics plus an outlier class**.
The substantive topics cover operations, beneficiaries, regional rollouts,
incidents, audits, and parliamentary oversight; the outlier class captures
documents that do not cluster cleanly with any dominant theme.

![Two-dimensional UMAP scatter of the 3,976 cleaned documents colored by topic; five large substantive topics are directly labelled and unassigned outliers are shown in grey](assets/mbg/umap_scatter.png)

A two-dimensional UMAP projection of the cleaned documents, colored by
topic. Each point is one document. The five largest substantive topics are
labelled directly, while grey points show documents left unassigned by the
clustering model. Separation and overlap are diagnostic patterns, not proof
that the generated labels are definitive categories.

![Per-topic document counts ranked largest to smallest; the top three topics together account for 2,469 of 3,976 cleaned documents (62.1 percent)](assets/mbg/topic_size_bar.png)

Topic-size distribution ordered largest to smallest, including the outlier
class. The three largest topics account for **2,469 of 3,976 cleaned documents
(62.1%)**; the remainder is spread across the other 11 substantive topics and
the outlier class, confirming that program coverage is not a single narrative.

![Topic prevalence over the 19 calendar months from January 2025 through July 2026, with the largest topics tracked as separate lines](assets/mbg/topic_trendline.png)

Per-topic volume over the 19 calendar months in the window. The three largest
topics rise sharply in June 2026, when they total 845 documents — about 4.3
times their previous combined monthly peak. The pattern describes this
retrieved corpus and should not be extrapolated beyond 2026-07-14.

### Named entities and SPPG kitchens

Provisional entity extraction surfaces the most-mentioned people, event
locations, and SPPG/Dapur kitchen references in the corpus. The figures
below are aggregate counts; surface-form resolution is provisional.

![Top-mentioned people across the 3,976 cleaned documents; provisional extraction yields 23,487 mentions resolved to 3,423 unique surface forms](assets/mbg/person_top_bar.png)

Top-mentioned people across the corpus. Provisional extraction yields
**23,487 mentions resolved to 3,423 unique surface forms**. Ranks describe
prominence in this retrieved corpus, not policy importance. Audited aliases
reduce obvious name fragments, but shared or incomplete names can still split
or merge identities.

![Top event locations; counts exclude publisher datelines and general geographic framing, with 746 mentions resolving to 313 unique places](assets/mbg/place_top_bar.png)

Top event locations: **746 mentions resolving to 313 unique places**.
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
