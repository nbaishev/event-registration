import { ApiError, apiRequest } from '../../api/client';
import type { components } from '../../api/schema';
export type RegistrationResponse = components['schemas']['RegistrationResponse'];
export const registrationKeys = { detail: (userId: string, eventId: string) => ['registrations', userId, 'detail', eventId] as const };
export const registerForEvent = (eventId: string) => apiRequest<RegistrationResponse>(`/api/events/${encodeURIComponent(eventId)}/registrations`, { method: 'POST', requiresAuth: true });
export async function getMyRegistration(eventId: string, signal?: AbortSignal): Promise<RegistrationResponse | null> {
  try { return await apiRequest<RegistrationResponse>(`/api/events/${encodeURIComponent(eventId)}/my-registration`, { signal, requiresAuth: true }); }
  catch (cause) {
    if (cause instanceof ApiError && cause.status === 404 && cause.code === 'REGISTRATION_NOT_FOUND') return null;
    throw cause;
  }
}

export const cancelRegistration = (eventId: string) => apiRequest<RegistrationResponse>(`/api/events/${encodeURIComponent(eventId)}/registration`, { method: 'DELETE', requiresAuth: true });
