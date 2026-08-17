# What 59,197 articles with Prabowo in the headline show

Using `news-watch`, I collected and cleaned **59,197 article records from 53
Indonesian news sources whose headlines name Prabowo Subianto**. The collection
runs from his inauguration on 20 October 2024 to 14 August 2026. That gives 23
calendar-month buckets, although the first and last months are partial.

This is not a census of everything those portals published, nor is it all
coverage of the administration. It is a deliberately narrower object: retrieved
articles that put `prabowo` in the headline. Within the 43,500 records assigned
to a model-generated topic, foreign relations and state visits is the largest
theme at 19.0%. Across the full corpus, the sentiment model labels 50.6% of
records neutral. Law enforcement, corruption and the judiciary is the only
theme with a negative plurality. A person co-mention network also shows stronger
normalized overlap among a selected group of business figures than among
selected senior politicians.

Those findings come with limits. The topic model left 15,697 records unassigned,
search access varied sharply between portals, and the sentiment classifier was
not trained on news. The numbers describe this retrieved corpus, not public
opinion, policy performance, or the full Indonesian news ecosystem.

*Published on Indonesia's 81st Independence Day. Selamat Hari Kemerdekaan.*

## What the corpus measures

Prabowo was inaugurated on 20 October 2024 and announced the Kabinet Merah Putih
that evening. Starting on inauguration day keeps campaign and transition
coverage outside the window. It also explains why cabinet coverage is unusually
high in the first, partial month.

A record enters the corpus only when its title contains a standalone mention of
`prabowo`, matched without regard to case. The search ran against 74 stable
registry entries that supported keyword search; 53 sources contributed records
that survived cleaning.

The title rule gives the study a clear boundary, but it has a substantial cost.
Of 90,515 records that fell inside the date window and had unique links, 29,561
were excluded because they mentioned Prabowo only in the body. Another 2,308 of
those excluded records named a flagship programme such as Sekolah Rakyat or MBG
in the title without naming him there.

I read an exploratory sample of 40 title-excluded records using seed 42. Ten were
genuine coverage of Prabowo or his programmes, four were arguable, and 26 used
his name mainly as context for the current administration. The sample is too
small to estimate the whole excluded pool precisely. It does show why a simple
word rule could not separate central coverage from era context reliably.

After cleaning, 43,500 records received one of 111 topics. The remaining 15,697,
or 26.5%, fell into the model's outlier category. Every theme percentage below
therefore uses the assigned set as its denominator.

## Foreign relations is the largest sustained theme

The final 111 model-generated topics were grouped into 17 readable themes.
Foreign relations and state visits is the largest, with 8,273 records or 19.0%
of the assigned set. Cabinet, appointments and protocol follows at 11.8%. No other
theme reaches 12%.

![Documents by model-assigned theme](assets/prabowo/theme_size_bar.png)

The UMAP view below comes from an earlier 121-topic projection of the same
59,197 records. The published analysis later consolidated that fit to 111
reported topics, so the scatter is retained as a visual diagnostic rather than
a count of the final topic inventory. Each point is a record; grey points are
the 15,697-record outlier class. Distance in this two-dimensional projection is
suggestive, not proof that two themes are distinct.

![UMAP projection from the earlier 121-topic fit](assets/prabowo/umap_scatter.png)

The result is broad rather than tied to one diplomatic counterpart. The
underlying topics include Palestine, Russia, China, France, India, Japan, Korea,
the Gulf states, ASEAN, the European Union, Brazil, and Turkiye.

Foreign-relations coverage is also spread more evenly through the study window
than cabinet coverage. Its busiest month contains 733 assigned records, 1.94
times its median month. Cabinet coverage reaches 1,050 records in October 2024,
6.91 times its median, because the inauguration and cabinet announcement fell in
that partial month.

![Monthly volume for six themes](assets/prabowo/theme_trendline.png)

For the six themes in the chart, observed lag-one autocorrelation ranges from
-0.13 to +0.05. That provides little evidence of month-to-month persistence in
this window; it does not prove that one month contains no information about the
next. The chart uses monthly buckets because coarser quarters would conceal the
short cabinet and food-policy peaks.

Two sources also arrive in bursts rather than across the full period.
Wartaekonomi contributes 1,761 records on 96 distinct days, while Jawapos
contributes 706 across 170 days. Their absence in other months is a retrieval
pattern, not evidence that news volume disappeared. Any time-series use of this
corpus should exclude or explicitly account for such intermittent sources.

The topic partition deserves similar restraint. It is one plausible grouping of
a broad corpus, not a definitive taxonomy of the presidency. The fit has no
measured cross-seed stability, and a small change to the records could move topic
boundaries. That uncertainty is why the analysis keeps 111 topics instead of
compressing them into a deceptively tidy dozen.

## Most records receive a neutral label

Across all 59,197 records, the sentiment model assigns **29,963 neutral labels
(50.6%), 17,759 positive (30.0%), and 11,475 negative (19.4%)**. Meeting
readouts, appointments, and protocol stories make up much of the collection, so
a large neutral share is unsurprising.

Law enforcement, corruption and the judiciary stands apart. It is the only theme
where negative is the plurality label, at 44.9%, and it has the lowest mean score
at -0.30. The next-lowest displayed mean is -0.08 for labour, wages and welfare.
This makes law enforcement the strongest negative outlier. It does not mean that
this theme contains most of the corpus's negative records.

![Model-assigned sentiment by theme](assets/prabowo/topic_sentiment_diverging.png)

The positive end needs more caution than the negative one. Religion, ceremony
and commemoration has the highest mean at +0.33, followed by foreign relations at
+0.25. Both contain a great deal of polite protocol language: greetings,
congratulations, arrivals, and departures. A classifier trained on Indonesian
comments and reviews can read that register as positive even when a news report
is simply formal.

For that reason, sentiment here means model-assigned language tone in the title
and retained article text. It does not measure approval, stance, truth,
factuality, or policy effectiveness. Long records were also truncated from the
right at 512 model tokens, which gives the title and opening paragraphs more
weight. The exact model and settings are listed under [Method in brief](#method-in-brief).

## In the selected groups, business names overlap more strongly

The person co-mention network asks which names occur in the same retrieved
records. It does not infer personal relationships. This is an exploratory,
descriptive comparison between two selected groups, not a representative sample
of business figures or politicians. Eight business figures have a mean Jaccard
overlap of **0.389 across 28 retained edges**. Seven senior politicians have a
mean of **0.089 across eight retained edges**.

Jaccard measures how strongly two names' sets of records overlap after accounting
for how often each name appears. The roughly fourfold difference is therefore a
difference in normalized co-coverage, not raw mention frequency.

![Person co-mention network](assets/prabowo/person_comention_network.png)

The business group consists of Anthony Salim, Boy Thohir, Prajogo Pangestu,
Sugianto Kusuma, Franky Widjaja, James Riady, Dato Sri Tahir, and Tomy Winata.
The political group contains Prabowo, Joko Widodo, Gibran Rakabuming Raka,
Megawati Soekarnoputri, Muhaimin Iskandar, Puan Maharani, and Ahmad Muzani. The
strongest political edge, Gibran with Joko Widodo at 0.160, remains below the
weakest business edge in this comparison.

The most plausible reading concerns the shape of coverage. Business figures tend
to appear together in a smaller set of investment and appointment stories.
Politicians appear across many unrelated stories and therefore share a smaller
fraction of their respective record sets. Co-mention alone says nothing about
influence, endorsement, coordination, or personal affinity.

Six of the 15 strongest original edges joined one person to an alias, including
`Cak Imin` with `Muhaimin Iskandar`, `Gus Ipul` with `Saifullah Yusuf`, and `Gus
Yahya` with `Yahya Cholil Staquf`. Resolving all six pairs reduced the graph from
237 nodes and 479 edges to 230 nodes and 473 edges. This matters because `Gus`
and `Cak` prefix nicknames rather than formal names, so a simple prefix rule
misses them.

The query itself also shapes the ranking. Prabowo appears in 98.8% of records and
accounts for 331,466 of 777,979 person mentions. His rank measures the query
rather than his prominence, so the ranking below excludes him. Joko Widodo then
leads at 5,833 records, or 9.9%, followed by Gibran, Teddy Indra Wijaya, Prasetyo
Hadi, and Donald Trump. These are automated extractions, not measures of
political importance.

![Most-mentioned people after excluding the query term](assets/prabowo/person_top_bar.png)

The location extraction supplies a second view of the corpus. Jakarta leads at
1,681 records, followed by Aceh, Russia, India, and China. Eight of the ten most
frequent extracted locations are foreign. The ranking mixes places where events
occurred with places mentioned in diplomacy: Aceh reflects the December 2025
Sumatra flood response, while Russia, India, and China often appear in state-visit
coverage. The NER model extracts strings rather than verified event geographies,
so this chart cannot establish where every article's event took place.

![Most-mentioned extracted locations](assets/prabowo/place_top_bar.png)

## Event-driven stories form the clearest clusters

The similarity network reveals structure below the broad theme labels.
Event-driven coverage forms the cleanest clusters: trade and tariffs, disasters,
party politics, and cabinet stories account for 98% to 100% of their respective
displayed components. Broader policy coverage is less cohesive. The largest
displayed component is only 58% fiscal policy and macroeconomy, while law
enforcement divides into two disconnected components. Broad themes can
therefore contain separate story cycles, while discrete events generate
unusually similar reporting across records.

![Seven displayed document-similarity components](assets/prabowo/document_similarity_network.png)

The figure omits three components above the 400-record panel cap and reports them
in its caption. The graph links up to three nearest neighbours at cosine
similarity 0.90 or higher. It contains 27,354 active records and 33,555 edges;
31,843 records are isolated. Because this graph and BERTopic share the corpus
and embedding pipeline, the comparison is an internal structural check, not
independent validation.

## How incomplete is the retrieval?

No single number can measure recall across all 53 contributing sources because
most portals do not expose an exhaustive date index. I used two narrower checks
instead.

Kompas does have a date index. On ten days sampled across the study window, that
index listed 239 articles whose titles matched the corpus rule. The corpus
contained 235, or 98.3%. This result applies only to Kompas and those ten sampled
days. Three of the four misses were opinion columns, suggesting that its search
surface may return commentary less reliably than news.

A second audit re-ran searches from **1 July to 14 August 2026** using `prabowo
subianto`, `presiden prabowo`, and `kepala negara`. After applying the same
gates, 255 underlying articles were absent from the main corpus, a 4.06% omission
rate within that audit window. If 55 records with already-covered normalized
titles but different URLs count as misses, the rate rises to 4.90%.

That range is a window-specific lower bound, not an estimate of corpus-wide
recall. Both collections used the same scrapers against the same sites, so they
can share blind spots. Failure also varies by source and keyword.

Source shares are even less comparable. Kompas accounts for 26.2% of the corpus
because its date-partitioned archive allowed collection close to completeness.
Other national portals expose short RSS windows, capped result sets, or search
pages that cannot be paged deeply. Their smaller shares do not show that they
published less.

Use this corpus to study the retrieved language and themes, with adjustments for
bursty sources when working over time. Do not use it to rank portals by how much
they covered Prabowo.

## What the articles show

The clearest pattern is sustained attention to foreign relations. It is the
largest final model-assigned theme without depending on one isolated month, and
the location extraction gives a compatible but provisional view. Much of the
corpus is formal and receives a neutral sentiment label, while law enforcement
and the judiciary is the distinct negative outlier. The person and document
networks show two more structures: business names recur in tightly overlapping
stories, and broad themes can contain separate story clusters.

Each result describes a bounded collection. Headlines must name Prabowo,
retrieval depends on what each portal exposes, more than a quarter of records
remain outside the topic model, and the sentiment labels carry a domain mismatch.
These findings apply only within those limits.

## Method in brief

After schema and date checks, records had to contain `prabowo` in the title,
have a unique link and normalized title, include at least 200 body characters,
and pass an Indonesian-language heuristic. The shortest rejected body was the
six-character byline `VIVA -`.

Topic embeddings came from
`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`. BERTopic used
`min_cluster_size=120` and seed 42. The final reported inventory contains 111
topics plus an outlier class, grouped by the analyst into 17 themes. The retained
UMAP image visualizes an earlier 121-topic projection over the same corpus; it is
not the source of the final topic count. No cross-seed stability study was run.

Sentiment used
`w11wo/indonesian-roberta-base-sentiment-classifier` at revision
`ac452dcb0f4966130bba44f4ee0013bb5d52c282`. Its input was the title followed by
the body, right-truncated at 512 model tokens. Person extraction used
`cahya/bert-base-indonesian-NER` at revision
`a3a3fa494cf7555ef87f446af5e826de3ed181c0`, with a 0.4 score threshold. A
network edge required at least five shared records and Jaccard overlap of 0.05.

The collection process also changed the software. The first attempt returned
16,909 usable records and a source distribution distorted by four defects. Some
sites repeated a page indefinitely, some extraction rules harvested unrelated
page links, two scrapers cut an unordered set to 20 links, and Kompas's capped
search looked complete when it was not. The fixes stopped stale pagination,
scoped extraction to result containers, removed the arbitrary set cut, and
partitioned Kompas searches by date.

The analysis uses the fixed reference run ending on 14 August 2026, collected
with `news-watch` v1.2.5. Retrieval-audit counts and the 16,909-record pre-fix
collection came from separate diagnostic runs. Software DOI:
[10.5281/zenodo.14908389](https://doi.org/10.5281/zenodo.14908389). When quoting
an article, cite the publisher, title, publication date, and URL. The corpus
record is a pointer, not the source of record.
