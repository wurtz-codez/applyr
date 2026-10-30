import Link from "next/link";
import { getToken } from "@/lib/api";
import { logout } from "@/app/actions";

export default async function Workspace({ children }: { children: React.ReactNode }) {
  await getToken();
  return <>
    <header className="border-b border-slate-200 bg-white">
      <nav aria-label="Main navigation" className="mx-auto flex max-w-5xl flex-wrap items-center gap-6 px-6 py-5">
        <Link href="/dashboard" className="mr-auto text-xl font-bold no-underline">JobPilot AI</Link>
        <Link href="/dashboard">Dashboard</Link><Link href="/profile">Profile</Link>
        <form action={logout}><button type="submit">Sign out</button></form>
      </nav>
    </header>
    <main className="mx-auto max-w-5xl px-6 py-12">{children}</main>
  </>;
}
