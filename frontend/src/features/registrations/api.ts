import type { QueryClient } from '@tanstack/react-query';
import { ApiError, apiRequest } from '../../api/client';
import type { components } from '../../api/schema';
export type RegistrationResponse = components['schemas']['RegistrationResponse'];
export type MyRegistrationResponse = components['schemas']['MyRegistrationResponse'];
export const registrationKeys = { mine: (userId: string) => ['registrations', userId, 'mine'] as const, detail: (userId: string, eventId: string) => ['registrations', userId, 'detail', eventId] as const };
export const registerForEvent = (eventId: string) => apiRequest<RegistrationResponse>(`/api/events/${encodeURIComponent(eventId)}/registrations`, { method: 'POST', requiresAuth: true });
export async function getMyRegistration(eventId: string, signal?: AbortSignal): Promise<RegistrationResponse | null> {
  try { return await apiRequest<RegistrationResponse>(`/api/events/${encodeURIComponent(eventId)}/my-registration`, { signal, requiresAuth: true }); }
  catch (cause) {
    if (cause instanceof ApiError && cause.status === 404 && cause.code === 'REGISTRATION_NOT_FOUND') return null;
    throw cause;
  }
}

export const cancelRegistration = (eventId: string) => apiRequest<RegistrationResponse>(`/api/events/${encodeURIComponent(eventId)}/registration`, { method: 'DELETE', requiresAuth: true });

export const getMyRegistrations = (signal?: AbortSignal) => apiRequest<MyRegistrationResponse[]>('/api/me/registrations', { signal, requiresAuth: true });

export async function applyRegistrationMutation(client: QueryClient, userId: string, saved: RegistrationResponse): Promise<void> {
  const detail = registrationKeys.detail(userId, saved.event_id);
  const mine = registrationKeys.mine(userId);
  await Promise.all([client.cancelQueries({ queryKey: detail, exact: true }), client.cancelQueries({ queryKey: mine, exact: true })]);
  client.setQueryData(detail, saved);
  client.setQueryData<MyRegistrationResponse[]>(mine, items => items?.map(item => item.registration.id === saved.id ? { ...item, registration: saved } : item));
  await client.invalidateQueries({ queryKey: mine, exact: true });
}
