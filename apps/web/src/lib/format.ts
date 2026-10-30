import type { JobSummary } from "@/lib/job-types";
import { PROVIDER_LABELS, WORK_MODE_LABELS } from "@/lib/feed-filters";

const number = new Intl.NumberFormat("en", { maximumFractionDigits: 0 });
const compact = new Intl.NumberFormat("en", {
  notation: "compact",
  maximumFractionDigits: 1,
});
const dateShort = new Intl.DateTimeFormat("en-IN", {
  day: "numeric",
  month: "short",
  year: "numeric",
  timeZone: "Asia/Kolkata",
});
const dateTimeShort = new Intl.DateTimeFormat("en-IN", {
  day: "numeric",
  month: "short",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  timeZone: "Asia/Kolkata",
});
const relative = new Intl.RelativeTimeFormat("en", { numeric: "auto" });

export function formatCount(value: number): string {
  return number.format(value);
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "—" : dateShort.format(date);
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "—" : dateTimeShort.format(date);
}

export function formatRelativeDate(value: string | null | undefined): string {
  if (!value) return "date unknown";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "date unknown";

  const seconds = Math.round((date.getTime() - Date.now()) / 1000);
  const absolute = Math.abs(seconds);
  if (absolute < 60) return "just now";
  if (absolute < 3600) return relative.format(Math.round(seconds / 60), "minute");
  if (absolute < 86400) return relative.format(Math.round(seconds / 3600), "hour");
  if (absolute < 60 * 60 * 24 * 30) {
    return relative.format(Math.round(seconds / 86400), "day");
  }
  return dateShort.format(date);
}

export function providerLabel(provider: string): string {
  return PROVIDER_LABELS[provider] ?? provider;
}

export function workModeLabel(mode: string): string {
  return WORK_MODE_LABELS[mode] ?? humanize(mode);
}

export function humanize(value: string): string {
  return value
    .replaceAll("_", " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

export function formatSalary(job: JobSummary): string | null {
  if (job.salary_text) return job.salary_text;
  if (job.salary_min == null && job.salary_max == null) return null;

  const currency = job.salary_currency ?? "";
  const format = (value: number) => {
    if (!currency || currency.length !== 3) return number.format(value);
    try {
      return new Intl.NumberFormat("en", {
        style: "currency",
        currency,
        currencyDisplay: "narrowSymbol",
        notation: value >= 1000 ? "compact" : "standard",
        maximumFractionDigits: value >= 1000 ? 1 : 0,
      }).format(value);
    } catch {
      return `${currency} ${compact.format(value)}`;
    }
  };

  const range =
    job.salary_min != null && job.salary_max != null
      ? `${format(job.salary_min)}–${format(job.salary_max)}`
      : format((job.salary_min ?? job.salary_max) as number);

  const period = job.salary_period
    ? `/${job.salary_period.replace("yearly", "yr").replace("monthly", "mo").replace("hourly", "hr").replace("weekly", "wk").replace("daily", "day")}`
    : "";

  return `${range}${period}`;
}

export function sourceHost(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

export function listingTypeLabel(type: string): string {
  return type === "SEARCH_RESULT" ? "Search result page" : "Job posting";
}
