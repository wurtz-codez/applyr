import Link from "next/link";

export function FeedOffline({
  message,
  status = 0,
}: {
  message: string;
  status?: number;
}) {
  const tokenIssue = status === 401;

  return (
    <section className="feed-offline">
      <p className="feed-tag">[ ! ] — Connection</p>
      <h1>
        The feed is <em>offline.</em>
      </h1>
      <p className="feed-offline-lede">{message}</p>
      <div className="feed-offline-card">
        <span className="feed-filter-label">
          {tokenIssue ? "Local configuration" : "Start the API"}
        </span>
        {tokenIssue ? (
          <p>
            Check that <code>API_TOKEN</code> in the root <code>.env</code>{" "}
            matches the token used by the web app.
          </p>
        ) : (
          <pre>
            <code>
{`cd apps/api
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000`}
            </code>
          </pre>
        )}
        <Link href="/jobs" className="feed-btn">
          Try again <span aria-hidden="true">↗</span>
        </Link>
      </div>
    </section>
  );
}
