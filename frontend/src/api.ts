export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}

export async function api<T>(
  url: string,
  options: RequestInit = {},
): Promise<T> {
  const r = await fetch(url, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
  });
  if (!r.ok) {
    const x = await r.json().catch(() => ({}));
    // #region agent log
    fetch("http://127.0.0.1:7353/ingest/d7c1cc8b-c0a3-49b7-960e-6eca5743ef25", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Debug-Session-Id": "1b8194",
      },
      body: JSON.stringify({
        sessionId: "1b8194",
        runId: "pre-fix",
        hypothesisId: "A",
        location: "api.ts:api",
        message: "non-ok response detail",
        data: {
          url,
          status: r.status,
          detailType: Array.isArray(x.detail) ? "array" : typeof x.detail,
          detailLength: Array.isArray(x.detail) ? x.detail.length : null,
          items: Array.isArray(x.detail)
            ? x.detail.slice(0, 12).map((item: any) => ({
                loc: Array.isArray(item?.loc)
                  ? item.loc.map(String).join(".")
                  : null,
                msg: typeof item?.msg === "string" ? item.msg : null,
                type: typeof item?.type === "string" ? item.type : null,
              }))
            : null,
          stringified: String(x.detail ?? "").slice(0, 240),
        },
        timestamp: Date.now(),
      }),
    }).catch(() => {});
    // #endregion
    throw new ApiError(x.detail || `Request failed: ${r.status}`, r.status);
  }
  return r.status === 204 ? (undefined as T) : r.json();
}
