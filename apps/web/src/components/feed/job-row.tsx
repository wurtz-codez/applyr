import Link from "next/link";
import type { JobSummary } from "@/lib/job-types";
import {
  formatRelativeDate,
  formatSalary,
  humanize,
  providerLabel,
  workModeLabel,
} from "@/lib/format";

export function JobRow({
  job,
  index,
  returnQuery = "",
}: {
  job: JobSummary;
  index: number;
  returnQuery?: string;
}) {
  const salary = formatSalary(job);
  const published = job.published_at ?? job.first_seen_at;
  const publishedTime = new Date(published).getTime();
  const isNew = Number.isFinite(publishedTime) && Date.now() - publishedTime < 1000 * 60 * 60 * 72;
  const tags = job.tags.slice(0, 4);
  const extraTags = job.tags.length - tags.length;
  const isSearch = job.listing_type === "SEARCH_RESULT";

  return (
    <Link
      href={`/jobs/${job.id}${returnQuery ? `?${returnQuery}` : ""}`}
      className={`feed-job${isSearch ? " is-search" : ""}`}
    >
      <span className="feed-job-index" aria-hidden="true">
        {String(index).padStart(3, "0")}
      </span>

      <div className="feed-job-main">
        <div className="feed-job-topline">
          <span className="feed-job-company">
            {job.company || (isSearch ? "Search result" : "Company not listed")}
          </span>
          <span className="feed-job-source">{providerLabel(job.primary_source)}</span>
          {isNew && <span className="feed-job-new">New</span>}
          {isSearch && <span className="feed-job-new">Search page</span>}
        </div>

        <h2>{job.title}</h2>

        {job.description_excerpt && (
          <p className="feed-job-excerpt">{job.description_excerpt}</p>
        )}

        <div className="feed-job-meta">
          <span>{job.location || "Location unknown"}</span>
          {job.work_mode !== "UNKNOWN" && (
            <span className={job.work_mode === "REMOTE" ? "is-remote" : ""}>
              {job.work_mode === "REMOTE" && <i aria-hidden="true" />}
              {workModeLabel(job.work_mode)}
            </span>
          )}
          {job.employment_type && <span>{job.employment_type}</span>}
          {job.experience_level && <span>{humanize(job.experience_level)}</span>}
          {salary && <span className="feed-job-salary">{salary}</span>}
        </div>

        {tags.length > 0 && (
          <div className="feed-job-tags">
            {tags.map((tag) => (
              <span key={tag}>#{tag}</span>
            ))}
            {extraTags > 0 && <span>+{extraTags}</span>}
          </div>
        )}
      </div>

      <div className="feed-job-side">
        <span className="feed-job-date">{formatRelativeDate(published)}</span>
        <span className="feed-job-arrow" aria-hidden="true">↗</span>
      </div>
    </Link>
  );
}
