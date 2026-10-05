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
export class SessionChangedError extends ApiError {
  constructor() { super(401, { code: 'AUTH_REQUIRED', message: 'Session changed', details: {} }); }
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
async function rawRequest<T>(path: string, options: RequestInit): Promise<T> {
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

type UserResponse = components['schemas']['UserResponse'];
type AuthPhase = 'active' | 'logging-in' | 'logging-out' | 'anonymous';
let generation = 0;
let renewal = 0;
let phase: AuthPhase = 'active';
const authListeners = new Set<() => void>();
const lossListeners = new Set<() => void>();
let refreshFlight: Promise<UserResponse> | undefined;
let logoutFlight: Promise<void> | undefined;
let loginFlight: Promise<UserResponse> | undefined;
let refreshAttempts = 0;
let lastRefresh: Promise<UserResponse> | undefined;
export const getAuthPhase = () => phase;
export function subscribeAuthChanges(listener: () => void) {
  authListeners.add(listener);
  return () => { authListeners.delete(listener); };
}
export function subscribeSessionLoss(listener: () => void) {
  lossListeners.add(listener);
  return () => { lossListeners.delete(listener); };
}
function setPhase(next: AuthPhase) {
  phase = next;
  authListeners.forEach(listener => listener());
}
function sessionChanged() {
  return new SessionChangedError();
}
function assertGeneration(expected: number) {
  if (expected !== generation) throw sessionChanged();
}
function loseSession() {
  generation++;
  setPhase('anonymous');
  lossListeners.forEach(listener => listener());
}
export function refreshSession(): Promise<UserResponse> {
  if (phase !== 'active') return Promise.reject(sessionChanged());
  if (refreshFlight) return refreshFlight;
  const expected = generation;
  refreshAttempts++;
  const flight = (async () => {
    try {
      const user = await rawRequest<UserResponse>('/api/auth/refresh', { method: 'POST' });
      assertGeneration(expected);
      if (phase !== 'active') throw sessionChanged();
      renewal++;
      return user;
    } catch (cause) {
      if (expected === generation && phase === 'active' && cause instanceof ApiError && cause.status === 401) loseSession();
      throw cause;
    }
  })().finally(() => { if (refreshFlight === flight) refreshFlight = undefined; });
  refreshFlight = flight;
  lastRefresh = flight;
  return flight;
}
export function logoutSession(): Promise<void> {
  if (logoutFlight) return logoutFlight;
  const pendingRefresh = refreshFlight;
  const pendingLogin = loginFlight;
  const previousPhase = phase === 'logging-in' ? 'active' : phase;
  generation++;
  setPhase('logging-out');
  const flight = (async () => {
    try {
      // Wait for its Set-Cookie to reach the browser before clearing cookies.
      await pendingLogin?.catch(() => undefined);
      await pendingRefresh?.catch(() => undefined);
      await rawRequest<void>('/api/auth/logout', { method: 'POST' });
      loseSession();
    } catch (cause) {
      setPhase(previousPhase);
      throw cause;
    }
  })().finally(() => { if (logoutFlight === flight) logoutFlight = undefined; });
  logoutFlight = flight;
  return flight;
}
function loginSession(path: string, options: RequestInit): Promise<UserResponse> {
  if (loginFlight) return Promise.reject(sessionChanged());
  const flight = (async () => {
    if (logoutFlight) await logoutFlight.catch(() => undefined);
    const pendingRefresh = refreshFlight;
    const previousPhase = phase;
    const expected = ++generation;
    setPhase('logging-in');
    try {
      // Old Set-Cookie must settle before another account's cookies are issued.
      await pendingRefresh?.catch(() => undefined);
      assertGeneration(expected);
      const user = await rawRequest<UserResponse>(path, options);
      assertGeneration(expected);
      renewal = 0;
      refreshAttempts = 0;
      lastRefresh = undefined;
      setPhase('active');
      return user;
    } catch (cause) {
      if (expected === generation) setPhase(previousPhase);
      throw cause;
    }
  })().finally(() => { if (loginFlight === flight) loginFlight = undefined; });
  loginFlight = flight;
  return flight;
}
export type ApiRequestOptions = RequestInit & {
  // Protected callers opt in; public transport is independent of auth state.
  requiresAuth?: boolean;
};
export async function apiRequest<T>(path: string, options: ApiRequestOptions): Promise<T> {
  const { requiresAuth = false, ...requestOptions } = options;
  const route = path.split('?')[0].replace(/\/+$/, '');
  const method = (options.method ?? 'GET').toUpperCase();
  if (method === 'POST' && route === '/api/auth/logout') return logoutSession() as Promise<T>;
  if (method === 'POST' && route === '/api/auth/refresh') return refreshSession() as Promise<T>;
  if (method === 'POST' && route === '/api/auth/login') return loginSession(path, requestOptions) as Promise<T>;
  if (!requiresAuth) return rawRequest<T>(path, requestOptions);
  const expected = generation;
  const originalRenewal = renewal;
  const originalAttempt = refreshAttempts;
  const originalRefresh = refreshFlight;
  if (phase !== 'active') throw sessionChanged();
  let result: T;
  try {
    result = await rawRequest<T>(path, requestOptions);
  } catch (cause) {
    assertGeneration(expected);
    if (!(cause instanceof ApiError) || cause.status !== 401 || cause.code !== 'AUTH_REQUIRED' || phase !== 'active') throw cause;
    if (originalRenewal === renewal) {
      // A delayed 401 belongs to the attempt already observed by its cohort,
      // including failed attempts. A newly started request can try again.
      if (originalRefresh) await originalRefresh;
      else if (originalAttempt < refreshAttempts && lastRefresh) await lastRefresh;
      else await refreshSession();
    }
    assertGeneration(expected);
    try { result = await rawRequest<T>(path, requestOptions); }
    catch (retryError) {
      assertGeneration(expected);
      if (retryError instanceof ApiError && retryError.status === 401 && retryError.code === 'AUTH_REQUIRED') loseSession();
      throw retryError;
    }
  }
  assertGeneration(expected);
  return result;
}
