import type { components } from './schema';

type ErrorDetail = components['schemas']['ErrorDetail'];
export class ApiError extends Error {
  readonly code: string;
  readonly details: ErrorDetail['details'];
  constructor(readonly status: number, error: ErrorDetail) {
    super(error.message);
    this.name = 'ApiError';
    this.code = error.code;
    this.details = error.details;
  }
}
let csrfToken: string | undefined;
let csrfBootstrap: Promise<string> | undefined;
async function getCsrfToken(): Promise<string> {
  if (csrfToken) return csrfToken;
  if (!csrfBootstrap) {
    csrfBootstrap = (async () => {
      const response = await fetch('/api/auth/csrf', { credentials: 'same-origin', cache: 'no-store' });
      if (!response.ok) throw new Error('CSRF bootstrap failed');
      const body: components['schemas']['CsrfResponse'] = await response.json();
      csrfToken = body.csrf_token;
      return csrfToken;
    })().finally(() => { csrfBootstrap = undefined; });
  }
  return csrfBootstrap;
}
export async function apiRequest<T>(path: string, options: RequestInit): Promise<T> {
  const headers = new Headers(options.headers);
  const method = (options.method ?? 'GET').toUpperCase();
  if (['POST', 'PUT', 'PATCH', 'DELETE'].includes(method)) {
    headers.set('X-CSRF-Token', await getCsrfToken());
  }
  if (options.body) headers.set('Content-Type', 'application/json');
  const response = await fetch(path, { ...options, headers, credentials: 'same-origin', cache: 'no-store' });
  if (!response.ok) {
    const body: components['schemas']['ErrorResponse'] = await response.json();
    if (body.error.code === 'CSRF_INVALID') csrfToken = undefined;
    throw new ApiError(response.status, body.error);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}
