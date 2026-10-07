import { apiRequest } from '../../api/client';
import type { components } from '../../api/schema';
export type EventResponse = components['schemas']['EventResponse'];
export type EventSummary = components['schemas']['EventSummary'];
export type EventCreateRequest = components['schemas']['EventCreateRequest'];
export type EventPatchRequest = components['schemas']['EventPatchRequest'];
export const eventKeys = { mine: (ownerId: string) => ['events', ownerId, 'mine'] as const, detail: (ownerId: string, id: string) => ['events', ownerId, 'detail', id] as const };
export const getMyEvents = (signal?: AbortSignal) => apiRequest<EventSummary[]>('/api/events/mine', { signal, requiresAuth: true });
export const getEvent = (id: string, signal?: AbortSignal) => apiRequest<EventResponse>(`/api/events/${encodeURIComponent(id)}`, { signal, requiresAuth: true });
export const createEvent = (body: EventCreateRequest) => apiRequest<EventResponse>('/api/events', { method: 'POST', body: JSON.stringify(body), requiresAuth: true });
export const patchEvent = (id: string, body: EventPatchRequest) => apiRequest<EventResponse>(`/api/events/${encodeURIComponent(id)}`, { method: 'PATCH', body: JSON.stringify(body), requiresAuth: true });
export const deleteEvent = (id: string) => apiRequest<void>(`/api/events/${encodeURIComponent(id)}`, { method: 'DELETE', requiresAuth: true });

export type PublicEventResponse = components['schemas']['PublicEventResponse'];
export const publishEvent = (id: string) => apiRequest<EventResponse>(`/api/events/${encodeURIComponent(id)}/publish`, { method: 'POST', requiresAuth: true });
export const publicEventKey = (slug: string) => ['public-events', slug] as const;
export const getPublicEvent = (slug: string, signal?: AbortSignal) => apiRequest<PublicEventResponse>(`/api/public/events/${encodeURIComponent(slug)}`, { signal });

export type CheckInResponse = components['schemas']['CheckInResponse'];
export const checkIn = (eventId: string, ticketCode: string) => apiRequest<CheckInResponse>(`/api/events/${encodeURIComponent(eventId)}/check-ins`, { method: 'POST', body: JSON.stringify({ ticket_code: ticketCode }), requiresAuth: true });
