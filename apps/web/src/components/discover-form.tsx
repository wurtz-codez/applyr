import { discoverJobs } from "@/app/mvp-actions";
import { SubmitButton } from "@/components/submit-button";
import type { Settings } from "@/lib/types";

export function DiscoverForm({ settings }: { settings: Settings }) {
  return <form action={discoverJobs} className="flex flex-wrap items-center gap-4">
    {settings.ai_configured && <label className="flex items-center gap-2 text-sm font-normal">
      <input type="checkbox" name="use_ai" defaultChecked />
      Use Gemini (up to {settings.ai_max_jobs_per_run} new analyses per scan)
    </label>}
    <SubmitButton pendingText="Starting discovery…">Discover jobs</SubmitButton>
  </form>;
}
