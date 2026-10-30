import Link from "next/link";
import { getToken } from "@/lib/api";
import { logout } from "@/app/actions";

export default async function Workspace({ children }: { children: React.ReactNode }) {
  await getToken();
  return <>
    <header className="border-b border-slate-200 bg-white">
      <nav aria-label="Main navigation" className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-5 gap-y-3 px-6 py-5 text-sm">
        <Link href="/dashboard" className="mr-auto text-xl font-bold no-underline">JobPilot AI</Link>
        {[ ["Dashboard", "/dashboard"], ["Jobs", "/jobs"], ["Applications", "/applications"], ["Resumes", "/resumes"], ["Profile", "/profile"], ["Runs", "/runs"], ["Settings", "/settings"] ].map(([name, href]) => <Link key={href} href={href}>{name}</Link>)}
        <form action={logout}><button type="submit" className="secondary">Sign out</button></form>
      </nav>
    </header>
    <main className="mx-auto max-w-6xl px-6 py-10">{children}</main>
  </>;
}
