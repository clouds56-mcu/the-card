/** Cloudflare Worker entry point for The Card website. */
import handler from "vinext/server/app-router-entry";

interface AssetFetcher {
  fetch(request: Request): Promise<Response>;
}

interface Env {
  ASSETS: AssetFetcher;
}

interface ExecutionContext {
  waitUntil(promise: Promise<unknown>): void;
  passThroughOnException(): void;
}

const worker = {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const response = await handler.fetch(request, env, ctx);
    const headers = new Headers(response.headers);
    const content_type = headers.get("Content-Type") ?? "";
    if (content_type.includes("text/html")) {
      headers.append(
        "Content-Security-Policy",
        "base-uri 'self'; frame-ancestors 'none'; object-src 'none'",
      );
    } else if (content_type.includes("image/svg+xml")) {
      headers.append(
        "Content-Security-Policy",
        "sandbox; default-src 'none'; style-src 'unsafe-inline'",
      );
    }
    headers.set("Permissions-Policy", "camera=(), geolocation=(), microphone=()");
    headers.set("Referrer-Policy", "strict-origin-when-cross-origin");
    headers.set("X-Content-Type-Options", "nosniff");
    headers.set("X-Frame-Options", "DENY");

    return new Response(response.body, {
      headers,
      status: response.status,
      statusText: response.statusText,
    });
  },
};

export default worker;
