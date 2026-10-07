import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient } from '@tanstack/react-query';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { eventKeys, publicEventKey, type EventResponse } from './api';

let App: typeof import('../../app')['App'];
beforeEach(async () => { vi.resetModules(); App = (await import('../../app')).App; });
afterEach(() => vi.unstubAllGlobals());
const owner = { id: '00000000-0000-4000-8000-000000000001', email: 'owner@example.com', created_at: '2026-10-04T12:00:00Z', updated_at: '2026-10-04T12:00:00Z' };
const event: EventResponse = { id: '00000000-0000-4000-8000-000000000002', owner_id: owner.id, title: 'Capacity meetup', description: 'Description', slug: 'capacity-meetup', starts_at: '2030-10-10T12:00:00Z', ends_at: '2030-10-10T14:00:00Z', timezone: 'UTC', capacity: 2, status: 'PUBLISHED', schedule_updated_at: owner.created_at, published_at: owner.created_at, cancelled_at: null, created_at: owner.created_at, updated_at: owner.created_at };
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const key = eventKeys.detail(owner.id, event.id);
function setup(handler: (input: RequestInfo | URL, options?: RequestInit) => Response | Promise<Response>, client = new QueryClient({ defaultOptions: { queries: { retry: false } } })) {
  window.history.replaceState({}, '', `/organizer/events/${event.id}`);
  vi.stubGlobal('fetch', vi.fn<typeof fetch>(async (input, options) => {
    if (input === '/api/auth/me') return json(owner);
    if (input === '/api/auth/csrf') return json({ csrf_token: 'test-token' });
    return handler(input, options);
  }));
  render(<App client={client} />);
  return client;
}
const input = () => screen.getByRole('spinbutton', { name: 'Количество мест' });
const save = () => screen.getByRole('button', { name: 'Сохранить количество мест' });

it('prefills published capacity and sends only capacity with CSRF; updates detail and invalidates list/public', async () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  client.setQueryData(eventKeys.mine(owner.id), [event]);
  client.setQueryData(publicEventKey(event.slug), event);
  let body: unknown;
  setup((url, options) => {
    if (options?.method === 'PATCH') {
      body = JSON.parse(String(options.body));
      expect(new Headers(options.headers).get('X-CSRF-Token')).toBe('test-token');
      return json({ ...event, capacity: 4 });
    }
    expect(url).toBe(`/api/events/${event.id}`);
    return json(event);
  }, client);
  await screen.findByRole('heading', { name: event.title });
  expect(input()).toHaveValue(2);
  expect(save()).toBeDisabled();
  fireEvent.change(input(), { target: { value: '4' } });
  fireEvent.click(save());
  await screen.findByText('Количество мест: 4');
  expect(body).toEqual({ capacity: 4 });
  expect(input()).toHaveValue(4);
  expect(save()).toBeDisabled();
  expect(client.getQueryData<EventResponse>(key)?.capacity).toBe(4);
  expect(client.getQueryState(eventKeys.mine(owner.id))?.isInvalidated).toBe(true);
  expect(client.getQueryState(publicEventKey(event.slug))?.isInvalidated).toBe(true);
});

it.each([
  ['CAPACITY_BELOW_CONFIRMED', 'подтверждённых участников'],
  ['EVENT_ALREADY_STARTED', 'уже началось'],
  ['EVENT_CANCELLED', 'отменено'],
  ['EVENT_NOT_EDITABLE', 'Нельзя изменить'],
  ['EVENT_NOT_OWNER', 'Нет доступа'],
  ['EVENT_NOT_FOUND', 'не найдено'],
  ['VALIDATION_ERROR', 'целое число'],
  ['SERVICE_UNAVAILABLE', 'Повторите'],
])('keeps input and offers retry after %s', async (code, message) => {
  let failed = true;
  setup((_url, options) => options?.method === 'PATCH' ? failed ? json({ error: { code, message: 'internal diagnostic', details: {} } }, 409) : json({ ...event, capacity: 3 }) : json(event));
  await screen.findByRole('heading', { name: event.title });
  fireEvent.change(input(), { target: { value: '3' } });
  fireEvent.click(save());
  expect(await screen.findByRole('alert')).toHaveTextContent(message);
  expect(screen.queryByText('internal diagnostic')).not.toBeInTheDocument();
  expect(input()).toHaveValue(3);
  expect(screen.getByText('Количество мест: 2')).toBeVisible();
  expect(save()).toBeEnabled();
  failed = false;
  fireEvent.click(save());
  await screen.findByText('Количество мест: 3');
});

it.each(['', '0', '-1', '1.5', '2147483648'])('blocks invalid capacity %s locally', async value => {
  setup(() => json(event));
  await screen.findByRole('heading', { name: event.title });
  fireEvent.change(input(), { target: { value } });
  fireEvent.submit(save().closest('form')!);
  expect(await screen.findByRole('alert')).toHaveTextContent('целое число');
  expect(vi.mocked(fetch).mock.calls.some(([, options]) => options?.method === 'PATCH')).toBe(false);
});

it('does not submit an unchanged value even through form submission', async () => {
  setup(() => json(event));
  await screen.findByRole('heading', { name: event.title });
  fireEvent.submit(save().closest('form')!);
  expect(vi.mocked(fetch).mock.calls.some(([, options]) => options?.method === 'PATCH')).toBe(false);
});

it.each([false, true])('refreshes pristine baseline while preserving dirty input: dirty=%s', async dirty => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  setup(() => json(event), client);
  await screen.findByRole('heading', { name: event.title });
  if (dirty) fireEvent.change(input(), { target: { value: '5' } });
  act(() => { client.setQueryData(key, { ...event, capacity: 4 }); });
  await screen.findByText('Количество мест: 4');
  expect(input()).toHaveValue(dirty ? 5 : 4);
  if (dirty) fireEvent.change(input(), { target: { value: '4' } });
  expect(save()).toBeDisabled();
});

it('capacity success survives delayed detail GET', async () => {
  let reads = 0;
  let release!: (response: Response) => void;
  const oldRead = new Promise<Response>(resolve => { release = resolve; });
  const client = setup((_url, options) => options?.method === 'PATCH' ? json({ ...event, capacity: 4 }) : ++reads === 1 ? json(event) : oldRead);
  await screen.findByRole('heading', { name: event.title });
  let refetch!: Promise<void>;
  act(() => { refetch = client.refetchQueries({ queryKey: key, exact: true }); });
  await waitFor(() => expect(reads).toBe(2));
  fireEvent.change(input(), { target: { value: '4' } });
  fireEvent.click(save());
  await screen.findByText('Количество мест: 4');
  await act(async () => { release(json(event)); await refetch; });
  expect(client.getQueryData<EventResponse>(key)?.capacity).toBe(4);
  expect(input()).toHaveValue(4);
  expect(screen.getByText('Количество мест: 4')).toBeVisible();
});

it('disables the form while saving and prevents duplicate submission', async () => {
  let release!: (response: Response) => void;
  let patches = 0;
  setup((_url, options) => {
    if (options?.method !== 'PATCH') return json(event);
    patches++;
    return new Promise<Response>(resolve => { release = resolve; });
  });
  await screen.findByRole('heading', { name: event.title });
  fireEvent.change(input(), { target: { value: '4' } });
  fireEvent.click(save());
  await waitFor(() => expect(patches).toBe(1));
  expect(input()).toBeDisabled();
  fireEvent.submit(input().closest('form')!);
  expect(patches).toBe(1);
  release(json({ ...event, capacity: 4 }));
  await screen.findByText('Количество мест: 4');
});

it.each(['DRAFT', 'CANCELLED'] as const)('hides capacity control for %s', async status => {
  setup(() => json({ ...event, status }));
  await screen.findByRole('heading', { name: event.title });
  expect(screen.queryByRole('spinbutton')).not.toBeInTheDocument();
});
