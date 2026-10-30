import { apiFetch } from "@/lib/api";

export async function GET(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  if (!/^[0-9a-f-]{36}$/i.test(id)) return new Response("Resume not found", { status: 404 });
  const response = await apiFetch(`/api/v1/resumes/${id}/download`);
  if (!response.ok) return new Response("Resume unavailable", { status: response.status });
  return new Response(response.body, { headers: {
    "Content-Type": "application/pdf",
    "Content-Disposition": response.headers.get("Content-Disposition") ?? "attachment; filename=resume.pdf",
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
    "Content-Security-Policy": "sandbox; default-src 'none'",
  } });
}
