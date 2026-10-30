import Link from "next/link";
import { apiGet, getProfile } from "@/lib/api";
import type { Company, Resume, Settings, Stats, ApplicationsPage } from "@/lib/types";
import { DiscoverForm } from "@/components/discover-form";
import { dateTime, label } from "@/lib/format";

export default async function Dashboard() {
  const [profile, stats, settings, companies, resumes, applications] = await Promise.all([
    getProfile(), apiGet<Stats>("/api/v1/dashboard/stats"), apiGet<Settings>("/api/v1/settings"),
    apiGet<Company[]>("/api/v1/companies"), apiGet<Resume[]>("/api/v1/resumes"), apiGet<ApplicationsPage>("/api/v1/applications?limit=1"),
  ]);
  const defaultResume = resumes.find((resume) => resume.is_default);
  const sources = companies.filter((source) => source.enabled).length;
  return <div className="space-y-7">
    <div><p className="eyebrow">Your job search</p>
      <h1 className="text-3xl font-semibold">{profile ? `Welcome, ${profile.full_name}.` : "Your next opportunity starts here."}</h1>
      <p className="mt-3 text-slate-600">Discover opportunities, review the evidence, and track your next steps.</p>
    </div>
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      {[["Open jobs", stats.active_jobs], ["Eligible jobs", stats.eligible_jobs], ["Matches 80+", stats.strong_matches], ["Applications tracked", applications.total]].map(([name, value]) =>
        <section className="panel" key={name}><h2 className="text-sm text-slate-500">{name}</h2><p className="mt-2 text-3xl font-semibold">{value}</p></section>)}
    </div>
    <section className="panel space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-4"><div><h2 className="text-xl font-semibold">Find your next role</h2>
        <p className="mt-2 text-slate-600">{sources} enabled career boards · {settings.ai_configured ? "Gemini matching available" : "Deterministic matching available"}</p></div>
        <Link href="/jobs" className="font-semibold">Browse jobs →</Link>
      </div>
      {!profile?.facts.length ? <p>Add <Link href="/profile">verified profile facts</Link> before discovering jobs.</p> : !sources ? <p>Add a company career board in <Link href="/settings">Settings</Link> to begin discovery.</p> : <DiscoverForm settings={settings} />}
      {stats.latest_run && <p className="text-sm text-slate-500">Last run: <Link href={`/runs/${stats.latest_run.id}`}>{label(stats.latest_run.status)}</Link> · {dateTime(stats.latest_run.started_at)}</p>}
    </section>
    <div className="grid gap-5 md:grid-cols-2">
      <section className="panel space-y-3"><h2 className="text-xl font-semibold">Your application resume</h2>
        <p className="text-slate-600">{defaultResume ? `Default: ${defaultResume.original_filename} · version ${defaultResume.version}` : "Upload your resume once and keep a default ready for future applications."}</p>
        <Link href="/resumes" className="font-semibold">Manage resumes →</Link>
      </section>
      <section className="panel space-y-3"><h2 className="text-xl font-semibold">Verified profile</h2>
        <p className="text-slate-600">{profile?.facts.length ?? 0} verified facts · India and India-eligible remote roles · 0–2 years</p>
        <Link href="/profile" className="font-semibold">Review your facts →</Link>
      </section>
    </div>
    <p className="text-sm text-slate-500">Applications are submitted manually on the original career site. JobPilot stores your resume unchanged and lets you track your application afterward.</p>
  </div>;
}
