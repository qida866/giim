"""发布者、所有权组、明显转载分别计数；报道广度不是事实真伪。"""

import hashlib
import re
from src.models.news import News


from src.services.publisher_identity import publisher_id, canonical_name


def wire_credit(news: News) -> str | None:
    byline = str((news.raw_metadata or {}).get("byline", "")).casefold()
    for key, pattern in [
        ("reuters", r"\breuters\b"),
        ("afp", r"\bafp\b|agence france.presse"),
        ("ap", r"\bassociated press\b|^ap$"),
    ]:
        if re.search(pattern, byline):
            return key
    return None


def evidence_coverage(news: list[News]) -> dict:
    parents = list(range(len(news)))

    def root(i: int) -> int:
        while parents[i] != i:
            i = parents[i]
        return i

    seen = {}
    countries = set()
    regions = set()
    languages = set()
    publishers = set()
    official = set()
    for i, n in enumerate(news):
        m = n.raw_metadata or {}
        pid = publisher_id(n)
        publishers.add(pid)
        languages.add(n.language)
        if m.get("publisher_country") and m["publisher_country"] != "UN":
            countries.add(m["publisher_country"])
        if m.get("publisher_region"):
            regions.add(m["publisher_region"])
        if m.get("source_role") == "official":
            official.add(pid)
        keys = ["owner:" + canonical_name(str(m.get("ownership_group") or pid))]
        content = " ".join((n.content or "").casefold().split())
        if len(content) >= 160:
            keys.append("copy:" + hashlib.sha256(content.encode()).hexdigest())
        if wire_credit(n):
            keys.append("credited-wire:" + wire_credit(n))
        for key in keys:
            if key in seen:
                parents[root(i)] = root(seen[key])
            else:
                seen[key] = i
    groups = len({root(i) for i in range(len(news))})
    state = (
        "limited_coverage" if groups <= 1 else "multi_source" if groups < 4 else "broadly_reported"
    )
    return {
        "articles": len(news),
        "publishers": len(publishers),
        "publisher_ids": sorted(publishers),
        "independent_evidence_groups": groups,
        "publisher_countries": sorted(countries),
        "publisher_regions": sorted(regions),
        "languages": sorted(languages),
        "official_sources": sorted(official),
        "state": state,
        "basis": "Known ownership, identical long excerpts and explicit wire bylines; independence remains an estimate, not verification of truth.",
    }


def claim_status(news: list[News]) -> str:
    coverage = evidence_coverage(news)
    if len(news) == 1 and coverage["official_sources"]:
        return "official_source_statement"
    return (
        "reported_by_multiple_origins"
        if coverage["independent_evidence_groups"] > 1
        else "reported_by_one_origin"
    )
