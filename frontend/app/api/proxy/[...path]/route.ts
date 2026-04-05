import { type NextRequest, NextResponse } from "next/server";

const STATE_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);
const TOKEN_COOKIE = "fairswarm_access_token";
const REFRESH_COOKIE = "fairswarm_refresh_token";
const CSRF_COOKIE = "fairswarm_csrf_token";

function backendBaseUrl(): string {
  return (
    process.env.BACKEND_INTERNAL_URL ??
    process.env.NEXT_PUBLIC_API_BASE_URL ??
    "http://localhost:8000/api/v1"
  ).replace(/\/$/, "");
}

function isAuthPath(path: string): boolean {
  return (
    path === "auth/login" ||
    path === "auth/register" ||
    path === "auth/refresh" ||
    path === "auth/logout"
  );
}

function applyAuthCookies(response: NextResponse, payload: Record<string, unknown>) {
  const accessToken = typeof payload.access_token === "string" ? payload.access_token : null;
  const refreshToken = typeof payload.refresh_token === "string" ? payload.refresh_token : null;
  const csrfToken = typeof payload.csrf_token === "string" ? payload.csrf_token : null;

  if (accessToken) {
    response.cookies.set(TOKEN_COOKIE, accessToken, {
      httpOnly: true,
      secure: process.env.NODE_ENV === "production",
      sameSite: "lax",
      path: "/",
      maxAge: 60 * 60,
    });
  }

  if (refreshToken) {
    response.cookies.set(REFRESH_COOKIE, refreshToken, {
      httpOnly: true,
      secure: process.env.NODE_ENV === "production",
      sameSite: "lax",
      path: "/",
      maxAge: 7 * 24 * 60 * 60,
    });
  }

  if (csrfToken) {
    response.cookies.set(CSRF_COOKIE, csrfToken, {
      httpOnly: false,
      secure: process.env.NODE_ENV === "production",
      sameSite: "lax",
      path: "/",
      maxAge: 7 * 24 * 60 * 60,
    });
  }
}

function clearAuthCookies(response: NextResponse) {
  response.cookies.set(TOKEN_COOKIE, "", { path: "/", maxAge: 0 });
  response.cookies.set(REFRESH_COOKIE, "", { path: "/", maxAge: 0 });
  response.cookies.set(CSRF_COOKIE, "", { path: "/", maxAge: 0 });
}

async function proxyRequest(request: NextRequest, pathParts: string[]) {
  const targetPath = pathParts.join("/");
  const targetUrl = `${backendBaseUrl()}/${targetPath}${request.nextUrl.search}`;

  if (STATE_METHODS.has(request.method) && !isAuthPath(targetPath)) {
    const csrfCookie = request.cookies.get(CSRF_COOKIE)?.value;
    const csrfHeader = request.headers.get("x-csrf-token");
    if (!csrfCookie || !csrfHeader || csrfCookie !== csrfHeader) {
      return NextResponse.json({ detail: "CSRF token missing or invalid." }, { status: 403 });
    }
  }

  const headers = new Headers(request.headers);
  headers.delete("host");
  headers.delete("cookie");
  headers.delete("content-length");

  const accessToken = request.cookies.get(TOKEN_COOKIE)?.value;
  if (accessToken) {
    headers.set("authorization", `Bearer ${accessToken}`);
  }

  let body: BodyInit | undefined;
  if (request.method !== "GET" && request.method !== "HEAD") {
    if (targetPath === "auth/refresh") {
      headers.set("content-type", "application/json");
      body = JSON.stringify({ refresh_token: request.cookies.get(REFRESH_COOKIE)?.value ?? "" });
    } else {
      const contentType = request.headers.get("content-type") ?? "";
      if (contentType.includes("application/json")) {
        const json = await request.text();
        body = json || undefined;
      } else {
        body = await request.arrayBuffer();
      }
    }
  }

  const upstream = await fetch(targetUrl, {
    method: request.method,
    headers,
    body,
    redirect: "manual",
  });

  const upstreamType = upstream.headers.get("content-type") ?? "";

  if (isAuthPath(targetPath)) {
    const payload = upstreamType.includes("application/json") ? await upstream.json() : {};
    const safePayload = { ...(payload as Record<string, unknown>) };
    delete safePayload.access_token;
    delete safePayload.refresh_token;
    delete safePayload.csrf_token;

    const response = NextResponse.json(safePayload, { status: upstream.status });

    if (upstream.ok && (targetPath === "auth/login" || targetPath === "auth/register" || targetPath === "auth/refresh")) {
      applyAuthCookies(response, payload as Record<string, unknown>);
    }

    if (upstream.ok && targetPath === "auth/logout") {
      clearAuthCookies(response);
    }

    return response;
  }

  const buffer = await upstream.arrayBuffer();
  const response = new NextResponse(buffer, { status: upstream.status });

  const passHeaders = ["content-type", "content-disposition", "cache-control"];
  for (const header of passHeaders) {
    const value = upstream.headers.get(header);
    if (value) {
      response.headers.set(header, value);
    }
  }

  return response;
}

export async function GET(request: NextRequest, context: { params: { path: string[] } }) {
  return proxyRequest(request, context.params.path);
}

export async function POST(request: NextRequest, context: { params: { path: string[] } }) {
  return proxyRequest(request, context.params.path);
}

export async function PUT(request: NextRequest, context: { params: { path: string[] } }) {
  return proxyRequest(request, context.params.path);
}

export async function PATCH(request: NextRequest, context: { params: { path: string[] } }) {
  return proxyRequest(request, context.params.path);
}

export async function DELETE(request: NextRequest, context: { params: { path: string[] } }) {
  return proxyRequest(request, context.params.path);
}
