import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient } from '@tanstack/react-query';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
let App: typeof import('../../app')['App'];
beforeEach(async () => { vi.resetModules(); App = (await import('../../app')).App; });

const user = { id: '00000000-0000-4000-8000-000000000001', email: 'alice@example.com', created_at: '2026-10-04T12:00:00Z', updated_at: '2026-10-04T12:00:00Z' };
const failure = (code: string) => ({ error: { code, message: 'arbitrary server text', details: {} } });
function setup(path: string, loginError?: string, client = new QueryClient()) {
  let authenticated = path === '/';
  window.history.replaceState({}, '', path);
  vi.stubGlobal('fetch', vi.fn<typeof fetch>(async (input, options) => {
    if (input === '/api/auth/csrf') return new Response(JSON.stringify({ csrf_token: 'test-token' }));
    if (input === '/api/auth/refresh') return new Response(JSON.stringify(failure('AUTH_REFRESH_INVALID')), { status: 401 });
    if (input === '/api/auth/me') return new Response(JSON.stringify(authenticated ? user : failure('AUTH_REQUIRED')), { status: authenticated ? 200 : 401 });
    if (input === '/api/auth/login') {
      expect(options?.credentials).toBe('same-origin');
      expect(new Headers(options?.headers).get('X-CSRF-Token')).toBe('test-token');
      expect(JSON.parse(String(options?.body))).toEqual({ email: 'alice@example.com', password: 'a long password' });
      if (loginError) return new Response(JSON.stringify(failure(loginError)), { status: loginError === 'AUTH_RATE_LIMITED' ? 429 : 401 });
      authenticated = true;
      return new Response(JSON.stringify(user));
    }
    if (input === '/api/auth/logout') {
      authenticated = false;
      return new Response(null, { status: 204 });
    }
    throw new Error('Unexpected request');
  }));
  render(<App client={client} />);
  return client;
}
function submitLogin() {
  fireEvent.change(screen.getByLabelText(/^Email/), { target: { value: 'alice@example.com' } });
  fireEvent.change(screen.getByLabelText(/^Пароль/), { target: { value: 'a long password' } });
  fireEvent.click(screen.getByRole('button', { name: 'Войти' }));
}
afterEach(() => vi.unstubAllGlobals());

describe('Auth session', () => {
  it('keeps private content hidden during bootstrap and redirects anonymous users', async () => {
    window.history.replaceState({}, '', '/');
    let respond!: (response: Response) => void;
    vi.stubGlobal('fetch', vi.fn(async (input) => {
      if (input === '/api/auth/csrf') return new Response(JSON.stringify({ csrf_token: 'test-token' }));
      if (input === '/api/auth/refresh') return new Response(JSON.stringify(failure('AUTH_REFRESH_INVALID')), { status: 401 });
      return new Promise<Response>(resolve => { respond = resolve; });
    }));
    render(<App />);
    expect(screen.getByRole('status')).toHaveTextContent('Проверяем сессию');
    expect(screen.queryByText(user.email)).not.toBeInTheDocument();
    respond(new Response(JSON.stringify(failure('AUTH_REQUIRED')), { status: 401 }));
    await waitFor(() => expect(window.location.pathname).toBe('/login'));
    expect(await screen.findByRole('heading', { name: 'Войти' })).toBeVisible();
  });
  it('restores the current account from me on initial navigation', async () => {
    setup('/');
    expect(await screen.findByText(user.email)).toBeVisible();
    expect(screen.getByRole('button', { name: 'Выйти' })).toBeEnabled();
  });
  it('logs in with CSRF and navigates to the account without secrets in storage', async () => {
    setup('/login');
    submitLogin();
    expect(await screen.findByText(user.email)).toBeVisible();
    expect(window.location.pathname).toBe('/');
    expect(JSON.stringify(window.history.state)).not.toContain('a long password');
    expect(localStorage.length).toBe(0);
    expect(sessionStorage.length).toBe(0);
  });
  it('clears the entire query cache after successful logout and navigates to login', async () => {
    const client = new QueryClient();
    client.setQueryData(['private', 'events'], ['private data']);
    setup('/', undefined, client);
    await screen.findByText(user.email);
    fireEvent.click(screen.getByRole('button', { name: 'Выйти' }));
    await waitFor(() => expect(window.location.pathname).toBe('/login'));
    expect(await screen.findByRole('heading', { name: 'Войти' })).toBeVisible();
    expect(screen.queryByText(user.email)).not.toBeInTheDocument();
    expect(client.getQueryData(['private', 'events'])).toBeUndefined();
    expect(client.getQueryData(['auth', 'me'])).toBeUndefined();
  });
  it.each([
    ['AUTH_INVALID_CREDENTIALS', 'Неверный email или пароль'],
    ['AUTH_RATE_LIMITED', 'Слишком много попыток'],
    ['CSRF_INVALID', 'Повторите попытку'],
  ])('handles %s by error.code', async (code, message) => {
    setup('/login', code);
    submitLogin();
    expect(await screen.findByRole('alert')).toHaveTextContent(message);
    expect(window.location.pathname).toBe('/login');
    expect(screen.getByRole('button', { name: 'Войти' })).toBeEnabled();
  });
  it('keeps account hidden and displays a retry on a bootstrap network failure', async () => {
    window.history.replaceState({}, '', '/');
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Network unavailable')));
    render(<App />);
    expect(await screen.findByRole('alert')).toHaveTextContent('Не удалось проверить сессию');
    expect(screen.queryByText(user.email)).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Повторить' })).toBeEnabled();
  });
});

it('clears private cache and redirects when background recovery loses the session', async () => {
  const client = setup('/');
  client.setQueryData(['private', 'events'], ['private data']);
  await screen.findByText(user.email);
  vi.stubGlobal('fetch', vi.fn<typeof fetch>(async input => {
    if (input === '/api/auth/csrf') return new Response(JSON.stringify({ csrf_token: 'test-token' }));
    return new Response(JSON.stringify(failure(input === '/api/auth/refresh' ? 'AUTH_REFRESH_INVALID' : 'AUTH_REQUIRED')), { status: 401 });
  }));
  await client.invalidateQueries({ queryKey: ['auth', 'me'] });
  await waitFor(() => expect(window.location.pathname).toBe('/login'));
  expect(await screen.findByRole('heading', { name: 'Войти' })).toBeVisible();
  expect(screen.queryByText(user.email)).not.toBeInTheDocument();
  expect(client.getQueryData(['private', 'events'])).toBeUndefined();
  expect(client.getQueryData(['auth', 'me'])).toBeUndefined();
});

it('keeps logout pending until refresh settles and never restores its user afterwards', async () => {
  const client = setup('/');
  await screen.findByText(user.email);
  let release!: (response: Response) => void;
  const refresh = new Promise<Response>(resolve => { release = resolve; });
  const events: string[] = [];
  let finishLogout!: (response: Response) => void;
  const logoutResponse = new Promise<Response>(resolve => { finishLogout = resolve; });
  vi.stubGlobal('fetch', vi.fn<typeof fetch>(async input => {
    if (input === '/api/auth/csrf') return new Response(JSON.stringify({ csrf_token: 'test-token' }));
    if (input === '/api/auth/refresh') { events.push('refresh'); return refresh; }
    if (input === '/api/auth/logout') { events.push('logout'); return logoutResponse; }
    return new Response(JSON.stringify(failure('AUTH_REQUIRED')), { status: 401 });
  }));
  const refetch = client.invalidateQueries({ queryKey: ['auth', 'me'] });
  await waitFor(() => expect(events).toEqual(['refresh']));
  fireEvent.click(screen.getByRole('button', { name: 'Выйти' }));
  expect(screen.getByRole('button', { name: 'Выходим…' })).toBeDisabled();
  expect(events).toEqual(['refresh']);
  release(new Response(JSON.stringify(user)));
  await refetch;
  await waitFor(() => expect(events).toEqual(['refresh', 'logout']));
  expect(window.location.pathname).toBe('/');
  finishLogout(new Response(null, { status: 204 }));
  await waitFor(() => expect(window.location.pathname).toBe('/login'));
  expect(events).toEqual(['refresh', 'logout']);
  expect(await screen.findByRole('heading', { name: 'Войти' })).toBeVisible();
  expect(screen.queryByText(user.email)).not.toBeInTheDocument();
  expect(client.getQueryData(['auth', 'me'])).toBeUndefined();
});

it('redirects a known anonymous session when returning to the root inside the SPA', async () => {
  setup('/');
  await screen.findByText(user.email);
  fireEvent.click(screen.getByRole('button', { name: 'Выйти' }));
  expect(await screen.findByRole('heading', { name: 'Войти' })).toBeVisible();
  window.history.pushState({}, '', '/');
  fireEvent(window, new PopStateEvent('popstate'));
  await waitFor(() => expect(window.location.pathname).toBe('/login'));
  expect(await screen.findByRole('heading', { name: 'Войти' })).toBeVisible();
});
