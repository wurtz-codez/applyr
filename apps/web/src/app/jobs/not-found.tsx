import Link from "next/link";

export default function JobNotFound() {
  return (
    <section className="feed-offline">
      <p className="feed-tag">[ 404 ] — Missing listing</p>
      <h1>
        That role has <em>vanished.</em>
      </h1>
      <p className="feed-offline-lede">
        The listing may have been removed by its source, or the link is no
        longer valid.
      </p>
      <div className="feed-offline-card">
        <Link href="/jobs" className="feed-btn">
          Back to the feed <span aria-hidden="true">↗</span>
        </Link>
      </div>
    </section>
  );
}
