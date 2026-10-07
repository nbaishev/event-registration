import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient } from '@tanstack/react-query';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
let App: typeof import('../../app')['App'];
beforeEach(async () => { vi.resetModules(); App = (await import('../../app')).App; });
afterEach(() => vi.unstubAllGlobals());
const user = { id: '00000000-0000-4000-8000-000000000001', email: 'owner@example.com', created_at: '2026-10-04T12:00:00Z', updated_at: '2026-10-04T12:00:00Z' };
const event = { id: '00000000-0000-4000-8000-000000000002', owner_id: user.id, title: 'Meetup', description: 'Description', slug: 'meetup-abcdef012345', starts_at: '2026-10-04T13:00:00Z', ends_at: '2026-10-04T15:00:00Z', timezone: 'UTC', capacity: 25, status: 'PUBLISHED', schedule_updated_at: user.created_at, published_at: user.created_at, cancelled_at: null, created_at: user.created_at, updated_at: user.created_at };
const success = { status: 'checked_in', registration_id: '00000000-0000-4000-8000-000000000003', event_id: event.id, ticket_code: '7K4P-9Q2M-8RTA', checked_in_at: '2026-10-04T12:00:00Z', participant: { user_id: '00000000-0000-4000-8000-000000000004', email: 'participant@example.com' } };
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const error = (code: string) => json({ error: { code, message: 'diagnostic', details: {} } }, 409);
function setup(handler: (options?: RequestInit) => Response | Promise<Response> = () => json(success), detail = json(event), path = `/organizer/events/${event.id}/check-in`) {
  window.history.replaceState({}, '', path);
  let posts = 0;
  vi.stubGlobal('fetch', vi.fn<typeof fetch>(async (input, options) => {
    if (input === '/api/auth/me') return json(user);
    if (input === '/api/auth/csrf') return json({ csrf_token: 'test-token' });
    if (input === `/api/events/${event.id}`) return detail.clone();
    if (input === `/api/events/${event.id}/check-ins`) { posts++; return handler(options); }
    throw new Error(`Unexpected request: ${String(input)}`);
  }));
  render(<App client={new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: 2, retryDelay: 0 } } })} />);
  return () => posts;
}
async function submit() {
  fireEvent.change(await screen.findByLabelText(/^Код билета/), { target: { value: '7k4p-9q2m-8rta' } });
  fireEvent.click(screen.getByRole('button', { name: 'Отметить участника' }));
}
it('submits once with CSRF, blocks pending and displays participant/time/code', async () => {
  let resolve!: (response: Response) => void;
  const posts = setup(options => {
    expect(options?.method).toBe('POST');
    expect(JSON.parse(String(options?.body))).toEqual({ ticket_code: '7k4p-9q2m-8rta' });
    expect(new Headers(options?.headers).get('X-CSRF-Token')).toBe('test-token');
    return new Promise<Response>(done => { resolve = done; });
  });
  await submit();
  await waitFor(() => expect(posts()).toBe(1));
  expect(screen.getByRole('button', { name: 'Отмечаем…' })).toBeDisabled();
  expect(screen.getByLabelText(/^Код билета/)).toBeDisabled();
  await act(async () => resolve(json(success)));
  expect(await screen.findByText('participant@example.com')).toBeVisible();
  expect(screen.getByText('7K4P-9Q2M-8RTA')).toBeVisible();
  expect(screen.getByText(/12:00/)).toBeVisible();
});
it.each([['TICKET_NOT_FOUND', 'Билет не найден'], ['TICKET_ALREADY_CHECKED_IN', 'уже отмечен'], ['CHECKIN_NOT_OPEN', 'ещё не открыт'], ['EVENT_CANCELLED', 'отменено'], ['EVENT_FINISHED', 'завершилось'], ['EVENT_NOT_OWNER', 'Нет доступа'], ['EVENT_NOT_FOUND', 'не найдено'], ['VALIDATION_ERROR', 'Проверьте код'], ['SERVICE_UNAVAILABLE', 'Не удалось']])('shows safe error %s without retry', async (code, message) => {
  const posts = setup(() => error(code));
  await submit();
  expect(await screen.findByRole('alert')).toHaveTextContent(message);
  expect(posts()).toBe(1);
  expect(screen.queryByText('diagnostic')).not.toBeInTheDocument();
});
it('does not repeat transport failures and removes stale success', async () => {
  let fail = false;
  const posts = setup(() => { if (fail) throw new TypeError('network failed'); return json(success); });
  await submit();
  expect(await screen.findByText('participant@example.com')).toBeVisible();
  fail = true;
  await submit();
  expect(await screen.findByRole('alert')).toHaveTextContent('Не удалось');
  expect(screen.queryByText('participant@example.com')).not.toBeInTheDocument();
  await act(async () => { await new Promise(done => setTimeout(done, 30)); });
  expect(posts()).toBe(2);
});
it.each(['DRAFT', 'CANCELLED'])('handles direct %s route', async status => {
  setup(undefined, json({ ...event, status }));
  expect(await screen.findByRole('alert')).toHaveTextContent(status === 'DRAFT' ? 'ещё не открыт' : 'отменено');
  expect(screen.queryByLabelText(/^Код билета/)).not.toBeInTheDocument();
});
it('handles detail access error', async () => {
  setup(undefined, error('EVENT_NOT_OWNER'));
  expect(await screen.findByRole('alert')).toHaveTextContent('Нет доступа');
});
it('links published detail to check-in', async () => {
  setup(undefined, json(event), `/organizer/events/${event.id}`);
  expect(await screen.findByRole('link', { name: 'Check-in' })).toHaveAttribute('href', `/organizer/events/${event.id}/check-in`);
});
