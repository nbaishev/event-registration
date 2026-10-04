import { useQuery } from '@tanstack/react-query';
import { ApiError, apiRequest } from '../../api/client';
import type { components } from '../../api/schema';

export type CurrentUser = components['schemas']['UserResponse'];
export const sessionKey = ['auth', 'me'] as const;

export function useSession(enabled = true) {
  return useQuery({
    queryKey: sessionKey,
    enabled,
    queryFn: async ({ signal }): Promise<CurrentUser | null> => {
      try { return await apiRequest<CurrentUser>('/api/auth/me', { signal }); }
      catch (cause) {
        if (cause instanceof ApiError && cause.code === 'AUTH_REQUIRED') return null;
        throw cause;
      }
    },
    retry: false,
  });
}
