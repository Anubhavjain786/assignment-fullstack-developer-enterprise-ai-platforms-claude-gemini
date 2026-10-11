/** Thin HTTP client for the Part A service; identity passes through as header. */
export function serviceUrl(): string {
  return (process.env.MERIDIAN_SERVICE_URL ?? "http://localhost:8000").replace(
    /\/$/,
    "",
  );
}

export function callerEmail(): string {
  return process.env.MERIDIAN_USER_EMAIL ?? "";
}

export interface ServiceResult {
  status: number;
  body: any;
}

export async function serviceGet(
  path: string,
  params: Record<string, string | number | undefined>,
  fetchFn: typeof fetch = fetch,
): Promise<ServiceResult> {
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined) qs.set(k, String(v));
  }
  const res = await fetchFn(`${serviceUrl()}${path}?${qs.toString()}`, {
    headers: { "X-User-Email": callerEmail() },
  });
  return { status: res.status, body: await res.json() };
}

export async function servicePut(
  path: string,
  payload: unknown,
  fetchFn: typeof fetch = fetch,
): Promise<ServiceResult> {
  const res = await fetchFn(`${serviceUrl()}${path}`, {
    method: "PUT",
    headers: {
      "X-User-Email": callerEmail(),
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  return { status: res.status, body: await res.json() };
}
