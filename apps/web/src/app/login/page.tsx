import { login } from "@/app/actions";

export default async function Login({ searchParams }: {
  searchParams: Promise<{ error?: string }>
}) {
  const { error } = await searchParams;
  return <main className="mx-auto max-w-lg px-6 py-24">
    <p className="mb-4 text-sm font-bold uppercase tracking-widest text-emerald-800">JobPilot AI</p>
    <h1 className="mb-4 text-4xl font-semibold">Your next opportunity starts here.</h1>
    <p className="mb-8 text-slate-600">Sign in to manage your verified profile and prepare for your job search.</p>
    <form action={login} className="panel space-y-5">
      <label htmlFor="token">Local access token</label>
      <input id="token" name="token" type="password" autoComplete="current-password" required minLength={32} maxLength={512} />
      <p className="text-sm text-slate-500">Use the API_TOKEN generated in your local .env file.</p>
      {error && <p role="alert" className="text-red-700">{error === "unavailable" ? "The API is unavailable. Start the backend and try again." : "Please enter a valid access token to continue."}</p>}
      <button type="submit">Sign in</button>
    </form>
  </main>;
}
