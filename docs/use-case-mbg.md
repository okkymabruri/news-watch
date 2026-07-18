# MBG Use Case: Collecting and Analyzing Indonesian News on Makan Bergizi Gratis

This guide walks the public workflow — from collection through aggregate
analysis — for the *Makan Bergizi Gratis* (MBG) policy research corpus
covering **2025-01-05 through 2026-07-17**, using the `newswatch` registry
exactly as it is currently configured. It is the companion to
`practical-guide.md`; it does not duplicate installation, configuration, or
troubleshooting content.

## Background: What Is MBG?

*Makan Bergizi Gratis* (MBG) is Indonesia's national free nutritious-meals
program, administered by the Badan Gizi Nasional (BGN). It provides meals
designed against daily nutritional adequacy standards for school students,
pregnant women, breastfeeding mothers, and young children. Delivery is
organized through *Satuan Pelayanan Pemenuhan Gizi* (SPPG), the local service
units that prepare and distribute meals.

BGN describes MBG as both a nutrition intervention and a platform for nutrition
education. Its operating model also links SPPG procurement with local farmers,
fishers, cooperatives, and small businesses. This scale makes MBG a useful news
research case: reporting spans beneficiary access, kitchen expansion, food
safety, procurement, public finance, regional implementation, oversight, and
political accountability.

The corpus starts on **5 January 2025**, when BGN formally introduced the 2025
program, and includes implementation from **6 January 2025** onward. Official
program context and operating details are available from:

- [BGN's program launch statement](https://www.bgn.go.id/news/artikel/bgn-akan-memulai-program-mbg-secara-bertahap)
- [BGN's MBG frequently asked questions](https://www.bgn.go.id/faq)
- [BGN's SPPG quality-oversight statement](https://www.bgn.go.id/news/siaran-pers/bgn-perkuat-pengawasan-sppg-untuk-menjaga-kualitas-penyelenggaraan-program-mbg)

## Collection Command

Run the stable, search-capable registry subset against the MBG keywords for the
declared window. `--scrapers all` resolves every stable entry with
`supports_search=True`, not all 75 registered sources.

```bash
uv run newswatch \
  --method search \
  --keywords "mbg,makan bergizi gratis,program MBG,satuan pelayanan pemenuhan gizi,SPPG,badan gizi nasional" \
  --start_date "2025-01-05" \
  --daterange "2025-01-05/2026-07-17" \
  --scrapers all \
  --scraper-timeout 180 \
  --output_format jsonl \
  --output_path mbg-all.jsonl \
  --progress
```

What `--scrapers all` resolves to in this repo:

- 75 registry entries total.
- 68 stable entries support search and are resolved by `--scrapers all`.
- Banten News supports search but remains `investigating`, so the stable CLI
  resolver excludes it; its two retained 13–14 July records were collected in
  a separate bounded pass.
- 4 entries are stable and support latest collection only, so they are skipped
  by search runs: `aljazeera`, `balipost`, `hukumonline`, and `independen`.
- `investor` and `bantennews` are registered with both search and latest,
  but their `investigating` status excludes them from the stable CLI resolver.
- `dandapala` is registered, supports latest collection only, and is also in
  `investigating` status; it is not yet promoted to stable.


## Corpus Validation

Validate each collection before analysis; retrieval totals are evidence about
that run, not fixed properties of the news ecosystem.

1. **Check the schema.** Require `title`, `publish_date`, `content`, `link`, and
   `source` on every record. Reject malformed rows rather than filling missing
   evidence with inferred values.
2. **Enforce the study window.** Parse publication timestamps and retain only
2025-01-05 through 2026-07-17 inclusive of both full calendar days (i.e. 2025-01-05 00:00:00 through 2026-07-17 23:59:59).
3. **Confirm relevance.** Keep a record only when its title contains standalone
   `MBG` or an explicit program term: `Makan Bergizi Gratis`, `Program MBG`,
   `satuan pelayanan pemenuhan gizi`, `SPPG`, `Badan Gizi Nasional`, or `BGN`.
   Matching is case-insensitive, and acronym boundaries reject collisions such
   as `PVMBG`. Title anchoring excludes tangential articles that mention an MBG
   term only in the body.
4. **Remove duplicates in order.** Deduplicate exact article links first, then
   lowercase and collapse whitespace in titles before removing repeated titles.
   Preserve the number removed at each step so the final corpus is auditable.
5. **Publish aggregates only.** Reconcile retained records by source and calendar
   month, but keep article text, titles, URLs, and document-level outputs in the
   private research workspace.

Inspect the actual numbers in each run; do not treat one retrieval as a fixed
benchmark. The run documented here yielded 24,757 well-formed records before
cleaning, then 17,875 after relevance filtering, 8,364 after URL deduplication,
and 8,331 after normalized-title deduplication. It covered 48 contributing
sources and all 19 calendar months in the window. These are one run's
retrieval counts, not estimates of article production.

## Aggregate Analysis

The run documented above — **8,331 cleaned documents**, **48 contributing
sources**, and all **19 calendar months** in the window — supports the
aggregate topic and entity figures below. Topic annotations are **provisional
English summaries** derived from auto-generated Indonesian term statistics and
a manual review of private topic assignments; named entities retain their
source-language proper names. Treat both as working labels pending further
validation before citing them as facts.

### Topic landscape and prevalence

The cleaned corpus resolves to **14 substantive topics plus an outlier class**.
The substantive topics span SPPG operations and budgeting, corruption
investigations, food poisoning incidents, BGN leadership and appointments,
public demonstrations, food and livestock supply, viral incidents and
governance disputes, delivery vehicles and procurement, tax and fiscal
implications, food commodity price shifts, SPPG staffing and PPPK appointments,
suspected fictitious SPPG locations, TB patient support, and MBG insurance
proposals; the outlier class captures documents that do not cluster cleanly
with any dominant theme.
![Two-dimensional UMAP scatter of the 8,331 cleaned documents colored by topic; all 14 substantive topics are labeled directly over their cluster regions and unassigned outliers are shown in grey](assets/mbg/umap_scatter.png)

A two-dimensional UMAP projection of the cleaned documents, colored by
topic. Each point is one document. All 14 substantive topics are labeled
directly over their cluster regions within the scatter, while grey points
show documents left unassigned by the clustering model. Separation and
overlap are diagnostic patterns, not proof that the generated labels are
definitive categories.

**Visualization projection (figure only).** The scatter uses a dedicated
UMAP projection tuned for readability (`random_state=42`,
`n_neighbors=30`, `min_dist=0.3`, `metric=cosine`). It is distinct from
the analysis UMAP embedded inside the BERTopic pipeline, which produces
the topic assignments themselves; this second projection only re-lays
the documents out in two dimensions so clusters spread out and the
topic clouds stay legible. Topic assignments and cluster identities
are unchanged.
![Per-topic document counts ranked largest to smallest; the top three topics together account for 4,280 of 8,331 cleaned documents (51.4 percent)](assets/mbg/topic_size_bar.png)


Topic-size distribution ordered largest to smallest, including the outlier
class. The three largest topics account for **4,280 of 8,331 cleaned documents
(51.4%)**; the remainder is spread across the other 11 substantive topics and
the outlier class, confirming that program coverage is not a single narrative.

![Per-topic document volume across the 19 calendar months from January 2025 through July 2026, with the six largest topics each rendered in a distinct colorblind-safe color and a distinct line style, endpoint labels printed directly at the right margin, and four callout annotations marking contemporaneous coverage families for October 2025 (SPPG operations and budgeting), February 2026 (SPPG operations and budgeting around Ramadan), June 2026 (SPPG operations and budgeting expansion), and June 2026 T1 (corruption investigations)](assets/mbg/topic_trendline.png)

Per-topic volume over the 19 calendar months in the window for the **six
largest topics**: T0 SPPG operations and budgeting, T1 corruption
investigations, T2 food poisoning incidents, T3 BGN leadership and
appointments, T4 public demonstrations, and T5 food and livestock supply.
The figure renders each topic in a **distinct colorblind-safe color and line
style** and prints the topic label directly at the right-hand endpoint of every
line, so each series stays legible without relying on color alone.

Four callouts report exact monthly counts and mark contemporaneous coverage
families rather than causal triggers:

- **October 2025 — T0, 229 documents:** SPPG operations and budgeting coverage.
- **February 2026 — T0, 340 documents:** SPPG operations and budgeting around Ramadan.
- **June 2026 — T0, 566 documents:** SPPG operations and budgeting expansion.
- **June 2026 — T1, 372 documents:** corruption investigations peak. T1
  coverage grows steadily across the window, with this month the calendar peak.
In **June 2026** the three largest topics combined reach **951 documents**
— about **2.5428 times** their previous combined monthly peak of **374**.
This run reports aggregate volume only; annotations describe contemporaneous
news coverage families that happen to align with each spike and are not
claims that those events caused the observed volume. The pattern describes
this retrieved corpus and should not be extrapolated beyond 2026-07-17.

Independent public reporting documents the same contemporaneous coverage
families without quoting private records:

- [Bandung Barat mass-poisoning response, ANTARA (September 2025)](https://www.antaranews.com/berita/5129056/pemkab-bandung-barat-tetapkan-klb-usai-ratusan-siswa-keracunan-mbg)
- [Ramadan dry-food adaptation statement, ANTARA](https://en.antaranews.com/news/405814/free-meals-nutrition-maintained-despite-dry-food-shift-minister)
- [BGN school-holiday audit of MBG kitchens, ANTARA](https://en.antaranews.com/news/419313/bgn-to-fully-audit-free-meal-kitchens-during-school-holidays)
- [SPPG safety certification push after poisoning cases, Kompas](https://money.kompas.com/read/2025/10/03/100000126/usai-kasus-keracunan-bgn-ngebut-sertifikasi-sppg-agar-pangan-aman-)


### Document-similarity network

The method builds an undirected graph over the canonical **8,331 cleaned-document**
corpus using the cleaned document embeddings. Each node is one document. An
edge connects two documents when their cosine similarity is at least **0.90**
among each document's **k=5** nearest neighbors.

The full graph contains **1,699 active nodes and 1,708 edges**, distributed
across **499 active connected components**, with **6,632 isolates**. The
bounded figure displays the **20 largest components** within a **500-node cap**,
rendering **500 linked documents**; smaller components are shown in grey and
do not carry group annotations.

![Document-similarity network for the MBG corpus over 8,331 cleaned-document embeddings; edges retain cosine ≥ 0.90 among each document's k=5 nearest neighbors, the bounded figure shows 500 linked documents across the 20 largest components within a 500-node cap with smaller groups in grey, fitted G1–G4 color areas follow the displayed component extent only, and the layout uses deterministic spring placement with seed=42](assets/mbg/document_similarity_network.png)

The four leading groups shown are:

- **G1 — SPPG operations and budgeting: 146 documents, 100.00% dominant.**
- **G2 — corruption investigations: 87 documents, 74.71% dominant.**
- **G3 — food poisoning incidents: 61 documents, 93.44% dominant.**
- **G4 — separate corruption component: 47 documents, 100.00% dominant.**

The fitted color areas follow the displayed component extent and do **not**
represent confidence regions, ground-truth boundaries, or calibrated
estimates. "Dominant" means the share of documents inside the displayed
component that carry the indicated topic label, not a probability that the
component is exclusively about that topic.

**Interpretation boundary.** Proximity and edges mean embedding similarity
between retrieved documents. They do **not** establish shared event identity,
factual equivalence, causation, coordination, or editorial influence. The
layout uses a deterministic spring algorithm with `seed=42`, so the figure
is reproducible, but the visual placement is not itself meaningful beyond
revealing the connected components. Article-level evidence remains private
and is not published alongside this figure.

### Sentiment by topic

The aggregate sentiment classifier shows that news tone varies substantially by
topic. Among the larger substantive topics, food poisoning incidents coverage
(T2, **n=583**) has the clearest negative pattern: **58.8336%** of documents
have `negative` as their highest-probability label and the mean probability
score is **-0.471467**. Corruption investigations (T1, **n=657**) are mostly
neutral by highest-probability label (**56.3166%**) but still have a negative
mean score (**-0.372763**), reflecting very little positive probability. By
contrast, food and livestock supply (T5, **n=195**) has a positive mean score of
**+0.218492**.

![Diverging per-topic sentiment distribution for the 14 substantive topics, with negative and positive highest-probability label shares shown on opposing axes and neutral marked at the center](assets/mbg/topic_sentiment_diverging.png)

The figure reports each document's highest-probability label as a share of its
topic; the centered grey marker indicates neutral classification, while the
mean score used for ordering is the topic average of
`P(positive) - P(negative)`. These measures can differ. For example, SPPG
operations and budgeting (T0, **n=3,040**) has **892 positive**, **1,360 neutral**, and **788
negative** highest-probability labels, with a mean score of **+0.049018**.
Smaller substantive topics each contain at most 150 documents (T6 delivery vehicles
and procurement), so their directions are especially provisional. The
heterogeneous outlier class is
retained in aggregate reconciliation but omitted from this substantive-topic
figure.

Overall, the corpus shows **2,120 positive**, **3,398 neutral**, and **2,813
negative** highest-probability labels across the cleaned documents.



The figure is the public aggregate output; document-level predictions and the
underlying review tables remain private.

**Interpretation boundary.** The pinned Indonesian RoBERTa classifier was
trained on IndoNLU SmSA comments and reviews, not MBG news. Its outputs describe
the language tone of retrieved articles after right truncation at 512 model
tokens. They do **not** measure public opinion, policy effectiveness,
factuality, or stance, and the probabilities should be treated as ordinal
comparisons rather than calibrated population estimates.

### Named entities and SPPG kitchens

Provisional entity extraction surfaces the most-mentioned people, event
locations, and SPPG/Dapur kitchen references in the corpus. The figures
below are aggregate counts; surface-form resolution is provisional.

![Top-mentioned multi-token people across the 8,331 cleaned documents; provisional extraction yields 46,987 mentions resolved to 5,529 normalized surfaces](assets/mbg/person_top_bar.png)

Top-mentioned multi-token people across the corpus. Provisional extraction
yields **46,987 mentions resolved to 5,529 normalized surfaces**. Ranks
describe prominence in this retrieved corpus, not policy importance. Audited
aliases combine `Purbaya`, `Purba`, `Yudhi`, and `Yudhi Sadewa` with
**Purbaya Yudhi Sadewa (1,132 mentions across 271 documents)**. Ambiguous
single-token surfaces such as `Yusuf` are retained in aggregate tables but
excluded from this precision-oriented chart rather than assigned to one person.

![Top event locations; counts exclude publisher datelines and general geographic framing, with 1,810 mentions resolving to 535 unique places](assets/mbg/place_top_bar.png)

Top event locations: **1,810 mentions resolving to 535 unique places**.
These counts **exclude publisher datelines and general geographic
framing** — only locations anchored to a described event (visit, launch,
incident, audit) are counted. As a result, this chart under-represents
places that appear only as byline cities or background geography.

![Top SPPG/Dapur (satuan pelayanan pemenuhan gizi) kitchen references; 1,364 mentions resolve to 677 unique kitchen surfaces](assets/mbg/sppg_top_bar.png)

Top SPPG/Dapur (*satuan pelayanan pemenuhan gizi*) kitchen references:
**1,364 mentions resolving to 677 unique kitchen surfaces**. Unit numbers are
preserved where available, while strict normalization excludes regional
collectives and malformed identifiers. These automated identifiers remain
provisional until reconciled against operational records.

### Person co-mention network

The method builds an undirected graph over the canonical **8,331-document**
corpus. Each node is one normalized person surface. An edge connects two nodes
when both people occur in the same document; repeated mentions of the same
normalized person are deduplicated within that document before document and
edge counts are incremented.

The precision gate retains people mentioned in at least **25 documents** whose
canonical names contain at least **two tokens**. It retains an edge only when
the pair co-occurs in at least **5 documents** and has Jaccard similarity of at
least **0.05**, where Jaccard is the co-document count divided by the number of
documents mentioning either endpoint. These gates produce **26 nodes and 41
edges** across **5 connected components** and **6 detected communities**.

![Person co-mention network for the MBG corpus; the largest component shows 17 of 26 eligible normalized person surfaces, and node colors mark categorical detected-community IDs with no sentiment or political-polarity meaning](assets/mbg/person_comention_network.png)

The method uses the full canonical corpus and all eligible components, while
the figure displays only the largest connected component (**17 nodes**) for
readability. Its deterministic spring layout uses `seed=42`. Larger nodes
represent people mentioned in more documents; wider edges represent higher
co-document counts. Node colors distinguish only the detected communities
visible in the displayed component; visible community IDs are categorical,
not sentiment or political-polarity scores.

By weighted degree, the most connected eligible surfaces are **Sony Sonjaya
(1,015, 650 documents)**, **Prabowo Subianto (949, 2,770 documents)**,
**Dadan Hindayana (818, 1,114 documents)**, **Nanik Sudaryati Deyang
(658, 763 documents)**, and **Asep Yusuf Somantri (347, 203 documents)**.
The strongest single edge is **Dadan Hindayana ↔ Prabowo Subianto** with
**435 co-mentioned documents** (Jaccard 0.1261). Other top edges include
Nanik Sudaryati Deyang ↔ Prabowo Subianto (345), Dadan Hindayana ↔ Sony
Sonjaya (193), Prabowo Subianto ↔ Sony Sonjaya (169), and Asep Yusuf
Somantri ↔ Sony Sonjaya (155). The figure illustrates aggregation only.

Names remain provisional NER surfaces: there is no general co-reference
resolution, and ambiguous identities may still split or merge. Audited
`Purbaya`/`Yudhi Sadewa` fragments are canonicalized to `Purbaya Yudhi Sadewa`;
ambiguous bare `Yusuf` remains unresolved and is excluded by the two-token
network precision gate. No article-level evidence is published.

**Interpretation boundary.** Co-mention indicates only shared coverage within
the same retrieved document. It does **not** establish a personal relationship,
influence, endorsement, coordination, political alignment, or causality.

## Collection Limitations

Be explicit about what this corpus can and cannot support.

- **Retrieval coverage.** The registry contains 75 entries; 68 stable sources
  are search-capable and 48 contributed documents retained after cleaning.
  Four stable sources (`aljazeera`, `balipost`, `hukumonline`, and
  `independen`) support latest collection only and cannot participate in
  keyword search. The `investor`, `bantennews`, and `dandapala` entries
  are `investigating` status and are excluded from the stable CLI resolver;
  `dandapala` also supports latest collection only. Sources outside the
  registry are not searched.
- **Keyword recall.** Retrieval uses six related queries: `mbg`, `makan bergizi
  gratis`, `program MBG`, `satuan pelayanan pemenuhan gizi`, `SPPG`, and
  `badan gizi nasional`. Articles that discuss implementation without any of
  those terms can still be missed.
- **Completeness.** A finished corpus is bounded by what each scraper's
  search endpoint exposes. Some sources cap depth, return only top-N, or
  paginate inconsistently. Re-running with a tighter window or
  source-by-source will not necessarily close those gaps.
- **Copyright.** Each row is a *news article record*: title, link,
  publish date, author, and a content excerpt as returned by the source's
  own feed/page. The corpus is suitable for aggregate analysis, citation,
  and downstream modeling within fair-use research bounds; it is not a
  redistribution of full article text. Honor each publisher's terms.