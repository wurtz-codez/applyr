export type WorkMode = "REMOTE" | "HYBRID" | "ONSITE" | "UNKNOWN";
export type ListingType = "JOB_POSTING" | "SEARCH_RESULT";
export type SortKey = "india" | "newest" | "oldest" | "title" | "match";
export type FeedType = "jobs" | "all" | "search";

export type SourceRef = {
  provider: string;
  source_url: string;
  last_seen_at: string;
};

export type JobSummary = {
  apply_url: string | null;
  original_job_url: string | null;
  normalized_json: { job_url?: string; apply_url?: string | null } | null;
  match_score: number | null;
  match_reasons: string[];
  india_status: "CONFIRMED" | "NOT_ELIGIBLE" | "UNCERTAIN";
  eligibility_reason: string | null;
  eligibility_evaluated_at: string | null;
  india_eligible: boolean | null;
  experience_min: number | null;
  experience_max: number | null;
  status: string;
  id: string;
  canonical_url: string;
  title: string;
  company: string | null;
  location: string | null;
  description_excerpt: string;
  work_mode: WorkMode;
  employment_type: string | null;
  experience_level: string | null;
  salary_min: number | null;
  salary_max: number | null;
  salary_currency: string | null;
  salary_period: string | null;
  salary_text: string | null;
  listing_type: ListingType;
  enrichment_status: string;
  primary_source: string;
  published_at: string | null;
  first_seen_at: string;
  last_seen_at: string;
  tags: string[];
  sources: SourceRef[];
};

export type JobDetail = JobSummary & {
  description: string;
};

export type JobsPage = {
  items: JobSummary[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
};

export type FacetValue = {
  value: string;
  count: number;
};

export type Facets = {
  company: FacetValue[];
  location: FacetValue[];
  work_mode: FacetValue[];
  employment_type: FacetValue[];
  experience_level: FacetValue[];
  salary_currency: FacetValue[];
  salary_period: FacetValue[];
  listing_type: FacetValue[];
  tags: FacetValue[];
  sources: FacetValue[];
};

export type RunResult = {
  provider: string;
  status: string;
  fetched: number;
  new: number;
  updated: number;
  unchanged: number;
  invalid: number;
  partial: boolean;
  enriched: number;
  error_code: string | null;
  next_refresh_at: string | null;
};

export type DiscoveryRun = {
  id: string;
  status: string;
  query: string;
  providers: string[];
  results: RunResult[];
  started_at: string;
  finished_at: string | null;
  error_code: string | null;
};

export type Dashboard = {
  last_ingestion_attempt_at: string | null;
  total: number;
  job_postings: number;
  search_results: number;
  remote: number;
  new_today: number;
  companies: number;
  last_run: DiscoveryRun | null;
};

export type FeedFilters = {
  matchProfile: string;
  indiaEligible: string;
  maxExperience: string;
  includeUncertain: boolean;
  q: string;
  company: string;
  location: string;
  workMode: string;
  employmentType: string;
  experienceLevel: string;
  sources: string[];
  tags: string[];
  postedWithin: string;
  type: FeedType;
  sort: SortKey;
  page: number;
  minSalary: string;
  currency: string;
  salaryPeriod: string;
};

export type RegisteredSource = {
  id: string;
  company_name: string;
  career_url: string | null;
  provider: string;
  board_id: string;
  enabled: boolean;
  access_policy: string;
  health: string;
  last_success_at: string | null;
  last_attempt_at: string | null;
  failure_count: number;
  job_count: number;
  active_run_id: string | null;
};

export type IngestionRun = {
  id: string;
  source_id: string;
  status: string;
  started_at: string;
  finished_at: string | null;
  fetched: number;
  inserted: number;
  updated: number;
  deduplicated: number;
  failed: number;
  errors: { code: string }[];
};

export type RegistryPage<T> = {
  items: T[];
  page: number;
  page_size: number;
  total: number;
};
