"use client";

import Link from "next/link";
import { useEffect } from "react";

export default function FeedError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <section className="feed-offline">
      <p className="feed-tag">[ ! ] — Unexpected error</p>
      <h1>
        Something went <em>sideways.</em>
      </h1>
      <p className="feed-offline-lede">
        The feed could not be rendered. This is usually a temporary API or
        network problem.
      </p>
      <div className="feed-offline-card">
        <span className="feed-filter-label">Try</span>
        <p>Reload the feed, or check that the local API is still running.</p>
        <div className="feed-offline-actions">
          <button type="button" className="feed-btn" onClick={reset}>
            Try again <span aria-hidden="true">↗</span>
          </button>
          <Link href="/jobs" className="feed-text-btn">Back to feed</Link>
        </div>
      </div>
    </section>
  );
}
