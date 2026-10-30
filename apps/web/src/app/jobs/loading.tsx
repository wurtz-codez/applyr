export default function FeedLoading() {
  return (
    <div className="feed-loading" role="status" aria-live="polite">
      <span className="feed-loading-mark" aria-hidden="true">✳</span>
      <p>Scanning the feed…</p>
      <div className="feed-skeleton" aria-hidden="true">
        {[0, 1, 2, 3, 4].map((row) => (
          <div className="feed-skeleton-row" key={row}>
            <span />
            <span />
            <span />
          </div>
        ))}
      </div>
    </div>
  );
}
