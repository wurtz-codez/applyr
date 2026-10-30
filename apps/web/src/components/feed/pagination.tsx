import Link from "next/link";
import type { FeedFilters } from "@/lib/job-types";
import { PAGE_SIZE, feedHref } from "@/lib/feed-filters";
import { formatCount } from "@/lib/format";

export function FeedPagination({
  filters,
  total,
  totalPages,
}: {
  filters: FeedFilters;
  total: number;
  totalPages: number;
}) {
  const start = total === 0 ? 0 : (filters.page - 1) * PAGE_SIZE + 1;
  const end = Math.min(filters.page * PAGE_SIZE, total);

  return (
    <nav className="feed-pagination" aria-label="Pagination">
      <span className="feed-pagination-range">
        {total === 0
          ? "0 roles"
          : `${formatCount(start)}–${formatCount(end)} of ${formatCount(total)}`}
      </span>
      <div className="feed-pagination-controls">
        {filters.page > 1 ? (
          <Link href={feedHref({ ...filters, page: filters.page - 1 })} rel="prev">
            ← Previous
          </Link>
        ) : (
          <span aria-disabled="true">← Previous</span>
        )}
        <span className="feed-pagination-page">
          Page <b>{filters.page}</b> / {Math.max(totalPages, 1)}
        </span>
        {filters.page < totalPages ? (
          <Link href={feedHref({ ...filters, page: filters.page + 1 })} rel="next">
            Next →
          </Link>
        ) : (
          <span aria-disabled="true">Next →</span>
        )}
      </div>
    </nav>
  );
}
