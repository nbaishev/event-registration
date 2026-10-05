import { apiRequest } from '../../api/client';
import type { components } from '../../api/schema';
export type EventResponse = components['schemas']['EventResponse'];
export type EventSummary = components['schemas']['EventSummary'];
export type EventCreateRequest = components['schemas']['EventCreateRequest'];
export const eventKeys = { mine: (ownerId: string) => ['events', ownerId, 'mine'] as const, detail: (ownerId: string, id: string) => ['events', ownerId, 'detail', id] as const };
export const getMyEvents = (signal?: AbortSignal) => apiRequest<EventSummary[]>('/api/events/mine', { signal, requiresAuth: true });
export const getEvent = (id: string, signal?: AbortSignal) => apiRequest<EventResponse>(`/api/events/${encodeURIComponent(id)}`, { signal, requiresAuth: true });
export const createEvent = (body: EventCreateRequest) => apiRequest<EventResponse>('/api/events', { method: 'POST', body: JSON.stringify(body), requiresAuth: true });
