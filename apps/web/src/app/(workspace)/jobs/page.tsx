import Link from "next/link";
import { apiGet } from "@/lib/api";
import type { JobsPage, Settings } from "@/lib/types";
import { DiscoverForm } from "@/components/discover-form";
import { MatchBadge } from "@/components/match-badge";
import { Notice } from "@/components/notice";
import { dateTime } from "@/lib/format";

export default async function Jobs({ searchParams }: { searchParams: Promise<{
  q?: string; eligibility?: string; min_score?: string; shortlisted?: string; offset?: string; status?: string; error?: string;
}> }) {
  const params = await searchParams;
  const query = new URLSearchParams();
  if (params.q) query.set("q", String(params.q).slice(0, 200));
  if (["ELIGIBLE", "INELIGIBLE", "NEEDS_REVIEW"].includes(params.eligibility ?? "")) query.set("eligibility", params.eligibility!);
  const score = Math.max(0, Math.min(100, Number(params.min_score) || 0));
  const offset = Math.max(0, Math.floor(Number(params.offset) || 0));
  if (score) query.set("min_score", String(score));
  if (params.shortlisted === "true") query.set("shortlisted", "true");
  if (params.status === "CLOSED") query.set("status", "CLOSED");
  query.set("offset", String(offset));
  const [jobs, settings] = await Promise.all([
    apiGet<JobsPage>(`/api/v1/jobs?${query}`), apiGet<Settings>("/api/v1/settings"),
  ]);
  function pageHref(next: number) {
    const nextQuery = new URLSearchParams(query); nextQuery.set("offset", String(next));
    return `/jobs?${nextQuery}`;
  }
  return <div className="space-y-6">
    <div className="flex flex-wrap items-center justify-between gap-4"><div><p className="eyebrow">Opportunities</p><h1 className="text-3xl font-semibold">Find your next role</h1></div><DiscoverForm settings={settings} /></div>
    <Notice error={params.error} />
    <form className="panel grid items-end gap-4 sm:grid-cols-2 lg:grid-cols-6" method="GET">
      <div className="lg:col-span-2"><label htmlFor="q">Search jobs, companies, locations</label><input id="q" name="q" defaultValue={params.q} maxLength={200} className="mt-2" placeholder="Python, Bengaluru, company…" /></div>
      <div><label htmlFor="eligibility">Eligibility</label><select id="eligibility" name="eligibility" defaultValue={params.eligibility ?? ""} className="mt-2"><option value="">All</option><option value="ELIGIBLE">Eligible</option><option value="NEEDS_REVIEW">Needs review</option><option value="INELIGIBLE">Not eligible</option></select></div>
      <div><label htmlFor="min_score">Minimum score</label><input id="min_score" name="min_score" type="number" min={0} max={100} defaultValue={score} className="mt-2" /></div>
      <div><label htmlFor="status">Listing status</label><select id="status" name="status" defaultValue={params.status ?? "OPEN"} className="mt-2"><option value="OPEN">Open</option><option value="CLOSED">Closed</option></select></div>
      <div className="space-y-3"><label className="flex items-center gap-2 font-normal"><input type="checkbox" name="shortlisted" value="true" defaultChecked={params.shortlisted === "true"} />Saved only</label><button type="submit">Filter</button></div>
    </form>
    <div className="flex flex-wrap justify-between gap-2 text-sm text-slate-500"><p>{jobs.total} jobs · sorted by current match score</p><Link href="/settings">Manage career sources</Link></div>
    {!jobs.items.length ? <section className="panel space-y-3"><h2 className="text-xl font-semibold">No jobs match this view yet.</h2><p className="text-slate-600">Add a company board in Settings, complete your verified profile, and run discovery. If you already have jobs, broaden your filters.</p></section> : <div className="space-y-4">
      {jobs.items.map((job) => <article className="panel" key={job.id}>
        <div className="flex items-start justify-between gap-4"><div className="space-y-2"><p className="text-sm font-semibold text-emerald-800">{job.company}{job.shortlisted ? " · Saved" : ""}</p><h2 className="text-xl font-semibold"><Link href={`/jobs/${job.id}`}>{job.title}</Link></h2><p className="text-sm text-slate-600">{job.location_text}</p></div>
          <div className="text-right"><p className="text-3xl font-semibold">{job.match?.score ?? "—"}</p><p className="text-xs text-slate-500">{job.match?.score != null ? "fit score / 100" : "not ranked"}</p></div>
        </div>
        <div className="mt-4 flex flex-wrap items-center gap-3"><MatchBadge match={job.match} /><span className="text-xs text-slate-500">{job.match?.provider === "gemini" ? "Gemini" : "Rule-based"} · Last seen {dateTime(job.last_seen_at)}</span></div>
        <p className="mt-3 text-sm text-slate-600">{job.match?.reason ?? "Your profile or listing changed. Open the job and refresh its match."}</p>
      </article>)}
    </div>}
    <nav aria-label="Job result pages" className="flex justify-between text-sm">
      {offset > 0 ? <Link href={pageHref(Math.max(0, offset - jobs.limit))}>← Previous</Link> : <span />}
      {offset + jobs.items.length < jobs.total && <Link href={pageHref(offset + jobs.limit)}>Next →</Link>}
    </nav>
  </div>;
}
