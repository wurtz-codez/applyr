import type {
  FacetValue,
  FeedFilters,
  FeedType,
  SortKey,
} from "@/lib/job-types";

export const PAGE_SIZE = 24;

export const PROVIDERS = ["himalayas", "arbeitnow", "remotive", "jobicy", "tavily", "greenhouse", "lever", "ashby", "smartrecruiters", "career_page", "feed", "browser", "jobspy"] as const;
export const WORK_MODES = ["REMOTE", "HYBRID", "ONSITE", "UNKNOWN"] as const;
export const SORTS: SortKey[] = ["india", "newest", "oldest", "title", "match"];
export const CURRENCIES = [
  "USD",
  "EUR",
  "GBP",
  "CAD",
  "AUD",
  "INR",
  "SEK",
  "PLN",
  "CZK",
  "ILS",
] as const;
export const SALARY_PERIODS = [
  "yearly",
  "monthly",
  "weekly",
  "daily",
  "hourly",
] as const;

export const PROVIDER_LABELS: Record<string, string> = {
  himalayas: "Himalayas",
  arbeitnow: "Arbeitnow",
  remotive: "Remotive",
  jobicy: "Jobicy",
  tavily: "Tavily",
  greenhouse: "Greenhouse",
  lever: "Lever",
  ashby: "Ashby",
  smartrecruiters: "SmartRecruiters",
  career_page: "Company career page",
  feed: "Authorized feed",
  browser: "Rendered career page",
  jobspy: "Authorized JobSpy",
  auto: "Detect from URL",
};

export const WORK_MODE_LABELS: Record<string, string> = {
  REMOTE: "Remote",
  HYBRID: "Hybrid",
  ONSITE: "On-site",
  UNKNOWN: "Not specified",
};

export const POSTED_OPTIONS = [
  { value: "", label: "Any time" },
  { value: "1", label: "24 hours" },
  { value: "7", label: "7 days" },
  { value: "30", label: "30 days" },
  { value: "90", label: "90 days" },
] as const;

export const SORT_OPTIONS: { value: SortKey; label: string }[] = [
  { value: "india", label: "India · early career" },
  { value: "newest", label: "Newest first" },
  { value: "oldest", label: "Oldest first" },
  { value: "title", label: "Title A–Z" },
  { value: "match", label: "Match score" },
];

type ParamInput =
  | URLSearchParams
  | Record<string, string | string[] | undefined>;

function isSearchParams(input: ParamInput): input is URLSearchParams {
  return (
    typeof (input as URLSearchParams).get === "function" &&
    typeof (input as URLSearchParams).getAll === "function"
  );
}

function clean(value: string | null | undefined, max: number): string {
  return (value ?? "").trim().slice(0, max);
}

function one(input: ParamInput, key: string): string {
  return isSearchParams(input) ? input.get(key) ?? "" : clean(
    Array.isArray(input[key]) ? input[key]?.[0] : input[key],
    2000,
  );
}

function many(input: ParamInput, key: string): string[] {
  return isSearchParams(input) ? input.getAll(key) : (
    Array.isArray(input[key]) ? (input[key] as string[]) : input[key] ? [input[key] as string] : []
  );
}

function isOneOf<T extends readonly string[]>(value: string, values: T): value is T[number] {
  return values.includes(value);
}

export function parseFeedFilters(input: ParamInput): FeedFilters {
  const typeValue = one(input, "type");
  const type: FeedType =
    typeValue === "all" ? "all" : typeValue === "search" ? "search" : "jobs";

  const sortValue = one(input, "sort");
  const profileRaw = one(input, "match_profile");
  const matchProfile = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(profileRaw) ? profileRaw : "";
  const sort: SortKey = isOneOf(sortValue, SORTS) && (sortValue !== "match" || matchProfile) ? sortValue : "india";

  const workMode = one(input, "work_mode").toUpperCase();
  const posted = one(input, "posted_within_days");
  const page = Number.parseInt(one(input, "page"), 10);
  const currency = one(input, "currency").toUpperCase();
  const salaryPeriod = one(input, "salary_period").toLowerCase();
  const minSalaryRaw = one(input, "min_salary");
  const minSalary =
    /^\d{1,9}(\.\d{1,2})?$/.test(minSalaryRaw) && Number(minSalaryRaw) > 0
      ? minSalaryRaw
      : "";

  return {
    matchProfile,
    indiaEligible: one(input, "india_eligible") === "true" ? "true" : "",
    maxExperience: one(input, "experience_max") === "2" ? "2" : "",
    includeUncertain: one(input, "include_uncertain") !== "false",
    q: clean(one(input, "q"), 200),
    company: clean(one(input, "company"), 300),
    location: clean(one(input, "location"), 200),
    workMode: isOneOf(workMode, WORK_MODES) ? workMode : "",
    employmentType: clean(one(input, "employment_type"), 80),
    experienceLevel: clean(one(input, "experience_level"), 80),
    sources: [...new Set(many(input, "source").filter((value) => isOneOf(value, PROVIDERS)))],
    tags: [...new Set(many(input, "tag").map((value) => clean(value, 100)).filter(Boolean))].slice(
      0,
      10,
    ),
    postedWithin: isOneOf(posted, ["1", "7", "30", "90"] as const) ? posted : "",
    type,
    sort,
    page: Number.isFinite(page) && page > 0 ? Math.min(page, 100000) : 1,
    minSalary,
    currency: isOneOf(currency, CURRENCIES) ? currency : "USD",
    salaryPeriod: isOneOf(salaryPeriod, SALARY_PERIODS) ? salaryPeriod : "yearly",
  };
}

export function filtersToApiParams(filters: FeedFilters): URLSearchParams {
  const params = new URLSearchParams();
  if (filters.matchProfile) params.set("match_profile", filters.matchProfile);
  if (filters.indiaEligible) params.set("india_eligible", filters.indiaEligible);
  if (filters.maxExperience) params.set("experience_max", filters.maxExperience);
  params.set("include_uncertain", String(filters.includeUncertain));
  params.set("status", "active");
  params.set("page", String(filters.page));
  params.set("page_size", String(PAGE_SIZE));
  params.set("sort", filters.sort);

  if (filters.q) params.set("q", filters.q);
  if (filters.company) params.set("company", filters.company);
  if (filters.location) params.set("location", filters.location);
  if (filters.workMode) params.set("work_mode", filters.workMode);
  if (filters.employmentType) params.set("employment_type", filters.employmentType);
  if (filters.experienceLevel) params.set("experience_level", filters.experienceLevel);
  if (filters.type === "jobs") params.set("listing_type", "JOB_POSTING");
  if (filters.type === "search") params.set("listing_type", "SEARCH_RESULT");
  if (filters.postedWithin) params.set("posted_within_days", filters.postedWithin);

  filters.sources.forEach((source) => params.append("source", source));
  filters.tags.forEach((tag) => params.append("tag", tag));

  const salary = Number(filters.minSalary);
  if (Number.isFinite(salary) && salary > 0) {
    params.set("min_salary", String(salary));
    params.set("currency", filters.currency);
    params.set("salary_period", filters.salaryPeriod);
  }

  return params;
}

export function filtersToSearchParams(filters: FeedFilters): URLSearchParams {
  const params = new URLSearchParams();
  if (filters.matchProfile) params.set("match_profile", filters.matchProfile);
  if (filters.indiaEligible) params.set("india_eligible", filters.indiaEligible);
  if (filters.maxExperience) params.set("experience_max", filters.maxExperience);
  if (!filters.includeUncertain) params.set("include_uncertain", "false");
  if (filters.q) params.set("q", filters.q);
  if (filters.company) params.set("company", filters.company);
  if (filters.location) params.set("location", filters.location);
  if (filters.workMode) params.set("work_mode", filters.workMode);
  if (filters.employmentType) params.set("employment_type", filters.employmentType);
  if (filters.experienceLevel) params.set("experience_level", filters.experienceLevel);
  if (filters.type !== "jobs") params.set("type", filters.type);
  if (filters.postedWithin) params.set("posted_within_days", filters.postedWithin);
  if (filters.sort !== "india") params.set("sort", filters.sort);
  if (filters.page > 1) params.set("page", String(filters.page));

  filters.sources.forEach((source) => params.append("source", source));
  filters.tags.forEach((tag) => params.append("tag", tag));

  if (filters.minSalary) {
    params.set("min_salary", filters.minSalary);
    params.set("currency", filters.currency);
    params.set("salary_period", filters.salaryPeriod);
  }

  return params;
}

export function feedHref(filters: FeedFilters): string {
  const query = filtersToSearchParams(filters).toString();
  return query ? `/jobs?${query}` : "/jobs";
}

export type ActiveChip = {
  key: string;
  value?: string;
  label: string;
};

export function activeFilterChips(filters: FeedFilters): ActiveChip[] {
  const chips: ActiveChip[] = [];
  if (filters.matchProfile) chips.push({ key: "match_profile", label: "Profile matches" });
  if (filters.indiaEligible) chips.push({ key: "india_eligible", label: "India location relevant" });
  if (filters.maxExperience) chips.push({ key: "experience_max", label: "Up to 2 years required" });
  if (!filters.includeUncertain) chips.push({ key: "include_uncertain", label: "Confirmed only" });
  if (filters.q) chips.push({ key: "q", label: `“${filters.q}”` });
  if (filters.company) chips.push({ key: "company", label: filters.company });
  if (filters.location) chips.push({ key: "location", label: filters.location });
  if (filters.workMode) {
    chips.push({
      key: "work_mode",
      label: WORK_MODE_LABELS[filters.workMode] ?? filters.workMode,
    });
  }
  if (filters.employmentType) {
    chips.push({ key: "employment_type", label: filters.employmentType });
  }
  if (filters.experienceLevel) {
    chips.push({ key: "experience_level", label: filters.experienceLevel });
  }
  filters.sources.forEach((source) =>
    chips.push({ key: "source", value: source, label: PROVIDER_LABELS[source] ?? source }),
  );
  filters.tags.forEach((tag) => chips.push({ key: "tag", value: tag, label: `#${tag}` }));
  if (filters.postedWithin) {
    const option = POSTED_OPTIONS.find((item) => item.value === filters.postedWithin);
    chips.push({ key: "posted_within_days", label: `Posted ${option?.label ?? ""}` });
  }
  if (Number(filters.minSalary) > 0) {
    chips.push({
      key: "min_salary",
      label: `≥ ${filters.currency} ${filters.minSalary}/${filters.salaryPeriod}`,
    });
  }
  if (filters.type === "all") {
    chips.push({ key: "type", label: "Including search pages" });
  }
  if (filters.type === "search") {
    chips.push({ key: "type", label: "Search pages only" });
  }
  return chips;
}

export function activeFilterCount(filters: FeedFilters): number {
  return activeFilterChips(filters).length;
}

export function facetedValues(
  values: FacetValue[],
  { limit, dedupe = false }: { limit?: number; dedupe?: boolean } = {},
): FacetValue[] {
  let next = values.filter((item) => item.value.trim());
  if (dedupe) {
    const merged = new Map<string, FacetValue>();
    for (const item of next) {
      const key = item.value.trim().toLowerCase();
      const existing = merged.get(key);
      if (existing) existing.count += item.count;
      else merged.set(key, { value: item.value.trim(), count: item.count });
    }
    next = [...merged.values()].sort((a, b) => b.count - a.count);
  }
  return typeof limit === "number" ? next.slice(0, limit) : next;
}
