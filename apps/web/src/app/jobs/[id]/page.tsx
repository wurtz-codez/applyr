import Link from "next/link";
import { notFound } from "next/navigation";
import { ApiError, getJob } from "@/lib/api";
import type { JobDetail } from "@/lib/job-types";
import { feedHref, parseFeedFilters } from "@/lib/feed-filters";
import { FeedOffline } from "@/components/feed/offline";
import {
  formatDate,
  formatDateTime,
  formatRelativeDate,
  formatSalary,
  humanize,
  listingTypeLabel,
  providerLabel,
  sourceHost,
  workModeLabel,
} from "@/lib/format";

export const dynamic = "force-dynamic";

export const metadata = {
  title: "Role — Applyr",
  description: "A listing from the Applyr job feed.",
};

export default async function JobDetailPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { id } = await params;
  const raw = await searchParams;
  if (!/^[0-9a-f-]{36}$/i.test(id)) notFound();

  const backHref = feedHref(parseFeedFilters(raw));

  let job: JobDetail;
  try {
    job = await getJob(id);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound();
    return (
      <FeedOffline
        message={
          error instanceof ApiError
            ? error.message
            : "This listing could not be loaded."
        }
        status={error instanceof ApiError ? error.status : 0}
      />
    );
  }

  const salary = formatSalary(job);
  const published = job.published_at ?? job.first_seen_at;
  const postedLabel = job.published_at ? "Posted" : "First seen";
  const canonicalHost = sourceHost(job.canonical_url);
  const otherSources = job.sources.filter(
    (source) => source.source_url !== job.canonical_url,
  );

  return (
    <article className="job-detail">
      <Link href={backHref} className="job-back">
        ← All roles
      </Link>

      <header className="job-head">
        <div className="job-head-top">
          <p className="feed-tag">
            [ {providerLabel(job.primary_source)} ] — {listingTypeLabel(job.listing_type)}
          </p>
          <span className="job-posted">
            {postedLabel} {formatRelativeDate(published)}
          </span>
        </div>

        <h1>{job.title}</h1>

        <p className="job-company">
          {job.company ? (
            <Link href={`/jobs?company=${encodeURIComponent(job.company)}`}>
              {job.company}
            </Link>
          ) : (
            "Company not listed"
          )}
          <span aria-hidden="true"> · </span>
          {job.location || "Location unknown"}
        </p>

        <div className="job-meta-chips">
          <span className={job.work_mode === "REMOTE" ? "is-remote" : ""}>
            {job.work_mode === "REMOTE" && <i aria-hidden="true" />}
            {job.work_mode === "UNKNOWN"
              ? "Work mode not specified"
              : workModeLabel(job.work_mode)}
          </span>
          {job.employment_type && <span>{job.employment_type}</span>}
          {job.experience_level && <span>{humanize(job.experience_level)}</span>}
          {salary && <span className="job-salary-chip">{salary}</span>}
        </div>
      </header>

      <div className="job-detail-grid">
        <div className="job-body">
          {job.tags.length > 0 && (
            <div className="job-tags">
              {job.tags.map((tag) => (
                <Link key={tag} href={`/jobs?tag=${encodeURIComponent(tag)}`}>
                  #{tag}
                </Link>
              ))}
            </div>
          )}

          <div className="job-description">
            {job.description || "No description was supplied. Open the original listing for details."}
          </div>
        </div>

        <aside className="job-aside">
          <div className="job-apply-card">
            <span className="feed-filter-label">Original listing</span>
            <p className="job-source-host">{canonicalHost}</p>
            <a
              href={job.canonical_url}
              className="feed-btn"
              target="_blank"
              rel="noopener noreferrer"
            >
              Open listing <span aria-hidden="true">↗</span>
            </a>

            <dl className="job-facts">
              <div>
                <dt>Source</dt>
                <dd>{providerLabel(job.primary_source)}</dd>
              </div>
              <div>
                <dt>{postedLabel}</dt>
                <dd>{formatDate(published)}</dd>
              </div>
              <div>
                <dt>First seen</dt>
                <dd>{formatDateTime(job.first_seen_at)}</dd>
              </div>
              <div>
                <dt>Last seen</dt>
                <dd>{formatDateTime(job.last_seen_at)}</dd>
              </div>
            </dl>

            {otherSources.length > 0 && (
              <div className="job-alt-sources">
                <span className="feed-filter-label">Also seen on</span>
                <div>
                  {otherSources.map((source) => (
                    <a
                      key={`${source.provider}-${source.source_url}`}
                      href={source.source_url}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      {providerLabel(source.provider)} ↗
                    </a>
                  ))}
                </div>
              </div>
            )}

            <p className="feed-filter-hint">
              Always verify the role and application details on the original
              listing. Applyr never submits anything for you.
            </p>
          </div>
        </aside>
      </div>
    </article>
  );
}
