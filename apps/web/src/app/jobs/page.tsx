import Link from "next/link";
import { redirect } from "next/navigation";
import { ApiError, getDashboard, getFacets, getJobs } from "@/lib/api";
import {
  PAGE_SIZE,
  facetedValues,
  feedHref,
  filtersToSearchParams,
  parseFeedFilters,
} from "@/lib/feed-filters";
import {
  formatCount,
  formatRelativeDate,
  providerLabel,
} from "@/lib/format";
import { FeedFilterPanel } from "@/components/feed/filter-panel";
import { FeedToolbar } from "@/components/feed/toolbar";
import { JobRow } from "@/components/feed/job-row";
import { FeedPagination } from "@/components/feed/pagination";
import { FeedOffline } from "@/components/feed/offline";

export const dynamic = "force-dynamic";

export const metadata = {
  title: "The feed — Applyr",
  description: "Filtered job listings from multiple public sources.",
};

export default async function JobsPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const raw = await searchParams;
  const filters = parseFeedFilters(raw);

  let jobs;
  let facets;
  let dashboard;

  try {
    [jobs, facets, dashboard] = await Promise.all([
      getJobs(filters),
      getFacets(filters.type),
      getDashboard(filters),
    ]);
  } catch (error) {
    const message =
      error instanceof ApiError
        ? error.message
        : "The feed could not be loaded. Check the API and try again.";
    return <FeedOffline message={message} status={error instanceof ApiError ? error.status : 0} />;
  }

  if (jobs.total > 0 && filters.page > jobs.total_pages) {
    redirect(feedHref({ ...filters, page: jobs.total_pages }));
  }

  const workModes = facetedValues(facets.work_mode);
  const employmentTypes = facetedValues(facets.employment_type);
  const experienceLevels = facetedValues(facets.experience_level, { dedupe: true });
  const locations = facetedValues(facets.location, { limit: 6 });
  const tags = facetedValues(facets.tags, { limit: 12 });
  const sources = facetedValues(facets.sources);
  const lastRun = dashboard.last_run;
  const lastRunTime = lastRun ? lastRun.finished_at ?? lastRun.started_at : null;
  const providerNames = sources
    .map((source) => providerLabel(source.value))
    .join(" · ");
  const scope =
    filters.type === "jobs"
      ? "Job postings"
      : filters.type === "search"
        ? "Search result pages"
        : "All listings";
  const returnQuery = filtersToSearchParams(filters).toString();

  return (
    <>
      <section className="feed-hero">
        <div className="feed-hero-copy">
          <p className="feed-tag">[01] — The feed</p>
          <h1>
            Roles, <em>distilled.</em>
          </h1>
          <p className="feed-hero-lede">
            {scope} from {providerNames || "your configured sources"}. Filter
            down to the few worth opening.
          </p>
        </div>
        <div className="feed-hero-count">
          <span>Matching roles</span>
          <strong>{formatCount(jobs.total)}</strong>
          <span className="feed-hero-sync">
            {lastRunTime
              ? `Last scan ${formatRelativeDate(lastRunTime)}`
              : "No scan yet"}{" "}
            · {sources.length} sources
          </span>
        </div>
      </section>

      <div className="feed-stats" aria-label="Feed summary">
        <div className="feed-stat">
          <b>{formatCount(dashboard.remote)}</b>
          <span>Remote</span>
        </div>
        <div className="feed-stat">
          <b>{formatCount(dashboard.companies)}</b>
          <span>Companies</span>
        </div>
        <div className="feed-stat">
          <b>{formatCount(dashboard.new_today)}</b>
          <span>New today</span>
        </div>
        <div className="feed-stat">
          <b>{sources.length}</b>
          <span>Sources</span>
        </div>
      </div>

      <div className="feed-layout">
        <FeedFilterPanel
          workModes={workModes}
          employmentTypes={employmentTypes}
          experienceLevels={experienceLevels}
          locations={locations}
          tags={tags}
          sources={sources}
        />

        <section className="feed-list" id="feed-results" aria-label="Job listings">
          <FeedToolbar total={jobs.total} shown={jobs.items.length} />

          {jobs.items.length > 0 ? (
            <div className="feed-rows">
              {jobs.items.map((job, index) => (
                <JobRow
                  key={job.id}
                  job={job}
                  index={(filters.page - 1) * PAGE_SIZE + index + 1}
                  returnQuery={returnQuery}
                />
              ))}
            </div>
          ) : (
            <FeedEmpty />
          )}

          {jobs.items.length > 0 && (
            <FeedPagination
              filters={filters}
              total={jobs.total}
              totalPages={jobs.total_pages}
            />
          )}
        </section>
      </div>
    </>
  );
}

function FeedEmpty() {
  return (
    <div className="feed-empty">
      <span className="feed-empty-mark" aria-hidden="true">∅</span>
      <h2>No roles match.</h2>
      <p>Loosen a filter, or clear them all and start again.</p>
      <Link href="/jobs" className="feed-btn">
        Clear filters <span aria-hidden="true">↗</span>
      </Link>
    </div>
  );
}
