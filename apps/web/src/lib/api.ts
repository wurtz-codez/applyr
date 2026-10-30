import "server-only";
import { readFile } from "node:fs/promises";
import path from "node:path";
import type {
  Dashboard,
  Facets,
  FeedFilters,
  FeedType,
  JobDetail,
  JobsPage,
} from "@/lib/job-types";
import { filtersToApiParams } from "@/lib/feed-filters";

export const apiBase = process.env.API_BASE_URL ?? "http://127.0.0.1:8000";

export class ApiError extends Error {
  status: number;

  constructor(message: string, status = 0) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

function readEnvValue(contents: string, key: string): string {
  for (const line of contents.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) continue;
    const match = trimmed.match(/^(?:export\s+)?([A-Z0-9_]+)\s*=\s*(.*)$/);
    if (!match || match[1] !== key) continue;
    let value = match[2].trim();
    if (
      (value.startsWith('"') && value.endsWith('"')) ||
      (value.startsWith("'") && value.endsWith("'"))
    ) {
      value = value.slice(1, -1);
    }
    return value;
  }
  return "";
}

let tokenPromise: Promise<string> | undefined;

async function getApiToken(): Promise<string> {
  if (process.env.API_TOKEN) return process.env.API_TOKEN;
  if (!tokenPromise) {
    tokenPromise = (async () => {
      const candidates = [
        path.resolve(process.cwd(), "../../.env"),
        path.resolve(process.cwd(), ".env"),
        path.resolve(process.cwd(), "../.env"),
      ];
      for (const candidate of candidates) {
        try {
          const contents = await readFile(/* turbopackIgnore: true */ candidate, "utf8");
          const token = readEnvValue(contents, "API_TOKEN");
          if (token) return token;
        } catch {
          // Try the next location; the API may be configured via real env vars.
        }
      }
      throw new ApiError(
        "API_TOKEN was not found. Add it to the root .env file or set it in the web environment.",
        401,
      );
    })().catch((error) => {
      tokenPromise = undefined;
      throw error;
    });
  }
  return tokenPromise;
}

async function apiGet<T>(pathname: string, params?: URLSearchParams): Promise<T> {
  const token = await getApiToken();
  const url = new URL(`${apiBase}${pathname}`);
  params?.forEach((value, key) => url.searchParams.append(key, value));

  let response: Response;
  try {
    response = await fetch(url, {
      headers: {
        Accept: "application/json",
        Authorization: `Bearer ${token}`,
      },
      cache: "no-store",
      signal: AbortSignal.timeout(20000),
    });
  } catch {
    throw new ApiError(
      "The job API is not reachable. Start the FastAPI service and refresh.",
      0,
    );
  }

  if (response.status === 401) {
    throw new ApiError("The local API rejected the configured API_TOKEN.", 401);
  }
  if (response.status === 404) {
    throw new ApiError("The requested listing could not be found.", 404);
  }
  if (!response.ok) {
    throw new ApiError(`The job API returned status ${response.status}.`, response.status);
  }

  return (await response.json()) as T;
}

export function getJobs(filters: FeedFilters): Promise<JobsPage> {
  return apiGet<JobsPage>("/api/v1/jobs", filtersToApiParams(filters));
}

export function getFacets(type: FeedType = "jobs"): Promise<Facets> {
  // Keep every option available while respecting the chosen listing type.
  const params = new URLSearchParams();
  if (type === "jobs") params.set("listing_type", "JOB_POSTING");
  if (type === "search") params.set("listing_type", "SEARCH_RESULT");
  return apiGet<Facets>("/api/v1/jobs/filters", params);
}

export function getDashboard(filters: FeedFilters): Promise<Dashboard> {
  return apiGet<Dashboard>("/api/v1/dashboard", filtersToApiParams(filters));
}

export function getJob(id: string): Promise<JobDetail> {
  return apiGet<JobDetail>(`/api/v1/jobs/${encodeURIComponent(id)}`);
}
