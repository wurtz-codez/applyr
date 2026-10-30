"use client";
export default function ErrorPage({ reset }: { reset: () => void }) {
  return <main className="mx-auto max-w-xl space-y-5 p-12">
    <h1 className="text-2xl font-semibold">We couldn’t load your workspace.</h1>
    <p>Check that the API is running and migrations have been applied, then try again.</p>
    <button onClick={reset}>Try again</button>
  </main>;
}
