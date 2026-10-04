import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { App } from '../../app';

const user = { id: '00000000-0000-4000-8000-000000000001', email: 'alice@example.com', created_at: '2026-10-04T12:00:00Z', updated_at: '2026-10-04T12:00:00Z' };
function setup(status: number, body: unknown) {
  window.history.replaceState({}, '', '/register');
  const fetch = vi.fn<typeof globalThis.fetch>(async (input, options) => {
    if (input === '/api/auth/csrf') return new Response(JSON.stringify({ csrf_token: 'test-token' }));
    expect(input).toBe('/api/auth/register');
    expect(options?.credentials).toBe('same-origin');
    expect(new Headers(options?.headers).get('X-CSRF-Token')).toBe('test-token');
    return new Response(JSON.stringify(body), { status });
  });
  vi.stubGlobal('fetch', fetch);
  render(<App />);
  return fetch;
}
function submit() {
  fireEvent.change(screen.getByLabelText(/^Email/), { target: { value: 'alice@example.com' } });
  fireEvent.change(screen.getByLabelText(/^Пароль/), { target: { value: 'a long password' } });
  fireEvent.click(screen.getByRole('button', { name: 'Создать аккаунт' }));
}
afterEach(() => vi.unstubAllGlobals());

describe('Register flow', () => {
  it('submits CSRF and navigates to login without password in URL/state/storage', async () => {
    const fetch = setup(201, user);
    submit();
    await waitFor(() => expect(window.location.pathname).toBe('/login'));
    expect(window.location.search).toBe('');
    expect(JSON.stringify(window.history.state)).not.toContain('a long password');
    expect(JSON.stringify(localStorage)).not.toContain('a long password');
    expect(JSON.stringify(sessionStorage)).not.toContain('a long password');
    const request = fetch.mock.calls.find(([path]) => path === '/api/auth/register');
    expect(JSON.parse(String(request?.[1]?.body))).toEqual({ email: 'alice@example.com', password: 'a long password' });
  });
  it('shows duplicate error using error.code and stays on register', async () => {
    setup(409, { error: { code: 'EMAIL_ALREADY_REGISTERED', message: 'arbitrary server text', details: {} } });
    submit();
    expect(await screen.findByRole('alert')).toHaveTextContent('Этот email уже зарегистрирован');
    expect(window.location.pathname).toBe('/register');
  });
  it('shows safe field validation details', async () => {
    setup(422, { error: { code: 'VALIDATION_ERROR', message: 'Invalid request.', details: { fields: [{ field: 'password', code: 'PASSWORD_LENGTH' }] } } });
    submit();
    expect(await screen.findByText('Пароль должен содержать от 12 до 128 символов')).toBeVisible();
  });
  it('shows a recoverable network error and enables submit again', async () => {
    setup(201, user);
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Network unavailable')));
    submit();
    expect(await screen.findByRole('alert')).toHaveTextContent('Не удалось отправить запрос');
    expect(screen.getByRole('button', { name: 'Создать аккаунт' })).toBeEnabled();
  });
});
