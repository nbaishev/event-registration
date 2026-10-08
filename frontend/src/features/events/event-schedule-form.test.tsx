import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, expect, it, vi } from 'vitest';
import { eventKeys, publicEventKey, type EventResponse } from './api';
import { EventScheduleForm } from './event-schedule-form';
const event: EventResponse = { id: 'event', owner_id: 'owner', title: 'Meetup', description: 'Text', slug: 'meetup', starts_at: '2030-10-10T12:00:37Z', ends_at: '2030-10-10T14:00:42Z', timezone: 'UTC', capacity: 2, status: 'PUBLISHED', schedule_updated_at: '2026-10-09T12:00:00Z', published_at: '2026-10-09T12:00:00Z', cancelled_at: null, created_at: '2026-10-09T12:00:00Z', updated_at: '2026-10-09T12:00:00Z' };
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
afterEach(() => vi.unstubAllGlobals());
function setup(handler: (options?: RequestInit) => Response | Promise<Response>, row = event) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  client.setQueryData(eventKeys.detail(row.owner_id, row.id), row);
  client.setQueryData(eventKeys.mine(row.owner_id), [row]);
  client.setQueryData(publicEventKey(row.slug), row);
  vi.stubGlobal('fetch', vi.fn<typeof fetch>(async (url, options) => url === '/api/auth/csrf' ? json({ csrf_token: 'test-token' }) : handler(options)));
  render(<QueryClientProvider client={client}><EventScheduleForm event={row} /></QueryClientProvider>);
  return client;
}
const save = () => screen.getByRole('button', { name: 'Сохранить расписание' });
it('sends only changed schedule, preserves seconds and updates caches', async () => {
  let body: unknown;
  const client = setup(options => {
    body = JSON.parse(String(options?.body));
    return json({ ...event, ends_at: '2030-10-10T15:00:42Z' });
  });
  expect(save()).toBeDisabled();
  fireEvent.change(screen.getByLabelText('Окончание'), { target: { value: '2030-10-10T15:00' } });
  fireEvent.click(save());
  await waitFor(() => expect(body).toEqual({ ends_at: '2030-10-10T15:00:42.000Z' }));
  await waitFor(() => expect(client.getQueryData<EventResponse>(eventKeys.detail('owner', 'event'))?.ends_at).toBe('2030-10-10T15:00:42Z'));
  expect(client.getQueryState(eventKeys.mine('owner'))?.isInvalidated).toBe(true);
  expect(client.getQueryState(publicEventKey('meetup'))?.isInvalidated).toBe(true);
});
it('disables pending form, prevents duplicate submission and keeps input after error', async () => {
  let release!: (r: Response) => void;
  let count = 0;
  setup(() => { count++; return new Promise(resolve => { release = resolve; }); });
  fireEvent.change(screen.getByLabelText('Окончание'), { target: { value: '2030-10-10T15:00' } });
  fireEvent.click(save());
  await waitFor(() => expect(count).toBe(1));
  expect(screen.getByLabelText('Начало')).toBeDisabled();
  fireEvent.submit(screen.getByLabelText('Начало').closest('form')!);
  expect(count).toBe(1);
  release(json({ error: { code: 'EVENT_ALREADY_STARTED', message: 'internal', details: {} } }, 409));
  expect(await screen.findByRole('alert')).toHaveTextContent('уже началось');
  expect(screen.getByLabelText('Окончание')).toHaveValue('2030-10-10T15:00');
});
it('requires DST choice for changed ambiguous time', async () => {
  let body: unknown;
  setup(options => { body = JSON.parse(String(options?.body)); return json(event); }, { ...event, starts_at: '2030-10-26T12:00:37Z', ends_at: '2030-10-27T06:00:42Z', timezone: 'Europe/Berlin' });
  fireEvent.change(screen.getByLabelText('Начало'), { target: { value: '2030-10-27T02:30' } });
  fireEvent.click(save());
  expect(await screen.findByRole('alert')).toHaveTextContent('смещение');
  fireEvent.change(screen.getByLabelText('Смещение начала'), { target: { value: '2030-10-27T01:30:00.000Z' } });
  fireEvent.click(save());
  await waitFor(() => expect(body).toEqual({ starts_at: '2030-10-27T01:30:37.000Z' }));
});
it.each(['Invalid/Zone', ''])('rejects invalid timezone %s locally', async timezone => {
  setup(() => { throw new Error('Unexpected HTTP request'); });
  fireEvent.change(screen.getByLabelText('Часовой пояс IANA'), { target: { value: timezone } });
  fireEvent.click(save());
  expect(await screen.findByRole('alert')).toHaveTextContent('часовой пояс');
});
