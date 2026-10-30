import Link from "next/link";
import { apiGet } from "@/lib/api";
import type { ApplicationsPage } from "@/lib/types";
import { trackApplication } from "@/app/mvp-actions";
import { SubmitButton } from "@/components/submit-button";
import { Notice } from "@/components/notice";
import { dateTime, label } from "@/lib/format";

const statuses = ["APPLIED", "INTERVIEW", "OFFER", "REJECTED", "WITHDRAWN"];

export default async function Applications({ searchParams }: { searchParams: Promise<{ status?: string; offset?: string; error?: string; success?: string }> }) {
  const params = await searchParams;
  const offset = Math.max(0, Math.floor(Number(params.offset) || 0));
  const query = new URLSearchParams({ offset: String(offset) });
  if (statuses.includes(params.status ?? "")) query.set("status", params.status!);
  const data = await apiGet<ApplicationsPage>(`/api/v1/applications?${query}`);
  function href(next: number) { const q = new URLSearchParams(query); q.set("offset", String(next)); return `/applications?${q}`; }
  return <div className="space-y-6"><div><p className="eyebrow">Your application history</p><h1 className="text-3xl font-semibold">Applications</h1><p className="mt-3 text-slate-600">Track applications you submitted yourself, update their status, and keep notes.</p></div><Notice error={params.error} success={params.success} />
    <form className="flex flex-wrap items-end gap-3" method="GET"><div><label htmlFor="status">Status</label><select id="status" name="status" defaultValue={params.status ?? ""} className="mt-2"><option value="">All applications</option>{statuses.map((status) => <option key={status} value={status}>{label(status)}</option>)}</select></div><button type="submit">Filter</button><p className="p-3 text-sm text-slate-500">{data.total} tracked</p></form>
    {!data.items.length ? <section className="panel space-y-3"><h2 className="text-xl font-semibold">No applications in this view yet.</h2><p className="text-slate-600">After applying on a company’s career site, open the job in JobPilot and choose “Record manual application”.</p><Link href="/jobs">Browse discovered jobs →</Link></section> : <div className="space-y-4">{data.items.map((application) => <article className="panel space-y-4" key={application.id}>
      <div className="flex flex-wrap justify-between gap-3"><div><p className="text-sm text-emerald-800">{application.company}</p><h2 className="mt-2 text-xl font-semibold"><Link href={`/jobs/${application.job_id}`}>{application.title}</Link></h2></div><span className="h-fit rounded-full bg-slate-100 px-3 py-1 text-sm">{label(application.status)}</span></div>
      <p className="text-sm text-slate-500">Recorded {dateTime(application.applied_at)} · Updated {dateTime(application.updated_at)} · {application.resume_version ? `Resume version ${application.resume_version}` : "No resume attached"}</p>
      <form action={trackApplication} className="grid items-end gap-4 sm:grid-cols-[180px_1fr_auto]"><input type="hidden" name="job_id" value={application.job_id} /><div><label htmlFor={`status-${application.id}`}>Application status</label><select id={`status-${application.id}`} name="status" defaultValue={application.status} className="mt-2">{statuses.map((status) => <option key={status} value={status}>{label(status)}</option>)}</select></div><div><label htmlFor={`notes-${application.id}`}>Notes</label><textarea id={`notes-${application.id}`} name="notes" defaultValue={application.notes} rows={2} maxLength={4000} className="mt-2" /></div><SubmitButton>Save update</SubmitButton></form>
      <div className="flex flex-wrap gap-5 text-sm"><a href={application.source_url} target="_blank" rel="noopener noreferrer">Open original listing ↗</a>{application.resume_id && <a href={`/resumes/${application.resume_id}/download`}>Download recorded resume</a>}</div>
    </article>)}</div>}
    <nav aria-label="Application result pages" className="flex justify-between text-sm">{offset > 0 ? <Link href={href(Math.max(0, offset - data.limit))}>← Previous</Link> : <span />}{offset + data.items.length < data.total && <Link href={href(offset + data.limit)}>Next →</Link>}</nav>
  </div>;
}
