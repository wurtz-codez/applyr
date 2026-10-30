import Link from "next/link";
import { notFound } from "next/navigation";
import { apiFetch, apiGet } from "@/lib/api";
import type { ApplicationsPage, JobDetail, Settings } from "@/lib/types";
import { matchJob, toggleShortlist, trackApplication } from "@/app/mvp-actions";
import { SubmitButton } from "@/components/submit-button";
import { MatchBadge } from "@/components/match-badge";
import { Notice } from "@/components/notice";
import { dateTime, label } from "@/lib/format";

export default async function JobPage({ params, searchParams }: {
  params: Promise<{ id: string }>; searchParams: Promise<{ error?: string }>;
}) {
  const { id } = await params;
  if (!/^[0-9a-f-]{36}$/i.test(id)) notFound();
  const response = await apiFetch(`/api/v1/jobs/${id}`);
  if (response.status === 404 || response.status === 422) notFound();
  if (!response.ok) throw new Error("Could not load job");
  const job: JobDetail = await response.json();
  const [settings, applications, messages] = await Promise.all([
    apiGet<Settings>("/api/v1/settings"), apiGet<ApplicationsPage>(`/api/v1/applications?job_id=${id}`), searchParams,
  ]);
  const match = job.match;
  return <div className="space-y-6">
    <Link href="/jobs" className="text-sm">← All jobs</Link>
    <Notice error={messages.error} />
    <section className="panel space-y-4"><p className="eyebrow">{job.company}</p><h1 className="text-3xl font-semibold">{job.title}</h1>
      <p className="text-slate-600">{job.location_text} · {label(job.status)} · Last seen {dateTime(job.last_seen_at)}</p>
      <div className="flex flex-wrap items-center gap-4"><MatchBadge match={match} />
        <a href={job.source_url} target="_blank" rel="noopener noreferrer" className="font-semibold">Open original listing ↗</a>
        <form action={toggleShortlist}><input type="hidden" name="job_id" value={id} /><input type="hidden" name="saved" value={String(job.shortlisted)} /><SubmitButton className="secondary">{job.shortlisted ? "Unsave job" : "Save job"}</SubmitButton></form>
      </div>
    </section>
    <div className="grid items-start gap-6 lg:grid-cols-[1fr_320px]">
      <div className="space-y-6">
        <section className="panel space-y-4"><div className="flex flex-wrap items-center justify-between gap-4"><h2 className="text-xl font-semibold">Match and eligibility</h2>
          <form action={matchJob}><input type="hidden" name="job_id" value={id} /><input type="hidden" name="use_ai" value={String(settings.ai_configured)} /><SubmitButton pendingText="Matching…">{settings.ai_configured ? "Match with Gemini" : "Refresh rule-based match"}</SubmitButton></form>
        </div>
          {job.needs_rematch && <p className="rounded-lg bg-amber-50 p-3 text-amber-900">Your profile or the listing changed. Refresh the match to evaluate the current information.</p>}
          {match && <><p className="text-4xl font-semibold">{match.score ?? "Not ranked"}{match.score != null && <span className="text-base font-normal text-slate-500"> / 100</span>}</p>
            <p className="text-sm text-slate-500">{match.provider === "gemini" ? `Gemini · ${match.model_id}` : "Deterministic rules"} · {label(match.confidence)} confidence</p>
            <p className="text-slate-600">{match.reason}</p>
            {match.warning && <p className="text-sm text-amber-800">AI analysis was unavailable or not configured. The result uses deterministic rules.</p>}
            <ul className="list-disc space-y-2 pl-5 text-sm">{match.eligibility_reasons.map((reason, i) => <li key={i}>{reason}</li>)}</ul>
            {match.component_scores && <dl className="grid grid-cols-2 gap-3 text-sm">{Object.entries(match.component_scores).map(([key, value]) => <div key={key} className="rounded-lg bg-slate-50 p-3"><dt>{label(key)}</dt><dd className="mt-1 font-semibold">{value}/100</dd></div>)}</dl>}
            {!!match.matched_skills?.length && <p className="text-sm"><strong>Matched skills:</strong> {match.matched_skills.join(", ")}</p>}
            {!!match.missing_skills?.length && <p className="text-sm"><strong>Potential gaps:</strong> {match.missing_skills.join(", ")}</p>}
          </>}
          {!!job.evidence.length && <div className="border-t border-slate-200 pt-4"><h3 className="font-semibold">Supporting verified facts</h3><ul className="mt-3 list-disc space-y-2 pl-5 text-sm">{job.evidence.map((fact, i) => <li key={i}>{String(fact.statement)}<span className="block text-slate-500">{String(fact.evidence_source)}</span></li>)}</ul></div>}
          <p className="text-xs text-slate-500">Scores estimate relative fit, not your probability of getting hired. Uncertain eligibility is never treated as confirmed.</p>
        </section>
        <section className="panel space-y-4"><h2 className="text-xl font-semibold">Job description</h2><p className="whitespace-pre-wrap break-words leading-7 text-slate-700">{job.description_text || "No description is available. Read the original listing."}</p></section>
      </div>
      <aside className="panel space-y-4"><h2 className="text-xl font-semibold">Track your application</h2>
        {applications.items.length ? <><p>Current status: <strong>{label(applications.items[0].status)}</strong></p><Link href="/applications">Update application →</Link></> : <>
          <p className="text-sm text-slate-600">Apply on the original career site, then record it here. Your current default resume version will be attached to the tracking record.</p>
          <form action={trackApplication} className="space-y-4"><input type="hidden" name="job_id" value={id} /><input type="hidden" name="status" value="APPLIED" />
            <label htmlFor="notes">Notes (optional)</label><textarea id="notes" name="notes" maxLength={4000} rows={3} />
            <label className="flex items-start gap-2 text-sm font-normal"><input type="checkbox" required />I have submitted this application myself.</label>
            <SubmitButton>Record manual application</SubmitButton>
          </form>
        </>}
        <Link href="/resumes" className="block text-sm">Manage your default resume</Link>
      </aside>
    </div>
  </div>;
}
