import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient } from '@tanstack/react-query';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';

import { FakeEventSource } from '../../test-utils/event-source';

let App: typeof import('../../app')['App'];
beforeEach(async () => { vi.resetModules(); FakeEventSource.instances = []; vi.stubGlobal('EventSource', FakeEventSource); App = (await import('../../app')).App; });
afterEach(() => vi.unstubAllGlobals());
const owner = { id: '00000000-0000-4000-8000-000000000001', email: 'owner@example.com', created_at: '2026-10-04T12:00:00Z', updated_at: '2026-10-04T12:00:00Z' };
const event = { id: '00000000-0000-4000-8000-000000000002', owner_id: owner.id, title: 'Statistics meetup', description: 'Description', slug: 'statistics-meetup', starts_at: '2030-10-10T12:00:00Z', ends_at: '2030-10-10T14:00:00Z', timezone: 'UTC', capacity: 7, status: 'PUBLISHED', schedule_updated_at: owner.created_at, published_at: owner.created_at as string | null, cancelled_at: null, created_at: owner.created_at, updated_at: owner.created_at };
const snapshot = { event_id: event.id, capacity: 7, confirmed: 4, waitlist: 2, checked_in: 1, available_slots: 3 };
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const error = (code: string, status = 409) => json({ error: { code, message: 'internal diagnostic', details: {} } }, status);
const detailKey = ['events', owner.id, 'detail', event.id];
const statsKey = ['events', owner.id, 'stats', event.id];
function setup(handler: (input: RequestInfo | URL, options?: RequestInit) => Response | Promise<Response>, detail = event) {
  window.history.replaceState({}, '', `/organizer/events/${event.id}`);
  vi.stubGlobal('fetch', vi.fn<typeof fetch>(async (input, options) => {
    if (input === '/api/auth/me') return json(owner);
    if (input === '/api/auth/csrf') return json({ csrf_token: 'test-token' });
    if (input === `/api/events/${event.id}`) return json(detail);
    return handler(input, options);
  }));
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<App client={client} />);
  return client;
}
function metric(label: string, value: number) {
  expect(within(screen.getByRole('group', { name: label })).getByText(String(value), { exact: true })).toBeVisible();
}
it('shows loading and all five values; manual refresh keeps event cache intact', async () => {
  let release!: (response: Response) => void;
  let reads = 0;
  const client = setup((input, options) => {
    expect(input).toBe(`/api/events/${event.id}/stats`);
    expect(options?.signal).toBeInstanceOf(AbortSignal);
    expect(options?.cache).toBe('no-store');
    return ++reads === 1 ? new Promise<Response>(resolve => { release = resolve; }) : json({ ...snapshot, confirmed: 5, checked_in: 2, available_slots: 2 });
  });
  expect(await screen.findByText('Загружаем статистику…')).toBeVisible();
  expect(screen.getByRole('button', { name: 'Обновить статистику' })).toBeDisabled();
  await act(async () => release(json(snapshot)));
  await screen.findByRole('group', { name: 'Вместимость' });
  metric('Вместимость', 7); metric('Подтверждено', 4); metric('В листе ожидания', 2); metric('Отмечено на входе', 1); metric('Свободных мест', 3);
  fireEvent.click(screen.getByRole('button', { name: 'Обновить статистику' }));
  await waitFor(() => metric('Подтверждено', 5));
  metric('Отмечено на входе', 2); metric('Свободных мест', 2);
  expect(client.getQueryData(detailKey)).toEqual(event);
  expect(client.getQueryData(statsKey)).toEqual({ ...snapshot, confirmed: 5, checked_in: 2, available_slots: 2 });
});
it.each(['EVENT_NOT_OWNER', 'EVENT_NOT_FOUND', 'EVENT_NOT_PUBLISHED', 'SERVICE_UNAVAILABLE'])('offers retry for %s without exposing diagnostics', async code => {
  let failed = true;
  setup(() => failed ? error(code) : json(snapshot));
  const region = await screen.findByRole('region', { name: 'Статистика мероприятия' });
  expect(await within(region).findByRole('alert')).toHaveTextContent(/статистик|доступ|найден|опубликован/);
  expect(screen.queryByText('internal diagnostic')).not.toBeInTheDocument();
  failed = false;
  fireEvent.click(within(region).getByRole('button', { name: 'Повторить' }));
  await waitFor(() => metric('Подтверждено', 4));
});
it('recovers from network failure and handles failed refetch', async () => {
  let failed = true;
  setup(() => { if (failed) throw new TypeError('offline'); return json(snapshot); });
  const region = await screen.findByRole('region', { name: 'Статистика мероприятия' });
  await within(region).findByRole('alert');
  failed = false;
  fireEvent.click(within(region).getByRole('button', { name: 'Повторить' }));
  await waitFor(() => metric('Подтверждено', 4));
  failed = true;
  fireEvent.click(within(region).getByRole('button', { name: 'Обновить статистику' }));
  expect(await within(region).findByRole('alert')).toBeVisible();
});
it('does not request draft stats and mounts dashboard after publication', async () => {
  let reads = 0;
  setup(input => {
    if (String(input).endsWith('/publish')) return json(event);
    if (String(input).endsWith('/stats')) { reads++; return json(snapshot); }
    throw new Error('Unexpected request');
  }, { ...event, status: 'DRAFT', published_at: null });
  await screen.findByRole('button', { name: 'Опубликовать' });
  expect(screen.queryByRole('region', { name: 'Статистика мероприятия' })).not.toBeInTheDocument();
  expect(reads).toBe(0);
  fireEvent.click(screen.getByRole('button', { name: 'Опубликовать' }));
  await waitFor(() => metric('Вместимость', 7));
  expect(reads).toBe(1);
});
it.each(['CANCELLED', 'PUBLISHED'])('shows dashboard for %s ended event', async status => {
  setup(() => json(snapshot), { ...event, status, starts_at: '2020-10-04T10:00:00Z', ends_at: '2020-10-04T12:00:00Z' });
  await waitFor(() => metric('Вместимость', 7));
});
it.each([false, true])('isolates owner cache and aborts delayed response after account switch: loaded=%s', async loaded => {
  let release!: (response: Response) => void;
  let signal: AbortSignal | undefined;
  let reads = 0;
  const client = setup((_input, options) => {
    if (loaded && ++reads === 1) return json(snapshot);
    signal = options?.signal ?? undefined;
    return new Promise<Response>(resolve => { release = resolve; });
  });
  if (loaded) {
    await waitFor(() => metric('Подтверждено', 4));
    fireEvent.click(screen.getByRole('button', { name: 'Обновить статистику' }));
  }
  await waitFor(() => expect(release).toBeDefined());
  const second = { ...owner, id: 'second-owner', email: 'second@example.com' };
  vi.stubGlobal('fetch', vi.fn<typeof fetch>(async input => {
    if (input === '/api/auth/me') return json(second);
    if (input === `/api/events/${event.id}`) return json({ ...event, owner_id: second.id });
    return json({ ...snapshot, capacity: 9, confirmed: 0, waitlist: 0, checked_in: 0, available_slots: 9 });
  }));
  await act(async () => client.setQueryData(['auth', 'me'], second));
  await waitFor(() => metric('Вместимость', 9));
  expect(signal?.aborted).toBe(true);
  await act(async () => release(json(snapshot)));
  metric('Подтверждено', 0); metric('Вместимость', 9);
  expect(client.getQueryData(['events', second.id, 'stats', event.id])).toEqual({ ...snapshot, capacity: 9, confirmed: 0, waitlist: 0, checked_in: 0, available_slots: 9 });
});

it('live signal refetches counters without invalidating event details', async () => {
  let confirmed = 4;
  const client = setup(() => json({ ...snapshot, confirmed }));
  await waitFor(() => metric('Подтверждено', 4));
  expect(FakeEventSource.instances).toHaveLength(1);
  expect(screen.getByText('Подключаемся…')).toBeVisible();
  await act(async () => FakeEventSource.instances[0].open());
  expect(screen.getByText('Обновляется в реальном времени')).toBeVisible();
  confirmed = 5;
  await act(async () => FakeEventSource.instances[0].signal());
  await waitFor(() => metric('Подтверждено', 5));
  expect(client.getQueryState(detailKey)?.isInvalidated).toBe(false);
  await act(async () => FakeEventSource.instances[0].fail());
  expect(screen.getByText('Восстанавливаем соединение…')).toBeVisible();
  metric('Подтверждено', 5);
});
it('terminal reconnect shows access error and a successful manual retry displays snapshot', async () => {
  let forbidden = false;
  setup(input => input === '/api/auth/refresh' ? json(owner) : forbidden ? error('EVENT_NOT_OWNER', 403) : json(snapshot));
  await waitFor(() => metric('Подтверждено', 4));
  forbidden = true;
  await act(async () => FakeEventSource.instances[0].fail());
  await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Нет доступа'), { timeout: 2500 });
  expect(screen.queryByRole('group', { name: 'Подтверждено' })).not.toBeInTheDocument();
  forbidden = false;
  fireEvent.click(screen.getByRole('button', { name: 'Повторить' }));
  await waitFor(() => metric('Подтверждено', 4));
  expect(FakeEventSource.instances).toHaveLength(2);
  await act(async () => FakeEventSource.instances[1].open());
  expect(screen.getByText('Обновляется в реальном времени')).toBeVisible();
});
