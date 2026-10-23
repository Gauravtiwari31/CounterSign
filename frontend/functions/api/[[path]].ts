// Cloudflare Pages Function: proxies /api/* to the Render backend so the browser only ever talks to
// the Pages origin. Same origin means no CORS, and the session cookie stays first-party (SameSite=Lax),
// which third-party-cookie blocking in Safari and Chrome cannot break.
//
// Env (Pages project → Settings → Variables, both optional):
//   API_ORIGIN        overrides the production Render service below (local dev: http://localhost:8000)
//   PREVIEW_API_HOST  Render PR preview host pattern, e.g. countersign-rpcj-pr-{n}.onrender.com
// A deployment served from the alias pr-<n>.<project>.pages.dev talks to PR <n>'s Render preview.

const DEFAULT_API_ORIGIN = "https://countersign-rpcj.onrender.com";

interface Env {
  API_ORIGIN?: string;
  PREVIEW_API_HOST?: string;
}

function upstream(host: string, env: Env): string {
  const pr = /^pr-(\d+)\./.exec(host);
  if (pr && env.PREVIEW_API_HOST) return "https://" + env.PREVIEW_API_HOST.replace("{n}", pr[1]);
  return (env.API_ORIGIN || DEFAULT_API_ORIGIN).replace(/\/+$/, "");
}

export const onRequest = async ({ request, env }: { request: Request; env: Env }): Promise<Response> => {
  const url = new URL(request.url);
  const origin = upstream(url.hostname, env);
  const req = new Request(origin + url.pathname + url.search, request);
  req.headers.set("x-forwarded-for", request.headers.get("cf-connecting-ip") ?? "");
  req.headers.set("x-forwarded-proto", "https");
  req.headers.set("x-forwarded-host", url.host);
  return fetch(req, { redirect: "manual" });
};
