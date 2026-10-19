'use strict';
function reportCard(r) {
 return `<article class="event-card"><span class="tag">Source reporting · ${esc(r.language)}</span><h3 class="event-title"><a href="${esc(safeURL(r.url))}" target="_blank" rel="noopener noreferrer">${esc(r.title)}</a></h3><p class="muted">${esc(r.source)} · ${esc(date(r.published_at))}</p></article>`;
}
function claimEvidence(s) {
 return `<p>${esc(s.text)}</p>${(s.citations||[]).map(c=>`<blockquote><a href="#source-${Number(c.news_id)}">Report ${Number(c.news_id)}</a>: ${esc(c.quote)}</blockquote>`).join('')}`;
}
function intelligenceDetail(data) {
 const ev=data.event, p=data.perspectives||{}, coverage=ev.coverage||{};
 const why=ev.why_it_matters?`<section><h3>Why it matters <small>AI interpretation</small></h3>${claimEvidence(ev.why_it_matters)}</section>`:'';
 const compared=(p.common_facts||[]).length?`<h3>Commonly reported facts</h3>${p.common_facts.map(claimEvidence).join('')}`:'';
 const differences=(p.differences||[]).length?`<h3>Differences in reporting</h3>${p.differences.map(d=>`<h4>${esc(d.kind.replaceAll('_',' '))}</h4>${d.reporting.map(claimEvidence).join('')}`).join('')}`:'';
 const uncertain=(p.uncertainties||[]).length?`<h3>Uncertain or developing</h3>${p.uncertainties.map(claimEvidence).join('')}`:'';
 const canonical=data.canonical_event_id?`<p>This historical card was consolidated. <button data-event="${esc(data.canonical_event_id)}">Open current story</button></p>`:'';
 const pending=data.provenance?.revalidation_pending?'<p class="muted">This story needs review. The previous AI brief has been withdrawn pending review; current source reporting is shown.</p>':'';
 const support=(data.current_support_ids||[]).length?`<p class="muted">Current summary uses reports ${(data.current_support_ids||[]).map(Number).join(', ')}. Other reports provide story history and do not automatically confirm new claims.</p>`:'';
 const revisions=data.revisions||[];
 const changes=revisions.length>1?`<details><summary>What changed · ${revisions.length} recorded versions</summary><p class="muted">GIIM observation times; these are not incident occurrence times.</p>${revisions.map(r=>`<article class="source-article"><time>${esc(date(r.recorded_at))}</time><h4>${esc(r.title)}</h4><p>${esc(r.summary)}</p><p>${r.added_news_ids.length} reports added · ${r.removed_news_ids.length} removed</p></article>`).join('')}</details>`:'';
 const timeline=data.articles.length>1?`<details><summary>Reporting timeline</summary><p class="muted">Publication times, not inferred times of developments.</p><ol>${[...data.articles].filter(n=>n.time_quality==='verified').sort((a,b)=>new Date(a.published_at)-new Date(b.published_at)).map(n=>`<li><time>${esc(date(n.published_at))}</time> · ${esc(n.source)}<p><a href="#source-${Number(n.id)}">${esc(n.title)}</a></p></li>`).join('')}</ol></details>`:'';
 return `${canonical}${pending}${support}${why}<section><h3>Coverage and confidence</h3><p>${coverage.publishers||ev.sources_count} publishers · ${(coverage.publisher_regions||[]).length} reporting regions · ${(coverage.languages||ev.languages).length} languages</p><p class="muted">${esc((coverage.state||'limited_coverage').replaceAll('_',' '))}. ${coverage.independent_evidence_groups??ev.sources_count} estimated reporting origins after known ownership and syndication. Reporting breadth does not establish factual certainty.</p></section>${compared}${differences}${uncertain}${changes}${timeline}`;
}
