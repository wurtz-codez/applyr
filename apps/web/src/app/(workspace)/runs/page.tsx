import Link from "next/link";
import { apiGet } from "@/lib/api";
import type { Run } from "@/lib/types";
import { dateTime, label } from "@/lib/format";
import { AutoRefresh } from "@/components/auto-refresh";

export default async function Runs() {
  const runs = await apiGet<Run[]>("/api/v1/runs");
  return <div className="space-y-6"><div><p className="eyebrow">Discovery history</p><h1 className="text-3xl font-semibold">Recent runs</h1><p className="mt-3 text-slate-600">Latest 20 scans, with source counts and visible failures.</p></div>
    <AutoRefresh active={runs.some((run) => ["QUEUED", "RUNNING"].includes(run.status))} />
    {!runs.length ? <section className="panel"><p>No discovery runs yet. Start a scan from <Link href="/jobs">Jobs</Link>.</p></section> : <div className="space-y-3">{runs.map((run) => <article key={run.id} className="panel flex flex-wrap items-center justify-between gap-3"><div><Link href={`/runs/${run.id}`} className="font-semibold">{label(run.status)}</Link><p className="mt-2 text-sm text-slate-500">{dateTime(run.started_at)}</p></div><Link href={`/runs/${run.id}`}>View progress →</Link></article>)}</div>}
  </div>;
}
