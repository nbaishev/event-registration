import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient } from '@tanstack/react-query';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
let App: typeof import('../../app')['App'];
beforeEach(async () => { vi.resetModules(); App = (await import('../../app')).App; });
afterEach(() => vi.unstubAllGlobals());
const user = { id: 'user-one', email: 'participant@example.com', created_at: '2026-10-04T12:00:00Z', updated_at: '2026-10-04T12:00:00Z' };
const event = { id: 'event-one', title: 'Meetup', slug: 'meetup', starts_at: '2099-10-10T12:00:00Z', ends_at: '2099-10-10T14:00:00Z', timezone: 'Asia/Almaty', status: 'PUBLISHED' };
const registration = { id: 'registration-one', event_id: event.id, user_id: user.id, status: 'CONFIRMED', confirmed_at: user.created_at, waitlisted_at: null, cancelled_at: null, waitlist_position: null, ticket_code: '7K4P-9Q2M-8RTA', checked_in_at: null };
const item = { event, registration };
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const error = (code: string, status: number) => json({ error: { code, message: 'diagnostic', details: {} } }, status);
function setup(handler: (input: RequestInfo | URL, options?: RequestInit) => Response | Promise<Response>, session = json(user)) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  window.history.replaceState({}, '', '/me/registrations');
  vi.stubGlobal('fetch', vi.fn<typeof fetch>(async (input, options) => {
    if (input === '/api/auth/me') return session.clone();
    if (input === '/api/auth/csrf') return json({ csrf_token: 'test-token' });
    return handler(input, options);
  }));
  render(<App client={client} />);
  return client;
}
it('shows own tickets, global waitlist position, cancelled history and timezone', async () => {
  setup(() => json([item, { event: { ...event, id: 'second', title: 'Queue' }, registration: { ...registration, id: 'second', status: 'WAITLIST', ticket_code: null, waitlist_position: 3 } }, { event: { ...event, id: 'third', title: 'History' }, registration: { ...registration, id: 'third', status: 'CANCELLED', ticket_code: null } }]));
  expect(await screen.findByText('7K4P-9Q2M-8RTA')).toBeVisible();
  expect(screen.getByText('Место в очереди: 3')).toBeVisible();
  expect(screen.getByText('Регистрация отменена')).toBeVisible();
  expect(screen.getByRole('link', { name: 'Meetup' })).toHaveAttribute('href', '/events/meetup');
  expect(screen.getAllByText(/Asia\/Almaty/).length).toBe(3);
});
it('shows loading, error retry, and empty state', async () => {
  let resolve!: (value: Response) => void;
  let reads = 0;
  setup(() => ++reads === 1 ? new Promise<Response>(r => { resolve = r; }) : json([]));
  expect(await screen.findByText('Загружаем регистрации…')).toBeVisible();
  await act(async () => resolve(error('SERVICE_UNAVAILABLE', 503)));
  fireEvent.click(await screen.findByRole('button', { name: 'Повторить' }));
  expect(await screen.findByText('У вас пока нет регистраций')).toBeVisible();
});
it('redirects anonymous direct navigation to login', async () => {
  setup(() => error('AUTH_REFRESH_INVALID', 401), error('AUTH_REQUIRED', 401));
  expect(await screen.findByRole('heading', { name: 'Войти' })).toBeVisible();
  expect(window.location.pathname).toBe('/login');
});
it('cancel success survives delayed list and own detail GETs', async () => {
  let resolveList!: (value: Response) => void;
  let resolveOwn!: (value: Response) => void;
  let reads = 0;
  const cancelled = { ...registration, status: 'CANCELLED', ticket_code: null, confirmed_at: null, cancelled_at: user.created_at };
  const client = setup((input, options) => {
    if (options?.method === 'DELETE') return json(cancelled);
    if (String(input).endsWith('/my-registration')) return new Promise<Response>(r => { resolveOwn = r; });
    if (input === '/api/me/registrations') return ++reads === 1 ? json([item]) : reads === 2 ? new Promise<Response>(r => { resolveList = r; }) : json([{ event, registration: cancelled }]);
    throw new Error('unexpected request');
  });
  await screen.findByText('7K4P-9Q2M-8RTA');
  void client.invalidateQueries({ queryKey: ['registrations', user.id, 'mine'] });
  void client.fetchQuery({ queryKey: ['registrations', user.id, 'detail', event.id], queryFn: ({ signal }) => import('./api').then(api => api.getMyRegistration(event.id, signal)) }).catch(() => {});
  await waitFor(() => { expect(reads).toBe(2); expect(resolveOwn).toBeDefined(); });
  fireEvent.click(screen.getByRole('button', { name: 'Отменить регистрацию' }));
  expect(await screen.findByText('Регистрация отменена')).toBeVisible();
  await act(async () => { resolveList(json([item])); resolveOwn(json(registration)); });
  expect(screen.queryByText('7K4P-9Q2M-8RTA')).toBeNull();
  expect(client.getQueryData(['registrations', user.id, 'detail', event.id])).toEqual(cancelled);
});
it('account switch cannot show previous list even when the old GET resolves late', async () => {
  let resolve!: (value: Response) => void;
  const client = setup(() => new Promise<Response>(r => { resolve = r; }));
  await screen.findByText('Загружаем регистрации…');
  const second = { ...user, id: 'user-two', email: 'second@example.com' };
  vi.stubGlobal('fetch', vi.fn<typeof fetch>(async input => input === '/api/auth/me' ? json(second) : json([])));
  await act(async () => client.setQueryData(['auth', 'me'], second));
  expect(await screen.findByText('У вас пока нет регистраций')).toBeVisible();
  await act(async () => resolve(json([item])));
  expect(screen.queryByText('7K4P-9Q2M-8RTA')).toBeNull();
});
it('recovers expired access before loading own registrations', async () => {
  let reads = 0;
  setup(input => {
    if (input === '/api/auth/refresh') return json(user);
    if (input === '/api/me/registrations') return ++reads === 1 ? error('AUTH_REQUIRED', 401) : json([item]);
    throw new Error('unexpected request');
  });
  expect(await screen.findByText('7K4P-9Q2M-8RTA')).toBeVisible();
  expect(window.location.pathname).toBe('/me/registrations');
});
it('keeps the ticket on cancellation error and allows explicit status recovery', async () => {
  setup((_input, options) => options?.method === 'DELETE' ? error('EVENT_ALREADY_STARTED', 409) : json([item]));
  fireEvent.click(await screen.findByRole('button', { name: 'Отменить регистрацию' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('Мероприятие уже началось');
  expect(screen.getByText('7K4P-9Q2M-8RTA')).toBeVisible();
  fireEvent.click(screen.getByRole('button', { name: 'Проверить текущий статус' }));
  expect(await screen.findByText('Регистрация подтверждена')).toBeVisible();
});
