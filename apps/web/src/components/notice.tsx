export function Notice({ error, success }: { error?: string; success?: string }) {
  return <>
    {error && <p role="alert" className="rounded-xl border border-red-200 bg-red-50 p-4 text-red-800">{error}</p>}
    {success && <p role="status" className="rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-emerald-900">{success}</p>}
  </>;
}
