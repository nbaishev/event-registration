import { CancelledError, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useSyncExternalStore } from 'react';
import { useNavigate } from 'react-router';
import { ApiError, SessionChangedError, apiRequest, getAuthPhase, subscribeAuthChanges, subscribeSessionLoss } from '../../api/client';
import type { components } from '../../api/schema';

export type CurrentUser = components['schemas']['UserResponse'];
export const sessionKey = ['auth', 'me'] as const;

export function useSession(enabled = true) {
  const client = useQueryClient();
  const phase = useSyncExternalStore(subscribeAuthChanges, getAuthPhase, getAuthPhase);
  return useQuery({
    queryKey: sessionKey,
    enabled: enabled && phase === 'active',
    queryFn: async ({ signal }): Promise<CurrentUser | null> => {
      const query = client.getQueryCache().find({ queryKey: sessionKey, exact: true });
      try { return await apiRequest<CurrentUser>('/api/auth/me', { signal }); }
      catch (cause) {
        if (cause instanceof SessionChangedError) {
          void query?.cancel({ revert: true });
          throw new CancelledError({ revert: true });
        }
        if (cause instanceof ApiError && ['AUTH_REQUIRED', 'AUTH_REFRESH_INVALID'].includes(cause.code)) return null;
        throw cause;
      }
    },
    retry: false,
  });
}

export function SessionBoundary() {
  const client = useQueryClient();
  const navigate = useNavigate();
  useEffect(() => subscribeSessionLoss(() => {
    void client.cancelQueries();
    client.clear();
    navigate('/login', { replace: true });
  }), [client, navigate]);
  return null;
}
