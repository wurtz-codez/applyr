import { label } from "@/lib/format";
import type { Run } from "@/lib/types";

const errors: Record<string, string> = {
  SOURCE_RATE_LIMITED: "This board has asked us to slow down. Try again later.",
  SOURCE_UNAVAILABLE: "Could not reach this career board. Try again later.",
  INVALID_OR_UNAVAILABLE_SOURCE: "Board unavailable or token invalid. Check the source in Settings.",
  SOURCE_RESPONSE_LIMIT: "The feed exceeded response limits. Other sources can still be processed.",
  INVALID_SOURCE_RESPONSE: "The board returned an unsupported response.",
};

export function RunResults({ run }: { run: Run }) {
  const sources = Array.isArray(run.result_json.sources) ? run.result_json.sources : [];
  return <div className="space-y-4">
    {!sources.length && <p className="text-sm text-slate-500">No completed source results yet.</p>}
    {sources.map((item, i) => {
      const source = item as Record<string, unknown>;
      return <section key={i} className="rounded-xl border border-slate-200 p-5"><div className="flex flex-wrap justify-between gap-3"><h3 className="font-semibold">{String(source.company ?? "Career source")}</h3><p className="text-sm">{label(String(source.status ?? "Waiting"))}</p></div>
        {source.error_code ? <p className="mt-3 text-sm text-red-700">{errors[String(source.error_code)] ?? "This source could not be processed. Please retry."}</p> : <dl className="mt-4 grid grid-cols-3 gap-3 text-sm sm:grid-cols-6">{["fetched", "new", "updated", "unchanged", "closed", "invalid"].map((key) => <div key={key}><dt className="text-slate-500">{label(key)}</dt><dd className="mt-1 font-semibold">{Number(source[key] ?? 0)}</dd></div>)}</dl>}
        {Number(source.invalid ?? 0) > 0 && <p className="mt-3 text-sm text-amber-800">Some listings could not be read. Missing listings were not marked closed.</p>}
      </section>;
    })}
    <p className="text-sm text-slate-500">New Gemini requests: {Number(run.result_json.ai_requests ?? 0)}. Unchanged results are reused.</p>
  </div>;
}
