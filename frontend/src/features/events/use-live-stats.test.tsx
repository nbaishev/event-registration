import { act, cleanup, renderHook } from '@testing-library/react';
import { QueryClient, QueryClientProvider, QueryObserver } from '@tanstack/react-query';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import type { PropsWithChildren } from 'react';
import { FakeEventSource } from '../../test-utils/event-source';

let useLiveStats: typeof import('./use-live-stats')['useLiveStats'];
let api: typeof import('../../api/client');
const owner = { id: 'owner', email: 'owner@example.com', created_at: '2026-10-04T12:00:00Z', updated_at: '2026-10-04T12:00:00Z' };
const snapshot = { event_id: 'event', capacity: 7, confirmed: 4, waitlist: 2, checked_in: 1, available_slots: 3 };
const key = ['events', 'owner', 'stats', 'event'];
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const error = (status: number, code: string) => json({ error: { code, message: 'diagnostic', details: {} } }, status);
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>(done => { resolve = done; });
  return { promise, resolve };
}
let requests: string[];
let handler: (path: string, options?: RequestInit) => Response | Promise<Response>;
beforeEach(async () => {
  vi.resetModules(); vi.useFakeTimers(); FakeEventSource.instances = []; requests = [];
  vi.stubGlobal('EventSource', FakeEventSource);
  handler = path => path === '/api/auth/csrf' ? json({ csrf_token: 'test-token' }) : path === '/api/auth/refresh' ? json(owner) : json(snapshot);
  vi.stubGlobal('fetch', vi.fn<typeof fetch>(async (input, options) => {
    const path = String(input); requests.push(path); return handler(path, options);
  }));
  api = await import('../../api/client');
  useLiveStats = (await import('./use-live-stats')).useLiveStats;
});
afterEach(() => { cleanup(); vi.useRealTimers(); vi.unstubAllGlobals(); });
async function tick(ms = 0) { await act(async () => { await vi.advanceTimersByTimeAsync(ms); }); }
function setup() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  client.setQueryData(key, snapshot);
  client.setQueryData(['events', 'owner', 'detail', 'event'], { title: 'unchanged' });
  const hook = renderHook(({ ownerId, eventId }) => useLiveStats(ownerId, eventId), {
    initialProps: { ownerId: 'owner', eventId: 'event' },
    wrapper: ({ children }: PropsWithChildren) => <QueryClientProvider client={client}>{children}</QueryClientProvider>,
  });
  return { ...hook, client };
}
it('test_signal_refetches_exact_stats: open and signals refetch snapshot only', async () => {
  const { client, result } = setup();
  const observer = new QueryObserver(client, { queryKey: key, queryFn: () => api.apiRequest('/api/events/event/stats', { requiresAuth: true }), staleTime: Infinity });
  const unsubscribe = observer.subscribe(() => undefined);
  expect(FakeEventSource.instances[0].url).toBe('/api/events/event/stats/stream');
  await act(async () => FakeEventSource.instances[0].open()); await tick();
  expect(requests).toEqual(['/api/events/event/stats']);
  handler = () => json({ ...snapshot, confirmed: 5 });
  await act(async () => FakeEventSource.instances[0].signal()); await tick();
  expect(client.getQueryData(key)).toEqual({ ...snapshot, confirmed: 5 });
  expect(client.getQueryState(['events', 'owner', 'detail', 'event'])?.isInvalidated).toBe(false);
  expect(result.current).toBe('live'); unsubscribe();
});
it('test_reconnect_refresh_open_refetch_order: validate before stream; invalidate after open', async () => {
  const refresh = deferred<Response>(), validation = deferred<Response>();
  handler = path => path === '/api/auth/csrf' ? json({ csrf_token: 'test-token' }) : path === '/api/auth/refresh' ? refresh.promise : validation.promise;
  const { result, client } = setup();
  const first = FakeEventSource.instances[0];
  await act(async () => first.fail()); expect(first.closed).toBe(true);
  await tick(999); expect(requests).toEqual([]);
  await tick(1); expect(requests).toEqual(['/api/auth/csrf', '/api/auth/refresh']);
  expect(FakeEventSource.instances).toHaveLength(1);
  await act(async () => refresh.resolve(json(owner)));
  expect(requests.at(-1)).toBe('/api/events/event/stats');
  expect(FakeEventSource.instances).toHaveLength(1);
  await act(async () => validation.resolve(json(snapshot)));
  expect(FakeEventSource.instances).toHaveLength(2);
  expect(client.getQueryState(key)?.isInvalidated).toBe(false);
  await act(async () => FakeEventSource.instances[1].open());
  expect(client.getQueryState(key)?.isInvalidated).toBe(true);
  expect(result.current).toBe('live');
});
it('test_backoff_and_open_timeout: one loop caps delay and successful open resets it', async () => {
  const { result } = setup();
  await tick(10000); expect(FakeEventSource.instances[0].closed).toBe(true);
  for (const [index, delay] of [1000, 2000, 4000, 8000, 16000, 30000, 30000].entries()) {
    await tick(delay - 1); expect(FakeEventSource.instances).toHaveLength(index + 1);
    await tick(1); expect(FakeEventSource.instances).toHaveLength(index + 2);
    const stream = FakeEventSource.instances.at(-1)!;
    await act(async () => { stream.fail(); stream.fail(); });
  }
  await tick(30000);
  const stream = FakeEventSource.instances.at(-1)!;
  await act(async () => stream.open()); expect(result.current).toBe('live');
  await act(async () => stream.fail()); await tick(1000);
  expect(FakeEventSource.instances).toHaveLength(10);
});
it('times out a reconnect attempt without a duplicate retry from its late error', async () => {
  setup(); await act(async () => FakeEventSource.instances[0].fail()); await tick(1000);
  const second = FakeEventSource.instances[1]; await tick(10000);
  expect(second.closed).toBe(true);
  await act(async () => second.fail()); await tick(1999);
  expect(FakeEventSource.instances).toHaveLength(2);
  await tick(1); expect(FakeEventSource.instances).toHaveLength(3);
});
it('test_refresh_401_stops: existing auth session loss fires and retries stop', async () => {
  const loss = vi.fn(); api.subscribeSessionLoss(loss);
  handler = path => path === '/api/auth/csrf' ? json({ csrf_token: 'test-token' }) : error(401, 'AUTH_REFRESH_INVALID');
  const { result } = setup(); await act(async () => FakeEventSource.instances[0].fail()); await tick(1000);
  expect(loss).toHaveBeenCalledOnce(); expect(api.getAuthPhase()).toBe('anonymous');
  await tick(120000); expect(FakeEventSource.instances).toHaveLength(1); expect(result.current).not.toBe('live');
});
it.each([[403, 'EVENT_NOT_OWNER'], [404, 'EVENT_NOT_FOUND'], [409, 'EVENT_NOT_PUBLISHED']] as const)('test_forbidden_stats_stops: %s %s preserves dashboard error', async (status, code) => {
  handler = path => path === '/api/auth/csrf' ? json({ csrf_token: 'test-token' }) : path === '/api/auth/refresh' ? json(owner) : error(status, code);
  const { result, client } = setup(); await act(async () => FakeEventSource.instances[0].fail()); await tick(1000);
  expect(result.current).toBe('error');
  expect(client.getQueryState(key)?.error).toMatchObject({ status, code });
  await tick(120000); expect(FakeEventSource.instances).toHaveLength(1);
});
it('transient refresh and validation errors preserve current snapshot and retry', async () => {
  let failures = 0;
  handler = path => path === '/api/auth/csrf' ? json({ csrf_token: 'test-token' }) : ++failures <= 2 ? error(503, 'SERVICE_UNAVAILABLE') : path === '/api/auth/refresh' ? json(owner) : json(snapshot);
  const { client, result } = setup(); await act(async () => FakeEventSource.instances[0].fail());
  await tick(1000); await tick(2000);
  expect(client.getQueryData(key)).toEqual(snapshot); expect(result.current).toBe('reconnecting');
  await tick(4000); expect(FakeEventSource.instances).toHaveLength(2);
});
it('test_cleanup_blocks_late_callbacks: unmount during refresh cannot open stream', async () => {
  const pending = deferred<Response>();
  handler = path => path === '/api/auth/csrf' ? json({ csrf_token: 'test-token' }) : pending.promise;
  const { unmount, client } = setup(); const old = FakeEventSource.instances[0];
  const lateOpen = old.onopen!, lateError = old.onerror!;
  await act(async () => old.fail()); await tick(1000); unmount();
  await act(async () => { pending.resolve(json(owner)); lateOpen(); lateError(); old.signal(); }); await tick(120000);
  expect(FakeEventSource.instances).toHaveLength(1); expect(client.getQueryState(key)?.isInvalidated).toBe(false);
});
it('aborts validation on navigation and ignores its late terminal response', async () => {
  const pending = deferred<Response>(); let signal: AbortSignal | undefined;
  handler = (path, options) => {
    if (path === '/api/auth/csrf') return json({ csrf_token: 'test-token' });
    if (path === '/api/auth/refresh') return json(owner);
    signal = options?.signal ?? undefined; return pending.promise;
  };
  const { rerender, client, result } = setup(); await act(async () => FakeEventSource.instances[0].fail()); await tick(1000);
  rerender({ ownerId: 'new-owner', eventId: 'new-event' }); expect(signal?.aborted).toBe(true);
  await act(async () => pending.resolve(error(403, 'EVENT_NOT_OWNER')));
  expect(FakeEventSource.instances).toHaveLength(2); expect(result.current).toBe('connecting');
  expect(client.getQueryState(key)?.error).toBeNull();
});
it('logout closes stream immediately and late callbacks cannot affect cache', async () => {
  setup(); const stream = FakeEventSource.instances[0];
  const lateOpen = stream.onopen!;
  await act(async () => { await api.logoutSession(); lateOpen(); stream.signal(); });
  expect(stream.closed).toBe(true); await tick(120000); expect(FakeEventSource.instances).toHaveLength(1);
});
it('test_concurrent_http_and_sse_share_refresh: real HTTP client uses one flight', async () => {
  const pending = deferred<Response>(); let protectedReads = 0;
  handler = path => {
    if (path === '/api/auth/csrf') return json({ csrf_token: 'test-token' });
    if (path === '/api/auth/refresh') return pending.promise;
    if (path === '/api/protected' && ++protectedReads === 1) return error(401, 'AUTH_REQUIRED');
    return json(snapshot);
  };
  setup(); await act(async () => FakeEventSource.instances[0].fail()); await tick(1000);
  const http = api.apiRequest('/api/protected', { requiresAuth: true }); await tick();
  expect(requests.filter(path => path === '/api/auth/refresh')).toHaveLength(1);
  await act(async () => { pending.resolve(json(owner)); await http; });
  expect(protectedReads).toBe(2); expect(FakeEventSource.instances).toHaveLength(2);
});
it('terminal validation cancels outstanding stats refetch so late success cannot erase access error', async () => {
  const pending = deferred<typeof snapshot>();
  handler = path => path === '/api/auth/csrf' ? json({ csrf_token: 'test-token' }) : path === '/api/auth/refresh' ? json(owner) : error(403, 'EVENT_NOT_OWNER');
  const { client } = setup();
  const observer = new QueryObserver(client, { queryKey: key, queryFn: () => pending.promise, staleTime: Infinity });
  const unsubscribe = observer.subscribe(() => undefined);
  void observer.refetch();
  await act(async () => FakeEventSource.instances[0].fail()); await tick(1000);
  expect(client.getQueryState(key)?.error).toMatchObject({ code: 'EVENT_NOT_OWNER' });
  await act(async () => pending.resolve(snapshot)); await tick();
  expect(client.getQueryState(key)?.error).toMatchObject({ code: 'EVENT_NOT_OWNER' });
  unsubscribe();
});
