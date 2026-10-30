"use client";
import { useEffect } from "react";
import { useRouter } from "next/navigation";

export function AutoRefresh({ active }: { active: boolean }) {
  const router = useRouter();
  useEffect(() => {
    if (!active) return;
    const timer = setInterval(() => router.refresh(), 3000);
    return () => clearInterval(timer);
  }, [active, router]);
  return active ? <p role="status" className="text-sm text-slate-500">Discovery is running. Progress updates automatically.</p> : null;
}
