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
    throw new ApiError(x.detail || `Request failed: ${r.status}`, r.status);
  }
  return r.status === 204 ? (undefined as T) : r.json();
}
