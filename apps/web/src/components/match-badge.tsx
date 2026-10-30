import { label } from "@/lib/format";
import type { Match } from "@/lib/types";

export function MatchBadge({ match }: { match: Match | null }) {
  const status = match?.eligibility_status;
  const tone = status === "ELIGIBLE" ? "bg-emerald-50 text-emerald-800" : status === "INELIGIBLE" ? "bg-slate-100 text-slate-600" : "bg-amber-50 text-amber-900";
  return <span className={`inline-flex rounded-full px-3 py-1 text-xs font-semibold ${tone}`}>
    {status ? label(status) : "Needs matching"}
  </span>;
}
