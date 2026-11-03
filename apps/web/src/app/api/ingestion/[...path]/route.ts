import { apiBase } from "@/lib/api";

// Mutations require the operator's token. Never promote an unauthenticated
// browser request by injecting the server's shared API_TOKEN.
async function proxy(request: Request, context: { params: Promise<{ path: string[] }> }) {
  const authorization = request.headers.get("authorization");
  if (!authorization?.startsWith("Bearer ")) {
    return Response.json({ detail: "Enter the administrator API token." }, { status: 401 });
  }
  const { path } = await context.params;
  const endpoint = path.join("/");
  const uuid = "[0-9a-fA-F-]{36}";
  const permitted = endpoint === "sources" && request.method === "POST" ||
    new RegExp(`^sources/${uuid}$`).test(endpoint) && request.method === "PATCH" ||
    new RegExp(`^sources/${uuid}/sync$`).test(endpoint) && request.method === "POST";
  if (!permitted) return Response.json({ detail: "Unknown operation" }, { status: 404 });
  const body = await request.text();
  if (body.length > 40000) return Response.json({ detail: "Request too large" }, { status: 413 });
  try {
    const response = await fetch(`${apiBase}/api/v1/${endpoint}`, {
      method: request.method,
      headers: { Authorization: authorization, "Content-Type": "application/json" },
      body: body || undefined,
      signal: AbortSignal.timeout(15000),
      cache: "no-store",
    });
    return new Response(await response.text(), {
      status: response.status,
      headers: { "Content-Type": "application/json", "Cache-Control": "no-store" },
    });
  } catch {
    return Response.json({ detail: "The API is unavailable." }, { status: 503 });
  }
}

export const POST = proxy;
export const PATCH = proxy;
