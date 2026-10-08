import { useEffect, useState, useSyncExternalStore } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { ApiError, getAuthPhase, refreshSession, subscribeAuthChanges } from '../../api/client';
import { eventKeys, getEventStats } from './api';

type LiveStatsStatus = 'connecting' | 'live' | 'reconnecting' | 'error';
const retryDelays = [1000, 2000, 4000, 8000, 16000, 30000];

export function useLiveStats(ownerId: string, eventId: string): LiveStatsStatus {
  const client = useQueryClient();
  const phase = useSyncExternalStore(subscribeAuthChanges, getAuthPhase, getAuthPhase);
  const [retryVersion, setRetryVersion] = useState(0);
  const [state, setState] = useState({ ownerId, eventId, status: 'connecting' as LiveStatsStatus });
  useEffect(() => {
    if (phase !== 'active') return;
    const queryKey = eventKeys.stats(ownerId, eventId);
    let active = true;
    let mounted = true;
    let terminal = false;
    let failures = 0;
    let stream: EventSource | undefined;
    let retryTimer: ReturnType<typeof setTimeout> | undefined;
    let openTimer: ReturnType<typeof setTimeout> | undefined;
    let validation: AbortController | undefined;
    const current = () => active && getAuthPhase() === 'active';
    const status = (next: LiveStatsStatus) => {
      if (current()) setState({ ownerId, eventId, status: next });
    };
    const closeStream = () => {
      clearTimeout(openTimer);
      stream?.close();
      stream = undefined;
    };
    const stop = () => {
      active = false;
      closeStream();
      clearTimeout(retryTimer);
      validation?.abort();
    };
    const unsubscribeQuery = client.getQueryCache().subscribe(event => {
      // A successful explicit snapshot retry validates access again. Start a
      // fresh lifecycle; cancelled requests cannot deliver a success here.
      if (mounted && terminal && getAuthPhase() === 'active' && event.type === 'updated' && event.action.type === 'success' && event.query === client.getQueryCache().find({ queryKey, exact: true })) {
        terminal = false;
        setRetryVersion(version => version + 1);
      }
    });
    const unsubscribe = subscribeAuthChanges(() => {
      // Stop synchronously: a late promise may settle before React's cleanup.
      if (getAuthPhase() !== 'active') stop();
    });
    const invalidate = () => {
      if (current()) void client.invalidateQueries({ queryKey, exact: true });
    };
    const recover = () => {
      if (!current()) return;
      closeStream();
      status('reconnecting');
      const delay = retryDelays[Math.min(failures++, retryDelays.length - 1)];
      retryTimer = setTimeout(() => { void reconnect(); }, delay);
    };
    const connect = () => {
      if (!current()) return;
      const source = new EventSource(`/api/events/${encodeURIComponent(eventId)}/stats/stream`);
      stream = source;
      let failed = false;
      const valid = () => current() && stream === source && !failed;
      const fail = () => {
        if (!valid()) return;
        failed = true;
        recover();
      };
      source.onopen = () => {
        if (!valid()) return;
        clearTimeout(openTimer);
        failures = 0;
        status('live');
        invalidate();
      };
      source.addEventListener('stats_changed', () => { if (valid()) invalidate(); });
      source.onerror = fail;
      openTimer = setTimeout(fail, 10000);
    };
    const reconnect = async () => {
      if (!current()) return;
      try {
        await refreshSession();
        if (!current()) return;
        validation = new AbortController();
        await getEventStats(eventId, validation.signal);
        if (current()) connect();
      } catch (cause) {
        if (!current()) return;
        if (cause instanceof ApiError && (cause.status === 401 || cause.status === 403 || cause.status === 404 || cause.code === 'EVENT_NOT_PUBLISHED')) {
          await client.cancelQueries({ queryKey, exact: true });
          if (!current()) return;
          status('error');
          terminal = true;
          const query = client.getQueryCache().find({ queryKey, exact: true });
          query?.setState({ status: 'error', error: cause, fetchStatus: 'idle' });
          stop();
        } else recover();
      }
    };
    status('connecting');
    connect();
    return () => { mounted = false; unsubscribeQuery(); unsubscribe(); stop(); };
  }, [client, ownerId, eventId, phase, retryVersion]);
  return state.ownerId === ownerId && state.eventId === eventId ? state.status : 'connecting';
}
