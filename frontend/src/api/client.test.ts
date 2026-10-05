import { waitFor } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
let client: typeof import('./client');
const user = { id: '00000000-0000-4000-8000-000000000001', email: 'alice@example.com', created_at: '2026-10-04T12:00:00Z', updated_at: '2026-10-04T12:00:00Z' };
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const error = (code = 'AUTH_REQUIRED', status = 401) => json({ error: { code, message: 'Request failed.', details: {} } }, status);
function deferred<T>() { let resolve!: (value: T) => void; const promise = new Promise<T>(done => { resolve = done; }); return { promise, resolve }; }
beforeEach(async () => { vi.resetModules(); client = await import('./client'); });
afterEach(() => vi.unstubAllGlobals());

it('shares a single refresh and retries concurrent originals with unchanged method/body/headers', async () => {
  const renewal = deferred<Response>();
  let authenticated = false, refreshes = 0, mutations = 0;
  const attempts: { method: string; body: BodyInit | null | undefined; headers: Headers }[] = [];
  vi.stubGlobal('fetch', vi.fn<typeof fetch>(async (input, options) => {
    if (input === '/api/auth/csrf') return json({ csrf_token: 'csrf-fixture' });
    if (input === '/api/auth/refresh') { refreshes++; expect(new Headers(options?.headers).get('X-CSRF-Token')).toBe('csrf-fixture'); const response = await renewal.promise; authenticated = true; return response; }
    expect(options).not.toHaveProperty('requiresAuth');
    attempts.push({ method: options?.method ?? 'GET', body: options?.body, headers: new Headers(options?.headers) });
    if (!authenticated) return error();
    if (options?.method === 'POST') mutations++;
    return json({ value: 'protected data' });
  }));
  const read = client.apiRequest('/api/protected/read', { requiresAuth: true,});
  const write = client.apiRequest('/api/protected/write', { requiresAuth: true, method: 'POST', body: JSON.stringify({ command: 'example' }), headers: { 'X-Request-Id': 'stable' } });
  await waitFor(() => expect(attempts).toHaveLength(2));
  expect(refreshes).toBe(1);
  renewal.resolve(json(user));
  expect(await Promise.all([read, write])).toEqual([{ value: 'protected data' }, { value: 'protected data' }]);
  expect(refreshes).toBe(1); expect(attempts).toHaveLength(4); expect(mutations).toBe(1);
  for (const attempt of attempts.filter(attempt => attempt.method === 'POST')) {
    expect(attempt.body).toBe(JSON.stringify({ command: 'example' }));
    expect(attempt.headers.get('X-Request-Id')).toBe('stable');
    expect(attempt.headers.get('X-CSRF-Token')).toBe('csrf-fixture');
  }
});
it('does not loop when the retried protected request still returns AUTH_REQUIRED', async () => {
  let refreshes = 0, reads = 0;
  vi.stubGlobal('fetch', vi.fn<typeof fetch>(async input => {
    if (input === '/api/auth/csrf') return json({ csrf_token: 'csrf-fixture' });
    if (input === '/api/auth/refresh') { refreshes++; return json(user); }
    reads++; return error();
  }));
  await expect(client.apiRequest('/api/protected/read', { requiresAuth: true,})).rejects.toMatchObject({ code: 'AUTH_REQUIRED' });
  expect(refreshes).toBe(1); expect(reads).toBe(2);
});
it.each(['/api/auth/login', '/api/auth/register', '/api/auth/refresh', '/api/auth/logout'])('never automatically recovers %s', async path => {
  const paths: string[] = [];
  vi.stubGlobal('fetch', vi.fn<typeof fetch>(async input => { if (input === '/api/auth/csrf') return json({ csrf_token: 'csrf-fixture' }); paths.push(String(input)); return error(); }));
  await expect(client.apiRequest(path, { method: 'POST' })).rejects.toMatchObject({ code: 'AUTH_REQUIRED' });
  expect(paths).toEqual([path]);
});
it('does not recover an arbitrary 401 error code', async () => {
  const paths: string[] = [];
  vi.stubGlobal('fetch', vi.fn<typeof fetch>(async input => { paths.push(String(input)); return error('OTHER_UNAUTHORIZED'); }));
  await expect(client.apiRequest('/api/protected/read', { requiresAuth: true,})).rejects.toMatchObject({ code: 'OTHER_UNAUTHORIZED' });
  expect(paths).toEqual(['/api/protected/read']);
});
it('terminal refresh 401 reports session loss and never retries the original', async () => {
  let reads = 0, refreshes = 0, losses = 0;
  client.subscribeSessionLoss(() => { losses++; });
  vi.stubGlobal('fetch', vi.fn<typeof fetch>(async input => {
    if (input === '/api/auth/csrf') return json({ csrf_token: 'csrf-fixture' });
    if (input === '/api/auth/refresh') { refreshes++; return error('AUTH_REFRESH_INVALID'); }
    reads++; return error();
  }));
  await expect(client.apiRequest('/api/protected/read', { requiresAuth: true,})).rejects.toMatchObject({ code: 'AUTH_REFRESH_INVALID' });
  expect(reads).toBe(1); expect(refreshes).toBe(1); expect(losses).toBe(1);
  expect(client.getAuthPhase()).toBe('anonymous');
});
it.each([403, 503, 'network'] as const)('propagates refresh %s without false success or retry', async status => {
  let refreshes = 0, reads = 0;
  vi.stubGlobal('fetch', vi.fn<typeof fetch>(async input => {
    if (input === '/api/auth/csrf') return json({ csrf_token: 'csrf-fixture' });
    if (input === '/api/auth/refresh') { refreshes++; if (status === 'network') throw new TypeError('Network unavailable'); return error(status === 403 ? 'CSRF_INVALID' : 'SERVICE_UNAVAILABLE', status); }
    reads++; return error();
  }));
  if (status === 'network') await expect(client.apiRequest('/api/protected/read', { requiresAuth: true,})).rejects.toBeInstanceOf(TypeError);
  else await expect(client.apiRequest('/api/protected/read', { requiresAuth: true,})).rejects.toMatchObject({ status });
  expect(refreshes).toBe(1); expect(reads).toBe(1); expect(client.getAuthPhase()).toBe('active');
});
it('logout waits for in-flight refresh and blocks late recovery/state publication', async () => {
  const renewal = deferred<Response>(); const events: string[] = []; let authenticated = false;
  vi.stubGlobal('fetch', vi.fn<typeof fetch>(async input => {
    if (input === '/api/auth/csrf') return json({ csrf_token: 'csrf-fixture' });
    if (input === '/api/auth/refresh') { events.push('refresh-start'); const response = await renewal.promise; authenticated = true; events.push('refresh-complete'); return response; }
    if (input === '/api/auth/logout') { events.push('logout'); authenticated = false; return new Response(null, { status: 204 }); }
    return error();
  }));
  const original = client.apiRequest('/api/protected/read', { requiresAuth: true,}).catch(cause => cause);
  await waitFor(() => expect(events).toEqual(['refresh-start']));
  const logout = client.logoutSession(); expect(client.getAuthPhase()).toBe('logging-out');
  await expect(client.refreshSession()).rejects.toMatchObject({ code: 'AUTH_REQUIRED' });
  expect(events).toEqual(['refresh-start']); renewal.resolve(json(user)); await logout;
  expect(events).toEqual(['refresh-start', 'refresh-complete', 'logout']); expect(authenticated).toBe(false);
  expect(await original).toMatchObject({ code: 'AUTH_REQUIRED' }); expect(client.getAuthPhase()).toBe('anonymous');
});
it('discards an old successful protected response after logout', async () => {
  const late = deferred<Response>();
  vi.stubGlobal('fetch', vi.fn<typeof fetch>(async input => { if (input === '/api/auth/csrf') return json({ csrf_token: 'csrf-fixture' }); if (input === '/api/auth/logout') return new Response(null, { status: 204 }); return late.promise; }));
  const original = client.apiRequest('/api/protected/read', { requiresAuth: true,}).catch(cause => cause);
  await client.logoutSession(); late.resolve(json(user)); expect(await original).toMatchObject({ code: 'AUTH_REQUIRED' });
});
it('coordinates explicit refreshSession calls for a future stream consumer', async () => {
  const renewal = deferred<Response>(); let refreshes = 0;
  vi.stubGlobal('fetch', vi.fn<typeof fetch>(async input => { if (input === '/api/auth/csrf') return json({ csrf_token: 'csrf-fixture' }); refreshes++; return renewal.promise; }));
  const first = client.refreshSession(), second = client.refreshSession();
  await waitFor(() => expect(refreshes).toBe(1)); renewal.resolve(json(user)); expect(await Promise.all([first, second])).toEqual([user, user]);
});
it('reuses completed recovery for a concurrent late 401 instead of starting another refresh', async () => {
  const late = deferred<Response>(); let refreshes = 0, lateReads = 0;
  vi.stubGlobal('fetch', vi.fn<typeof fetch>(async input => {
    if (input === '/api/auth/csrf') return json({ csrf_token: 'csrf-fixture' });
    if (input === '/api/auth/refresh') { refreshes++; return json(user); }
    if (input === '/api/protected/late' && ++lateReads === 1) return late.promise;
    return refreshes ? json(user) : error();
  }));
  const first = client.apiRequest('/api/protected/first', { requiresAuth: true,});
  const second = client.apiRequest('/api/protected/late', { requiresAuth: true,});
  await first; late.resolve(error());
  expect(await second).toEqual(user); expect(refreshes).toBe(1); expect(lateReads).toBe(2);
});
it('permits manual recovery after a failed logout without accepting old responses', async () => {
  let logouts = 0;
  vi.stubGlobal('fetch', vi.fn<typeof fetch>(async input => {
    if (input === '/api/auth/csrf') return json({ csrf_token: 'csrf-fixture' });
    if (input === '/api/auth/logout') { logouts++; return logouts === 1 ? error('CSRF_INVALID', 403) : new Response(null, { status: 204 }); }
    return json(user);
  }));
  await expect(client.logoutSession()).rejects.toMatchObject({ status: 403 });
  expect(client.getAuthPhase()).toBe('active');
  expect(await client.refreshSession()).toEqual(user);
  await client.logoutSession(); expect(client.getAuthPhase()).toBe('anonymous'); expect(logouts).toBe(2);
});
it.each([403, 503, 'network'] as const)('shares settled refresh %s with late failures, but permits a new manual request', async status => {
  const late = deferred<Response>(); let refreshes = 0, lateReads = 0;
  vi.stubGlobal('fetch', vi.fn<typeof fetch>(async input => {
    if (input === '/api/auth/csrf') return json({ csrf_token: 'csrf-fixture' });
    if (input === '/api/auth/refresh') { refreshes++; if (status === 'network') throw new TypeError('Network unavailable'); return error(status === 403 ? 'CSRF_INVALID' : 'SERVICE_UNAVAILABLE', status); }
    if (input === '/api/protected/late' && ++lateReads === 1) return late.promise;
    return error();
  }));
  const first = client.apiRequest('/api/protected/first', { requiresAuth: true,}).catch(cause => cause);
  const second = client.apiRequest('/api/protected/late', { requiresAuth: true,}).catch(cause => cause);
  const failure = await first; late.resolve(error());
  expect(await second).toBe(failure); expect(refreshes).toBe(1);
  await client.apiRequest('/api/protected/new', { requiresAuth: true,}).catch(() => undefined);
  expect(refreshes).toBe(2);
});
it('serializes login behind old refresh and blocks recovery during the account switch', async () => {
  const late = deferred<Response>(); const loginResponse = deferred<Response>(); const events: string[] = [];
  let cookieOwner = 'alice';
  const other = { ...user, email: 'bob@example.com' };
  vi.stubGlobal('fetch', vi.fn<typeof fetch>(async input => {
    if (input === '/api/auth/csrf') return json({ csrf_token: 'csrf-fixture' });
    if (input === '/api/auth/refresh') { events.push('refresh'); const response = await late.promise; cookieOwner = 'alice'; return response; }
    if (input === '/api/auth/login') { events.push('login'); const response = await loginResponse.promise; cookieOwner = 'bob'; return response; }
    return json(cookieOwner === 'bob' ? other : user);
  }));
  const refresh = client.refreshSession().catch(cause => cause);
  await waitFor(() => expect(events).toEqual(['refresh']));
  const login = client.apiRequest('/api/auth/login', { method: 'POST', body: JSON.stringify({ email: other.email, password: 'a long password' }) });
  expect(client.getAuthPhase()).toBe('logging-in');
  await expect(client.refreshSession()).rejects.toMatchObject({ code: 'AUTH_REQUIRED' });
  expect(events).toEqual(['refresh']);
  late.resolve(json(user));
  await waitFor(() => expect(events).toEqual(['refresh', 'login']));
  await expect(client.refreshSession()).rejects.toMatchObject({ code: 'AUTH_REQUIRED' });
  loginResponse.resolve(json(other)); expect(await login).toEqual(other);
  expect(await refresh).toMatchObject({ code: 'AUTH_REQUIRED' });
  expect(await client.apiRequest('/api/auth/me', { requiresAuth: true })).toEqual(other);
});
it('logout also waits for an already sent login before clearing its cookies', async () => {
  const late = deferred<Response>(); const events: string[] = []; let authenticated = false;
  vi.stubGlobal('fetch', vi.fn<typeof fetch>(async input => {
    if (input === '/api/auth/csrf') return json({ csrf_token: 'csrf-fixture' });
    if (input === '/api/auth/login') { events.push('login'); const response = await late.promise; authenticated = true; return response; }
    if (input === '/api/auth/logout') { events.push('logout'); authenticated = false; return new Response(null, { status: 204 }); }
    return error();
  }));
  const login = client.apiRequest('/api/auth/login', { method: 'POST' }).catch(cause => cause);
  await waitFor(() => expect(events).toEqual(['login']));
  const logout = client.logoutSession();
  await client.apiRequest('/api/protected/while-logging-out', { requiresAuth: true,}).catch(() => undefined);
  expect(events).toEqual(['login']); late.resolve(json(user)); await logout;
  expect(await login).toMatchObject({ code: 'AUTH_REQUIRED' }); expect(authenticated).toBe(false);
  expect(events).toEqual(['login', 'logout']);
});

it.each(['/api/public/events/spring-gathering', '/api/health', '/api/new-public-route'])('allows public %s after failed refresh, while explicitly protected requests remain blocked', async path => {
  const paths: string[] = [];
  const body = { slug: 'spring-gathering', title: 'Public event' };
  vi.stubGlobal('fetch', vi.fn<typeof fetch>(async (input, options) => {
    paths.push(String(input));
    expect(options).not.toHaveProperty('requiresAuth');
    if (input === '/api/auth/csrf') return json({ csrf_token: 'csrf-fixture' });
    if (input === '/api/auth/refresh') return error('AUTH_REFRESH_INVALID');
    return json(body);
  }));
  await expect(client.refreshSession()).rejects.toMatchObject({ code: 'AUTH_REFRESH_INVALID' });
  expect(client.getAuthPhase()).toBe('anonymous');
  expect(await client.apiRequest(path, {})).toEqual(body);
  const sent = paths.length;
  await expect(client.apiRequest('/api/auth/me', { requiresAuth: true })).rejects.toMatchObject({ code: 'AUTH_REQUIRED' });
  // The explicit flag, rather than a URL prefix, owns the auth requirement.
  await expect(client.apiRequest(path, { requiresAuth: true })).rejects.toMatchObject({ code: 'AUTH_REQUIRED' });
  expect(paths).toHaveLength(sent);
  expect(paths).toEqual(['/api/auth/csrf', '/api/auth/refresh', path]);
  expect(client.getAuthPhase()).toBe('anonymous');
});
it('does not infer recovery from a public route returning AUTH_REQUIRED', async () => {
  const paths: string[] = [];
  vi.stubGlobal('fetch', vi.fn<typeof fetch>(async input => { paths.push(String(input)); return error(); }));
  await expect(client.apiRequest('/api/public/events/private-preview', {})).rejects.toMatchObject({ code: 'AUTH_REQUIRED' });
  expect(paths).toEqual(['/api/public/events/private-preview']);
  expect(client.getAuthPhase()).toBe('active');
});
it('allows a pending public response to complete across logout', async () => {
  const response = deferred<Response>();
  vi.stubGlobal('fetch', vi.fn<typeof fetch>(async input => {
    if (input === '/api/auth/csrf') return json({ csrf_token: 'csrf-fixture' });
    if (input === '/api/auth/logout') return new Response(null, { status: 204 });
    return response.promise;
  }));
  const request = client.apiRequest('/api/public/events/spring-gathering', {}).catch(cause => cause);
  await client.logoutSession(); response.resolve(json({ slug: 'spring-gathering' }));
  expect(await request).toEqual({ slug: 'spring-gathering' });
});
