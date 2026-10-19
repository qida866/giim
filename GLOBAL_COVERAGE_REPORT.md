> Historical engineering report. Referenced raw evaluation files are retained in the local research archive and are not distributed in this release. See `docs/evaluation.md` for public reproduction limits.

# GIIM Global coverage report

## Phase 3 update — September 28–29, 2026 UTC

The September 28 local refresh succeeded for 38/39 feeds; France 24 English returned HTTP 200 with unusable feed content. Public coverage now normalizes the legacy BBC name to the same publisher organization: 26 observed organizations and ten reporting languages. No new media publisher was added. The official USGS feed now covers seven days and distinguishes instrument IDs despite repeated headlines. The new dated AP reference found six of eight bounded events, plus an excluded analysis item; two misses remain upstream and their exact historical source/ingestion causes are unresolved. This is not global recall. See the Phase 3 report for source-access limits, same-window statistics and reference links.

The record below preserves the dated Phase 2 baseline; its numbers are historical, not current Phase 3 counters.

---

## Registry and real ingestion

The registry contains **53 entries: 39 locally enabled and 14 disabled**. There are 35 production-enabled feeds. Real ingestion on September 22 recovered to **39 successes, zero failures, 111 inserted reports and four not-modified responses in 77.12 seconds**. An earlier expanded run succeeded on all then-enabled 37 feeds. These are dated observations, not continuous uptime claims.

At September 23 18:56 UTC, the seven-day window contains **1,204 verified-time reports from 26 publisher organizations in ten languages (27 raw identifiers)**: Arabic, German, English, Spanish, French, Japanese, Korean, Portuguese, Russian and Chinese. Publisher country/jurisdiction codes: AU, BR, CG, DE, FR, GB, HK, IN, JP, KR, LV, PK, QA, SG, TH, US, UY, ZA. UN reporting is global, not another country.

Publisher-region report counts are Europe 411, Asia-Pacific 505, Americas 85, Africa 82, Middle East 35, Global 27, Eastern Europe 33 and Oceania 25. These describe publisher metadata and can overlap; they do not measure incident geography or geographic completeness.

Enabled publisher organizations include BBC, NPR, PBS, Guardian, DW, France 24, Yonhap, RTHK, CNA, Hindu, Indian Express, Dawn, Bangkok Post, Africanews, Daily Maverick, Al Jazeera, Agencia Brasil, MercoPress, NASA, UN News, SBS, Mainichi, Meduza, SCMP, The Verge and USGS. Several have multiple language/category feeds; feed count is not publisher count. The canonical registry and operational snapshot contain the exact feed identities.

Feed category observations include general 1,106, technology 20, AI 10, business 26, science 29, geopolitics 27, humanitarian 27, disasters 42 and economy 16. These tags overlap and are not an audited event taxonomy. Business and science Guardian feeds were added after the initial coverage-gap review.

The public coverage counter currently shows 27 because one older BBC report lacks canonical publisher metadata and is counted separately from `bbc`. A read-only database audit confirmed 26 actual organizations. This is a remaining metadata-normalization defect; the event-level independence estimates should also be reviewed for legacy-name handling.

## Health and access limits

All 39 enabled feeds are **overdue**, not newly failed, in the September 23 audit because no local scheduler ran after validation. Last-success and last-failure records are distinct. An earlier wrapper defect incorrectly treated 304 responses as redirects, producing two failures in one refresh and nine in a later refresh; the repaired real run succeeded on all 39 feeds.

Disabled entries retain reasons: CBC timeout; RNZ forbidden; TASS connection failure; Kyiv Independent, Infobae and China Daily unavailable endpoints; NHK and WHO stale evidence; GDACS retained as an external reference; HN submission-time provenance; Xinhua/People missing reliable dates; 36kr/Huxiu connection failures. Their failure is not interpreted as absence of news.

Known personal/noncommercial feed restrictions exclude CNA and three Guardian feeds from production mode. Public availability is not a redistribution license. No direct Reuters/AP ingestion was fabricated. Source references and validation observations are in `config/sources.json` and `evaluation/source-validation-2026-09-22.json`.

## Event coverage

The September 23 audit counts **1,064 current stored items**: 1,006 single-publisher, 58 with two or more publishers, 17 with three or more. Mean publishers/item: **1.080**; median: **1**. Of these items, 91 are AI-reviewed summaries and 973 are attributed source excerpts. These are not 1,064 independently confirmed real-world events.

A real evolving story retained one ID across three observed versions, growing from one to three to six reports, ultimately representing three publishers, three languages and two publisher regions. The UI also exposes estimated reporting-origin independence, avoiding a claim that translated editions or obvious wire copies are independent confirmation.

## Independent discovery reference

`evaluation/coverage-reference.json` freezes a September 15–22 window: nine leading AP World/Business/Technology references plus four GDACS cyclone references, totaling 13 entries / 12 distinct stories because Polo overlaps. These were discovery references, not additional ingested corroboration.

Assistant review found reporting for six reference entries / five distinct stories: UN assembly, Polo, Paramount settlement, US-China AI safety and Dujuan. Gaps included the Bolivia species story, Wendy's franchise bankruptcy, market rally, AI antitrust delay, OpenAI behavior report, Odalys and Fay. This is a small, purposive reference comparison, not global recall. Keyword candidate retrieval can miss translations. Missing source reports indicate discovery/window gaps, not necessarily clustering failures. Later source additions do not retroactively improve this baseline result.

## Blind spots

Canada-local, mainland-China, Russia-domestic and Spanish-language Latin America remain weak. Africa, Middle East, Japan and Korea have limited local publisher diversity. English is dominant. USGS day-feed backfill cannot discover every older disaster. Short RSS excerpts constrain event identity and perspective analysis. Headlines in broad categories do not guarantee meaningful coverage of health, energy, culture or local public safety. Better coverage requires additional usable sources, independent reference review and ongoing freshness monitoring, not simply more URLs.
