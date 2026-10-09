import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient } from '@tanstack/react-query';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { eventKeys, publicEventKey, type EventResponse } from './api';
import { registrationKeys } from '../registrations/api';
let App: typeof import('../../app')['App'];
beforeEach(async () => { vi.resetModules(); App = (await import('../../app')).App; });
afterEach(() => vi.unstubAllGlobals());
const owner = { id: '00000000-0000-4000-8000-000000000001', email: 'owner@example.com', created_at: '2026-10-04T12:00:00Z', updated_at: '2026-10-04T12:00:00Z' };
const event: EventResponse = { id: '00000000-0000-4000-8000-000000000002', owner_id: owner.id, title: 'Conference', description: 'Description', slug: 'conference', starts_at: '2026-10-10T12:00:00Z', ends_at: '2026-10-10T14:00:00Z', timezone: 'UTC', capacity: 1, status: 'PUBLISHED', schedule_updated_at: owner.created_at, published_at: owner.created_at, cancelled_at: null, created_at: owner.created_at, updated_at: owner.created_at };
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
function setup(cancel: (options?: RequestInit) => Response | Promise<Response>, status: EventResponse['status'] = 'PUBLISHED', patch?: (options?: RequestInit) => Response | Promise<Response>) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  client.setQueryData(publicEventKey(event.slug), event);
  client.setQueryData(registrationKeys.mine(owner.id), []);
  client.setQueryData(registrationKeys.detail(owner.id, event.id), null);
  client.setQueryData(eventKeys.mine(owner.id), [event]);
  window.history.replaceState({}, '', `/organizer/events/${event.id}`);
  vi.stubGlobal('fetch', vi.fn<typeof fetch>(async (input, options) => {
    if (input === '/api/auth/me') return json(owner);
    if (input === '/api/auth/csrf') return json({ csrf_token: 'test-token' });
    if (input === `/api/events/${event.id}/cancel`) return cancel(options);
    if (input === `/api/events/${event.id}/stats`) return json({ event_id: event.id, capacity: 1, confirmed: 0, waitlist: 0, checked_in: 0, available_slots: 1 });
    if (input === `/api/events/${event.id}` && options?.method === 'PATCH' && patch) return patch(options);
    if (input === `/api/events/${event.id}`) return json({ ...event, status });
    throw new Error('Unexpected request');
  }));
  render(<App client={client} />);
  return client;
}
async function openDialog() {
  fireEvent.click(await screen.findByRole('button', { name: 'Отменить мероприятие' }));
  return within(await screen.findByRole('dialog'));
}
it('requires confirmation, prevents duplicate pending request, updates caches and removes actions', async () => {
  let resolve!: (response: Response) => void;
  let calls = 0;
  const client = setup(options => {
    calls++;
    expect(options?.method).toBe('POST');
    expect(options?.body).toBeUndefined();
    expect(new Headers(options?.headers).get('X-CSRF-Token')).toBe('test-token');
    return new Promise<Response>(done => { resolve = done; });
  });
  const dialog = await openDialog();
  expect(calls).toBe(0);
  fireEvent.click(dialog.getByRole('button', { name: 'Подтвердить отмену' }));
  await waitFor(() => expect(calls).toBe(1));
  expect(dialog.getByRole('button', { name: 'Отменяем…' })).toBeDisabled();
  fireEvent.click(dialog.getByRole('button', { name: 'Отменяем…' }));
  expect(calls).toBe(1);
  const saved = { ...event, status: 'CANCELLED' as const, cancelled_at: '2026-10-09T12:00:00Z', updated_at: '2026-10-09T12:00:00Z' };
  await act(async () => resolve(json(saved)));
  expect(await screen.findByText('Отменено')).toBeVisible();
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
  expect(screen.queryByRole('link', { name: 'Check-in' })).not.toBeInTheDocument();
  expect(screen.queryByRole('heading', { name: 'Изменить расписание' })).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Сохранить количество мест' })).not.toBeInTheDocument();
  expect(client.getQueryData(eventKeys.detail(owner.id, event.id))).toEqual(saved);
  for (const key of [eventKeys.mine(owner.id), publicEventKey(event.slug), registrationKeys.mine(owner.id), registrationKeys.detail(owner.id, event.id)]) {
    expect(client.getQueryState(key)?.isInvalidated).toBe(true);
  }
});
it('dismisses the confirmation without a request', async () => {
  const cancel = vi.fn(() => json(event));
  setup(cancel);
  const dialog = await openDialog();
  fireEvent.click(dialog.getByRole('button', { name: 'Назад' }));
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
  expect(cancel).not.toHaveBeenCalled();
});
it.each([
  ['EVENT_NOT_OWNER', 403, 'Нет доступа'],
  ['EVENT_NOT_FOUND', 404, 'Мероприятие не найдено'],
  ['EVENT_CANCELLED', 409, 'уже отменено'],
  ['EVENT_NOT_PUBLISHED', 409, 'не опубликовано'],
  ['EVENT_ALREADY_STARTED', 409, 'уже началось'],
  ['SERVICE_UNAVAILABLE', 503, 'Не удалось отменить'],
] as const)('shows safe cancellation error %s and allows retry', async (code, status, message) => {
  setup(() => json({ error: { code, message: 'private diagnostic', details: {} } }, status));
  const dialog = await openDialog();
  fireEvent.click(dialog.getByRole('button', { name: 'Подтвердить отмену' }));
  expect(await dialog.findByRole('alert')).toHaveTextContent(message);
  expect(dialog.getByRole('button', { name: 'Подтвердить отмену' })).toBeEnabled();
  expect(screen.queryByText('private diagnostic')).not.toBeInTheDocument();
});
it.each(['DRAFT', 'CANCELLED'] as const)('hides cancellation for %s', async status => {
  setup(() => json(event), status);
  await screen.findByRole('heading', { name: event.title });
  expect(screen.queryByRole('button', { name: 'Отменить мероприятие' })).not.toBeInTheDocument();
});

it.each(['schedule', 'capacity'] as const)('keeps cancelled state when an earlier %s PATCH response arrives late', async form => {
  let release!: (response: Response) => void;
  let patchCalls = 0;
  const saved = { ...event, status: 'CANCELLED' as const, cancelled_at: '2026-10-09T12:00:00Z', updated_at: '2026-10-09T12:00:00Z' };
  const client = setup(() => json(saved), 'PUBLISHED', () => {
    patchCalls++;
    return new Promise<Response>(resolve => { release = resolve; });
  });
  await screen.findByRole('heading', { name: event.title });
  if (form === 'schedule') {
    fireEvent.change(screen.getByLabelText('Окончание', { exact: true }), { target: { value: '2026-10-10T15:00' } });
    fireEvent.click(screen.getByRole('button', { name: 'Сохранить расписание' }));
  } else {
    fireEvent.change(screen.getByLabelText('Количество мест', { exact: true }), { target: { value: '2' } });
    fireEvent.click(screen.getByRole('button', { name: 'Сохранить количество мест' }));
  }
  await waitFor(() => expect(patchCalls).toBe(1));
  const dialog = await openDialog();
  fireEvent.click(dialog.getByRole('button', { name: 'Подтвердить отмену' }));
  expect(await screen.findByText('Отменено')).toBeVisible();
  await act(async () => release(json({ ...event, capacity: 2, ends_at: '2026-10-10T15:00:00Z' })));
  expect(client.getQueryData(eventKeys.detail(owner.id, event.id))).toEqual(saved);
  expect(screen.getByText('Отменено')).toBeVisible();
  expect(screen.queryByRole('link', { name: 'Check-in' })).not.toBeInTheDocument();
  expect(screen.queryByRole('heading', { name: 'Изменить расписание' })).not.toBeInTheDocument();
  expect(screen.queryByRole('heading', { name: 'Изменить количество мест' })).not.toBeInTheDocument();
});
