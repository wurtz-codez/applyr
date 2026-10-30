import Link from "next/link";
import { notFound } from "next/navigation";
import { apiFetch, apiGet } from "@/lib/api";
import type { Run, Settings } from "@/lib/types";
import { dateTime, label } from "@/lib/format";
import { AutoRefresh } from "@/components/auto-refresh";
import { RunResults } from "@/components/run-results";
import { DiscoverForm } from "@/components/discover-form";

export default async function RunPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  if (!/^[0-9a-f-]{36}$/i.test(id)) notFound();
  const response = await apiFetch(`/api/v1/runs/${id}`);
  if (response.status === 404 || response.status === 422) notFound();
  if (!response.ok) throw new Error("Could not load run");
  const run: Run = await response.json();
  const settings = await apiGet<Settings>("/api/v1/settings");
  const active = ["QUEUED", "RUNNING"].includes(run.status);
  return <div className="space-y-6"><Link href="/runs" className="text-sm">← Run history</Link><div className="flex flex-wrap justify-between gap-4"><div><p className="eyebrow">Discovery run</p><h1 className="text-3xl font-semibold">{label(run.status)}</h1><p className="mt-3 text-sm text-slate-500">Started {dateTime(run.started_at)}{run.finished_at && ` · Finished ${dateTime(run.finished_at)}`}</p></div>{!active && <DiscoverForm settings={settings} />}</div>
    <AutoRefresh active={active} />
    {run.error_code && <p role="alert" className="rounded-lg bg-amber-50 p-4 text-amber-900">{run.status === "INTERRUPTED" ? "This scan was interrupted. You can start a new scan." : "Some or all of this scan could not finish. Review the source results and retry."}</p>}
    <section className="panel"><RunResults run={run} /></section>
    <Link href="/jobs" className="font-semibold">Review discovered jobs →</Link>
  </div>;
}
