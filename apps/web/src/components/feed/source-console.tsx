"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import type { IngestionRun, RegisteredSource } from "@/lib/job-types";
import { formatRelativeDate, providerLabel } from "@/lib/format";

export function SourceConsole({ sources, runs }: { sources: RegisteredSource[]; runs: IngestionRun[] }) {
  const router = useRouter();
  const [token, setToken] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const active = runs.some((run) => ["QUEUED", "RUNNING"].includes(run.status));
  useEffect(() => {
    if (!active) return;
    const timer = setInterval(() => router.refresh(), 5000);
    return () => clearInterval(timer);
  }, [active, router]);

  async function mutate(path: string, method: string, body?: object) {
    setBusy(true);
    setMessage("");
    try {
      const response = await fetch(`/api/ingestion/${path}`, {
        method, headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: body ? JSON.stringify(body) : undefined,
      });
      const data = await response.json();
      if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail));
      setMessage(path.endsWith("/sync") ? `Run ${data.id}: ${data.status}. ${data.dispatched ? "Sent to worker." : "Waiting for queue dispatch."}` : "Source saved.");
      router.refresh();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "The operation failed.");
    } finally { setBusy(false); }
  }

  return <div className="source-console">
    <section className="source-card">
      <h2>Manage sources</h2>
      <label className="source-field">Administrator API token
        <input className="feed-input" type="password" autoComplete="off" value={token}
          onChange={(e) => setToken(e.target.value)} placeholder="Required to add, update, or sync sources" />
      </label>
      <p className="feed-filter-hint">The token stays in this page’s memory. Source reads use your self-hosted server configuration.</p>
      <p role="status" aria-live="polite">{message}</p>
      <button className="feed-btn" type="button" onClick={() => router.refresh()}>Refresh status</button>
    </section>
    <section className="source-card">
      <h2>Add a company board</h2>
      <form className="source-form" onSubmit={(event) => {
        event.preventDefault();
        const data = new FormData(event.currentTarget);
        const payload = Object.fromEntries(data.entries());
        void mutate("sources", "POST", {
          company_name: payload.company_name,
          website: payload.website || null,
          career_url: payload.career_url || null,
          provider: payload.provider,
          board_id: payload.board_id || null,
          access_policy: payload.access_policy,
          permission_notes: payload.permission_notes || null,
        });
      }}>
        <label className="source-field">Company<input className="feed-input" name="company_name" required maxLength={300} /></label>
        <label className="source-field">Company website<input className="feed-input" name="website" type="url" placeholder="https://example.com" /></label>
        <label className="source-field">Career URL<input className="feed-input" name="career_url" type="url" placeholder="https://jobs.ashbyhq.com/company" /></label>
        <label className="source-field">Provider<select className="feed-select" name="provider" defaultValue="auto">
          {["auto", "greenhouse", "lever", "ashby", "smartrecruiters", "career_page", "feed"].map((v) => <option key={v} value={v}>{providerLabel(v)}</option>)}
        </select></label>
        <label className="source-field">Board identifier (optional with URL)<input className="feed-input" name="board_id" maxLength={200} /></label>
        <label className="source-field">Access policy<select className="feed-select" name="access_policy" defaultValue="pending">
          <option value="pending">Pending review</option><option value="public_api">Documented public ATS API</option>
          <option value="permitted">Explicitly permitted career page or feed</option>
        </select></label>
        <label className="source-field">Permission notes<input className="feed-input" name="permission_notes" maxLength={4000} /></label>
        <button className="feed-btn" disabled={busy || !token}>Register source</button>
      </form>
    </section>
    <section className="source-card">
      <h2>Registered sources</h2>
      {sources.length === 0 && <p>No sources yet. Add a company board above.</p>}
      <div className="source-table-wrap"><table className="source-table">
        <thead><tr><th>Company / board</th><th>Provider</th><th>Health / access</th><th>Last successful sync</th><th>Jobs</th><th>Actions</th></tr></thead>
        <tbody>{sources.map((source) => <tr key={source.id}>
          <td>{source.company_name}<small>{source.board_id}</small></td>
          <td>{providerLabel(source.provider)}</td>
          <td>{source.enabled ? source.health : "disabled"}<small>{source.access_policy} · {source.failure_count} failures</small></td>
          <td>{source.last_success_at ? formatRelativeDate(source.last_success_at) : "Never"}</td>
          <td>{source.job_count}</td>
          <td><button className="feed-form-btn" disabled={busy || !token || !source.enabled || !!source.active_run_id}
            onClick={() => void mutate(`sources/${source.id}/sync`, "POST")}>{source.active_run_id ? "Queued / running" : "Sync"}</button>{" "}
            <button className="feed-text-btn" disabled={busy || !token} onClick={() => void mutate(`sources/${source.id}`, "PATCH", { enabled: !source.enabled })}>{source.enabled ? "Disable" : "Enable"}</button>{" "}
            {source.access_policy === "pending" && <button className="feed-text-btn" disabled={busy || !token || !["greenhouse", "lever", "ashby", "smartrecruiters"].includes(source.provider)}
              onClick={() => void mutate(`sources/${source.id}`, "PATCH", { access_policy: "public_api" })}>Approve public API</button>}
          </td>
        </tr>)}</tbody>
      </table></div>
    </section>
    <section className="source-card">
      <h2>Recent ingestion runs</h2>
      <p className="feed-filter-hint">Queued and running operations refresh every five seconds. A completed status comes from the backend.</p>
      <div className="source-table-wrap"><table className="source-table">
        <thead><tr><th>Run / source</th><th>Status</th><th>Fetched</th><th>Inserted</th><th>Updated</th><th>Deduplicated</th><th>Errors</th></tr></thead>
        <tbody>{runs.map((run) => <tr key={run.id}>
          <td title={run.id}>{formatRelativeDate(run.started_at)}<small>{sources.find((s) => s.id === run.source_id)?.company_name ?? run.source_id}</small></td>
          <td>{run.status}</td><td>{run.fetched}</td><td>{run.inserted}</td><td>{run.updated}</td><td>{run.deduplicated}</td>
          <td>{run.failed ? run.errors.map((e) => e.code).join(", ") : "—"}</td>
        </tr>)}</tbody>
      </table></div>
    </section>
  </div>;
}
