import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient } from '@tanstack/react-query';
import { beforeEach, afterEach, expect, it, vi } from 'vitest';
import { eventKeys } from './api';
let App: typeof import('../../app')['App'];
beforeEach(async () => { vi.resetModules(); App = (await import('../../app')).App; });
afterEach(() => vi.unstubAllGlobals());
const user = { id: '00000000-0000-4000-8000-000000000001', email: 'owner@example.com', created_at: '2026-10-04T12:00:00Z', updated_at: '2026-10-04T12:00:00Z' };
const event = { id: '00000000-0000-4000-8000-000000000002', owner_id: user.id, title: 'Meetup <script>bad()</script>', description: '<b>Plain description</b>', slug: 'meetup-abcdef012345', starts_at: '2026-10-10T13:30:00Z', ends_at: '2026-10-10T15:30:00Z', timezone: 'Asia/Almaty', capacity: 25, status: 'DRAFT', schedule_updated_at: user.created_at, published_at: null, cancelled_at: null, created_at: user.created_at, updated_at: user.created_at };
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const error = (code: string, status = 422) => json({ error: { code, message: 'server diagnostic', details: {} } }, status);
function setup(path: string, handler?: (input: RequestInfo | URL, options?: RequestInit) => Response | Promise<Response>, client = new QueryClient({ defaultOptions: { queries: { retry: false } } })) {
  window.history.replaceState({}, '', path);
  vi.stubGlobal('fetch', vi.fn<typeof fetch>(async (input, options) => {
    if (input === '/api/auth/me') return json(user);
    if (input === '/api/auth/csrf') return json({ csrf_token: 'test-token' });
    if (handler) return handler(input, options);
    if (input === '/api/events/mine') return json([event]);
    if (input === `/api/events/${event.id}`) return json(event);
    throw new Error('Unexpected request');
  }));
  render(<App client={client} />);
}
async function fill(local = '2026-10-10T18:30', zone = 'Asia/Almaty', end = '2026-10-10T20:30') {
  await screen.findByRole('heading', { name: 'Создать мероприятие' });
  for (const [label, value] of [
    [/^Название/, 'Meetup'], [/^Описание/, 'Plain description'], [/^Начало/, local],
    [/^Окончание/, end], [/^Часовой пояс/, zone], [/^Количество мест/, '25'],
  ] as const) fireEvent.change(screen.getByLabelText(label), { target: { value } });
}
it('creates with CSRF and UTC instants, then shows saved safe text details', async () => {
  setup('/organizer/events/new', (input, options) => {
    if (input === '/api/events') {
      expect(JSON.parse(String(options?.body))).toEqual({ title: 'Meetup', description: 'Plain description', starts_at: '2026-10-10T13:30:00.000Z', ends_at: '2026-10-10T15:30:00.000Z', timezone: 'Asia/Almaty', capacity: 25 });
      expect(new Headers(options?.headers).get('X-CSRF-Token')).toBe('test-token');
      return json(event, 201);
    }
    return json(event);
  });
  await fill();
  fireEvent.click(screen.getByRole('button', { name: 'Создать черновик' }));
  expect(await screen.findByRole('heading', { name: event.title })).toBeVisible();
  expect(screen.getByText(event.description)).toBeVisible();
  expect(document.querySelector('script')).toBeNull();
  expect(document.querySelector('b')).toBeNull();
  expect(screen.getByText(/18:30/)).toBeVisible();
  expect(window.location.pathname).toBe(`/organizer/events/${event.id}`);
});
it('blocks nonexistent DST time before submitting', async () => {
  setup('/organizer/events/new');
  await fill('2027-03-14T02:30', 'America/New_York', '2027-03-14T04:00');
  fireEvent.click(screen.getByRole('button', { name: 'Создать черновик' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('не существует');
  expect(window.location.pathname).toBe('/organizer/events/new');
});
it('requires explicit offset for ambiguous time and submits the selected instant', async () => {
  let saved = false;
  setup('/organizer/events/new', (input, options) => {
    if (input === '/api/events') { expect(JSON.parse(String(options?.body)).starts_at).toBe('2026-11-01T06:30:00.000Z'); saved = true; return json(event, 201); }
    return json(event);
  });
  await fill('2026-11-01T01:30', 'America/New_York', '2026-11-01T03:00');
  fireEvent.click(screen.getByRole('button', { name: 'Создать черновик' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('Выберите');
  expect(saved).toBe(false);
  fireEvent.change(screen.getByLabelText('Смещение начала'), { target: { value: '2026-11-01T06:30:00.000Z' } });
  fireEvent.click(screen.getByRole('button', { name: 'Создать черновик' }));
  await waitFor(() => expect(saved).toBe(true));
});
it('keeps form values and permits retry after server validation failure', async () => {
  setup('/organizer/events/new', () => error('VALIDATION_ERROR'));
  await fill();
  fireEvent.click(screen.getByRole('button', { name: 'Создать черновик' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('Проверьте');
  expect(screen.getByLabelText(/^Название/)).toHaveValue('Meetup');
  expect(screen.getByRole('button', { name: 'Создать черновик' })).toBeEnabled();
  expect(screen.queryByText('server diagnostic')).not.toBeInTheDocument();
});
it('shows an empty list and a create link', async () => {
  setup('/organizer/events', () => json([]));
  expect(await screen.findByText('У вас пока нет мероприятий')).toBeVisible();
  expect(screen.getByRole('link', { name: 'Создать мероприятие' })).toHaveAttribute('href', '/organizer/events/new');
});
it('shows an error and retries the list request', async () => {
  let count = 0;
  setup('/organizer/events', () => ++count === 1 ? error('SERVICE_UNAVAILABLE', 503) : json([event]));
  expect(await screen.findByRole('alert')).toHaveTextContent('Не удалось');
  fireEvent.click(screen.getByRole('button', { name: 'Повторить' }));
  expect(await screen.findByRole('link', { name: event.title })).toBeVisible();
});
it.each([['EVENT_NOT_OWNER', 403, 'Нет доступа'], ['EVENT_NOT_FOUND', 404, 'Мероприятие не найдено']] as const)('shows safe detail error %s', async (code, status, message) => {
  setup(`/organizer/events/${event.id}`, () => error(code, status));
  expect(await screen.findByRole('alert')).toHaveTextContent(message);
  expect(screen.queryByText(event.description)).not.toBeInTheDocument();
});

it('prefills and saves an event draft through PATCH, then shows saved values', async () => {
  const edited = { ...event, title: 'Updated meetup', description: 'Updated plain text' };
  let patchBody: unknown;
  setup(`/organizer/events/${event.id}`, (input, options) => {
    if (input === `/api/events/${event.id}` && options?.method === 'PATCH') {
      patchBody = JSON.parse(String(options.body));
      expect(new Headers(options.headers).get('X-CSRF-Token')).toBe('test-token');
      return json(edited);
    }
    if (input === `/api/events/${event.id}`) return json(event);
    throw new Error(`Unexpected request: ${String(input)}`);
  });
  fireEvent.click(await screen.findByRole('link', { name: 'Редактировать черновик' }));
  expect(await screen.findByRole('heading', { name: 'Редактировать мероприятие' })).toBeVisible();
  expect(screen.getByLabelText(/^Название/)).toHaveValue(event.title);
  fireEvent.change(screen.getByLabelText(/^Название/), { target: { value: 'Updated meetup' } });
  fireEvent.change(screen.getByLabelText(/^Описание/), { target: { value: 'Updated plain text' } });
  fireEvent.click(screen.getByRole('button', { name: 'Сохранить изменения' }));
  expect(await screen.findByRole('heading', { name: edited.title })).toBeVisible();
  expect(screen.getByText(edited.description)).toBeVisible();
  expect(patchBody).toEqual({ title: 'Updated meetup', description: 'Updated plain text' });
  expect(window.location.pathname).toBe(`/organizer/events/${event.id}`);
});

it('regenerates a draft slug only through the explicit edit action', async () => {
  const regenerated = { ...event, slug: 'meetup-new-link' };
  let body: Record<string, unknown> | undefined;
  setup(`/organizer/events/${event.id}`, (input, options) => {
    if (input === `/api/events/${event.id}` && options?.method === 'PATCH') {
      body = JSON.parse(String(options.body)) as Record<string, unknown>;
      return json(regenerated);
    }
    return json(event);
  });
  fireEvent.click(await screen.findByRole('link', { name: 'Редактировать черновик' }));
  await screen.findByRole('heading', { name: 'Редактировать мероприятие' });
  fireEvent.click(screen.getByRole('button', { name: 'Обновить ссылку' }));
  expect(await screen.findByText('Ссылка события: meetup-new-link')).toBeVisible();
  expect(body).toEqual({ regenerate_slug: true });
});

it('preserves saved schedule seconds during a text-only edit', async () => {
  const precise = { ...event, starts_at: '2026-10-10T13:30:42Z', ends_at: '2026-10-10T15:30:17Z' };
  const updated = { ...precise, description: 'Changed description' };
  let body: Record<string, unknown> | undefined;
  setup(`/organizer/events/${event.id}`, (input, options) => {
    if (input === `/api/events/${event.id}` && options?.method === 'PATCH') {
      body = JSON.parse(String(options.body)) as Record<string, unknown>;
      return json(updated);
    }
    return json(precise);
  });
  fireEvent.click(await screen.findByRole('link', { name: 'Редактировать черновик' }));
  await screen.findByRole('heading', { name: 'Редактировать мероприятие' });
  fireEvent.change(screen.getByLabelText(/^Описание/), { target: { value: 'Changed description' } });
  fireEvent.click(screen.getByRole('button', { name: 'Сохранить изменения' }));
  expect(await screen.findByRole('heading', { name: precise.title })).toBeVisible();
  expect(body?.starts_at).toBeUndefined();
  expect(body?.ends_at).toBeUndefined();
  expect(body?.description).toBe('Changed description');
});

it('does not overwrite a different field saved from another tab', async () => {
  let serverEvent = event;
  let body: Record<string, unknown> | undefined;
  setup(`/organizer/events/${event.id}/edit`, (input, options) => {
    if (input === `/api/events/${event.id}` && options?.method === 'PATCH') {
      body = JSON.parse(String(options.body)) as Record<string, unknown>;
      serverEvent = { ...serverEvent, ...body };
      return json(serverEvent);
    }
    if (input === `/api/events/${event.id}`) return json(event);
    throw new Error(`Unexpected request: ${String(input)}`);
  });
  await screen.findByRole('heading', { name: 'Редактировать мероприятие' });

  // Another tab saves after this form loaded its snapshot.
  serverEvent = { ...serverEvent, description: 'Saved in the other tab' };
  fireEvent.change(screen.getByLabelText(/^Название/), { target: { value: 'Saved here' } });
  fireEvent.click(screen.getByRole('button', { name: 'Сохранить изменения' }));

  expect(await screen.findByRole('heading', { name: 'Saved here' })).toBeVisible();
  expect(body).toEqual({ title: 'Saved here' });
  expect(serverEvent.description).toBe('Saved in the other tab');
  expect(screen.getByText('Saved in the other tab')).toBeVisible();
});

it('synchronizes untouched form fields when cached event data refreshes', async () => {
  const stale = { ...event, title: 'Cached title', description: 'Cached description', capacity: 10 };
  const fresh = { ...event, title: 'Fresh title', description: 'Fresh description', capacity: 40 };
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  client.setQueryData(eventKeys.detail(user.id, event.id), stale);
  let finishFresh: ((response: Response) => void) | undefined;
  setup(`/organizer/events/${event.id}/edit`, input => {
    if (input === `/api/events/${event.id}`) return new Promise<Response>(resolve => { finishFresh = resolve; });
    throw new Error(`Unexpected request: ${String(input)}`);
  }, client);

  expect(await screen.findByLabelText(/^Название/)).toHaveValue(stale.title);
  finishFresh?.(json(fresh));
  await waitFor(() => {
    expect(screen.getByLabelText(/^Название/)).toHaveValue(fresh.title);
    expect(screen.getByLabelText(/^Описание/)).toHaveValue(fresh.description);
    expect(screen.getByLabelText(/^Количество мест/)).toHaveValue(fresh.capacity);
  });
});

it('preserves dirty form fields while refreshing untouched fields', async () => {
  const stale = { ...event, title: 'Cached title', description: 'Cached description' };
  const fresh = { ...event, title: 'Fresh title', description: 'Fresh description', capacity: 40 };
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  client.setQueryData(eventKeys.detail(user.id, event.id), stale);
  let finishFresh: ((response: Response) => void) | undefined;
  setup(`/organizer/events/${event.id}/edit`, input => {
    if (input === `/api/events/${event.id}`) return new Promise<Response>(resolve => { finishFresh = resolve; });
    throw new Error(`Unexpected request: ${String(input)}`);
  }, client);

  expect(await screen.findByLabelText(/^Название/)).toHaveValue(stale.title);
  fireEvent.change(screen.getByLabelText(/^Название/), { target: { value: 'My unsaved title' } });
  finishFresh?.(json(fresh));
  await waitFor(() => expect(screen.getByLabelText(/^Описание/)).toHaveValue(fresh.description));
  expect(screen.getByLabelText(/^Название/)).toHaveValue('My unsaved title');
  expect(screen.getByLabelText(/^Количество мест/)).toHaveValue(fresh.capacity);
});

it.each(['list', 'detail'])('isolates %s cache when another account logs in without reload', async mode => {
  const other = { ...user, id: '00000000-0000-4000-8000-000000000003', email: 'other@example.com' };
  let current = user;
  let finishRequest: ((response: Response) => void) | undefined;
  window.history.replaceState({}, '', mode === 'list' ? '/organizer/events' : `/organizer/events/${event.id}`);
  vi.stubGlobal('fetch', vi.fn<typeof fetch>(async input => {
    if (input === '/api/auth/me') return json(current);
    if (input === '/api/auth/csrf') return json({ csrf_token: 'test-token' });
    if (input === '/api/auth/login') { current = other; return json(other); }
    if (current === other) return new Promise<Response>(resolve => { finishRequest = resolve; });
    return json(mode === 'list' ? [event] : event);
  }));
  render(<App client={new QueryClient({ defaultOptions: { queries: { retry: false } } })} />);
  expect(await screen.findByText(event.title)).toBeVisible();
  window.history.pushState({}, '', '/login');
  fireEvent(window, new PopStateEvent('popstate'));
  await screen.findByRole('heading', { name: 'Войти' });
  fireEvent.change(screen.getByLabelText(/^Email/), { target: { value: other.email } });
  fireEvent.change(screen.getByLabelText(/^Пароль/), { target: { value: 'a long password' } });
  fireEvent.click(screen.getByRole('button', { name: 'Войти' }));
  await screen.findByText(other.email);
  window.history.pushState({}, '', mode === 'list' ? '/organizer/events' : `/organizer/events/${event.id}`);
  fireEvent(window, new PopStateEvent('popstate'));
  await waitFor(() => expect(finishRequest).toBeDefined());
  expect(screen.queryByText(event.title)).not.toBeInTheDocument();
  expect(screen.queryByText(event.description)).not.toBeInTheDocument();
  finishRequest!(error(mode === 'list' ? 'SERVICE_UNAVAILABLE' : 'EVENT_NOT_OWNER', mode === 'list' ? 503 : 403));
  await screen.findByRole('alert');
  expect(screen.queryByText(event.title)).not.toBeInTheDocument();
});
