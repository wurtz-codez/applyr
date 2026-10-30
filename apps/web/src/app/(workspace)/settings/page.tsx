import { apiGet } from "@/lib/api";
import type { Company, Settings } from "@/lib/types";
import { addCompany, toggleCompany } from "@/app/mvp-actions";
import { SubmitButton } from "@/components/submit-button";
import { Notice } from "@/components/notice";

export default async function SettingsPage({ searchParams }: { searchParams: Promise<{ error?: string; success?: string }> }) {
  const [settings, companies, messages] = await Promise.all([
    apiGet<Settings>("/api/v1/settings"), apiGet<Company[]>("/api/v1/companies"), searchParams,
  ]);
  return <div className="space-y-6"><div><p className="eyebrow">Search configuration</p><h1 className="text-3xl font-semibold">Settings</h1></div>
    <Notice {...messages} />
    <section className="panel space-y-5"><h2 className="text-xl font-semibold">Company career boards</h2>
      <p className="max-w-3xl text-slate-600">Add public Greenhouse boards for companies you want to discover jobs from. Greenhouse lists openings per company, so a board is required to start. You can disable a source at any time.</p>
      <form action={addCompany} className="grid items-end gap-4 sm:grid-cols-[1fr_1fr_auto]">
        <div><label htmlFor="company_name">Company name</label><input id="company_name" name="name" required maxLength={200} className="mt-2" /></div>
        <div><label htmlFor="board_token">Greenhouse board token</label><input id="board_token" name="board_token" required pattern="[a-zA-Z0-9_-]{1,80}" maxLength={80} className="mt-2" placeholder="company-slug" /></div>
        <SubmitButton>Add board</SubmitButton>
      </form>
      <p className="text-sm text-slate-500">For a careers URL such as job-boards.greenhouse.io/company-slug, the board token is company-slug. Up to 20 boards are supported. Fetch errors appear in Runs.</p>
      {!companies.length && <p className="rounded-lg bg-slate-50 p-4 text-sm">No company boards configured yet.</p>}
      <ul className="divide-y divide-slate-100">{companies.map((company) => <li key={company.id} className="flex flex-wrap items-center justify-between gap-3 py-4"><div><p className="font-semibold">{company.name}</p><p className="text-sm text-slate-500">{company.board_token} · {company.enabled ? "Enabled" : "Disabled"}</p></div><form action={toggleCompany}><input type="hidden" name="company_id" value={company.id} /><input type="hidden" name="enabled" value={String(!company.enabled)} /><SubmitButton className="secondary">{company.enabled ? "Disable" : "Enable"}</SubmitButton></form></li>)}</ul>
    </section>
    <div className="grid items-start gap-5 md:grid-cols-2"><section className="panel space-y-4"><h2 className="text-xl font-semibold">Gemini matching</h2>
      <p>{settings.ai_configured ? `Configured · ${settings.llm_model}` : "Not configured · deterministic matching remains available"}</p>
      <p className="text-sm text-slate-600">Gemini receives bounded job text and verified fact statements. Your profile name field, evidence-source fields, and uploaded resume files are excluded. A scan requests at most {settings.ai_max_jobs_per_run} new AI analyses; cached results are reused.</p>
      <details className="text-sm"><summary className="cursor-pointer font-semibold">Configure your local Gemini connection</summary><p className="mt-3">Add these values to the root .env file and restart the API. Select a model available to your Gemini account.</p><pre className="mt-3 overflow-auto rounded-lg bg-slate-50 p-3">{`LLM_PROVIDER=gemini
GEMINI_API_KEY=your_private_key
LLM_MODEL=your_model_id`}</pre><p className="mt-3">Keys stay on the server. Provider errors fall back to rules and appear on the match.</p></details>
    </section>
    <section className="panel space-y-4"><h2 className="text-xl font-semibold">Discovery schedule</h2><p>{settings.discovery_schedule_enabled ? `Configured every ${settings.discovery_interval_hours} hours` : "Manual discovery · automatic scheduling is off"}</p><p className="text-sm text-slate-600">Manual scans work from Jobs or Dashboard. Local automatic discovery is available when enabled; Celery is available for a worker-based setup.</p><details className="text-sm"><summary className="cursor-pointer font-semibold">Configure the local schedule</summary><pre className="mt-3 overflow-auto rounded-lg bg-slate-50 p-3">{`DISCOVERY_EXECUTOR=local
DISCOVERY_SCHEDULE_ENABLED=true
DISCOVERY_INTERVAL_HOURS=6`}</pre><p className="mt-3">Restart the API after changing configuration. The API must remain running for local scheduling.</p></details></section></div>
  </div>;
}
