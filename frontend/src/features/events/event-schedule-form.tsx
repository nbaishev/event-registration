import { Alert, Button, Stack, TextField, Typography } from '@mui/material';
import { useQueryClient } from '@tanstack/react-query';
import { useEffect, useMemo, useRef, useState, type FormEvent } from 'react';
import { ApiError } from '../../api/client';
import { eventKeys, patchEvent, publicEventKey, type EventPatchRequest, type EventResponse } from './api';
import { localTimeCandidates, offsetLabel, resolveLocalTime, toLocalDateTimeInput } from './event-time';

function candidates(local: string, timezone: string) {
  try { return localTimeCandidates(local, timezone); } catch { return []; }
}
function valuesFor(event: EventResponse) {
  const starts = toLocalDateTimeInput(event.starts_at, event.timezone);
  const ends = toLocalDateTimeInput(event.ends_at, event.timezone);
  const choice = (instant: string, local: string) => candidates(local, event.timezone)
    .find(value => Math.floor(Date.parse(value) / 60000) === Math.floor(Date.parse(instant) / 60000)) ?? '';
  return { starts, ends, timezone: event.timezone, startChoice: choice(event.starts_at, starts), endChoice: choice(event.ends_at, ends) };
}
// Minute inputs retain the existing seconds/milliseconds, including DST choice.
function instantFor(local: string, timezone: string, selected: string, original: string, oldTimezone: string) {
  const remainder = Date.parse(original) % 60000;
  if (timezone === oldTimezone && local === toLocalDateTimeInput(original, oldTimezone)
    && (!selected || Date.parse(selected) + remainder === Date.parse(original))) return original;
  return new Date(Date.parse(resolveLocalTime(local, timezone, selected || undefined)) + remainder).toISOString();
}

export function EventScheduleForm({ event }: { event: EventResponse }) {
  const [values, setValues] = useState(() => valuesFor(event));
  const previous = useRef(valuesFor(event));
  useEffect(() => {
    const incoming = valuesFor(event);
    const old = previous.current;
    setValues(current => Object.fromEntries(Object.entries(incoming).map(([key, value]) => {
      const field = key as keyof typeof current;
      return [key, current[field] === old[field] ? value : current[field]];
    })) as typeof current);
    previous.current = incoming;
  }, [event]);
  const [pending, setPending] = useState(false);
  const saving = useRef(false);
  const [error, setError] = useState<string>();
  const client = useQueryClient();
  const startCandidates = useMemo(() => candidates(values.starts, values.timezone), [values.starts, values.timezone]);
  const endCandidates = useMemo(() => candidates(values.ends, values.timezone), [values.ends, values.timezone]);
  const dirty = Object.entries(values).some(([key, value]) => value !== previous.current[key as keyof typeof values]);

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (saving.current) return;
    setError(undefined);
    let body: EventPatchRequest;
    try {
      const starts_at = instantFor(values.starts, values.timezone, values.startChoice, event.starts_at, event.timezone);
      const ends_at = instantFor(values.ends, values.timezone, values.endChoice, event.ends_at, event.timezone);
      if (Date.parse(ends_at) <= Date.parse(starts_at)) throw new Error('Окончание должно быть позже начала');
      body = {};
      if (Date.parse(starts_at) !== Date.parse(event.starts_at)) body.starts_at = starts_at;
      if (Date.parse(ends_at) !== Date.parse(event.ends_at)) body.ends_at = ends_at;
      if (values.timezone !== event.timezone) body.timezone = values.timezone;
      if (!Object.keys(body).length) return;
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Проверьте расписание'); return; }
    saving.current = true;
    setPending(true);
    try {
      const saved = await patchEvent(event.id, body);
      const key = eventKeys.detail(saved.owner_id, saved.id);
      await client.cancelQueries({ queryKey: key, exact: true });
      const incoming = valuesFor(saved);
      previous.current = incoming;
      setValues(incoming);
      client.setQueryData(key, saved);
      void client.invalidateQueries({ queryKey: eventKeys.mine(saved.owner_id) });
      void client.invalidateQueries({ queryKey: publicEventKey(saved.slug), exact: true });
    } catch (cause) {
      setError(cause instanceof ApiError ? {
        EVENT_ALREADY_STARTED: 'Мероприятие уже началось. Расписание изменить нельзя.',
        EVENT_CANCELLED: 'Мероприятие отменено. Расписание изменить нельзя.',
        EVENT_NOT_EDITABLE: 'Нельзя изменить расписание в текущем состоянии мероприятия.',
        EVENT_NOT_OWNER: 'Нет доступа к этому мероприятию.',
        EVENT_NOT_FOUND: 'Мероприятие не найдено.',
        VALIDATION_ERROR: 'Проверьте расписание: начало должно быть в будущем, окончание — позже начала.',
        CSRF_INVALID: 'Защита запроса обновлена. Повторите попытку.',
      }[cause.code] ?? 'Не удалось сохранить расписание. Повторите попытку.' : 'Не удалось сохранить расписание. Повторите попытку.');
    } finally { saving.current = false; setPending(false); }
  }
  return <Stack component="form" noValidate onSubmit={submit} spacing={2}>
    <Typography component="h2" variant="h6">Изменить расписание</Typography>
    <Typography color="text.secondary">Даты указаны в часовом поясе мероприятия. Участники и список ожидания получат письмо о переносе.</Typography>
    {error && <Alert severity="error">{error}</Alert>}
    <TextField label="Часовой пояс IANA" value={values.timezone} onChange={e => setValues(v => ({ ...v, timezone: e.target.value, startChoice: '', endChoice: '' }))} disabled={pending} helperText="Например, Asia/Almaty или Europe/Berlin" />
    <TextField label="Начало" type="datetime-local" slotProps={{ inputLabel: { shrink: true } }} value={values.starts} onChange={e => setValues(v => ({ ...v, starts: e.target.value, startChoice: '' }))} disabled={pending} />
    {startCandidates.length > 1 && <TextField label="Смещение начала" select slotProps={{ select: { native: true }, inputLabel: { shrink: true } }} value={values.startChoice} onChange={e => setValues(v => ({ ...v, startChoice: e.target.value }))} disabled={pending}><option value="">Выберите смещение</option>{startCandidates.map(instant => <option key={instant} value={instant}>{offsetLabel(values.starts, instant)}</option>)}</TextField>}
    <TextField label="Окончание" type="datetime-local" slotProps={{ inputLabel: { shrink: true } }} value={values.ends} onChange={e => setValues(v => ({ ...v, ends: e.target.value, endChoice: '' }))} disabled={pending} />
    {endCandidates.length > 1 && <TextField label="Смещение окончания" select slotProps={{ select: { native: true }, inputLabel: { shrink: true } }} value={values.endChoice} onChange={e => setValues(v => ({ ...v, endChoice: e.target.value }))} disabled={pending}><option value="">Выберите смещение</option>{endCandidates.map(instant => <option key={instant} value={instant}>{offsetLabel(values.ends, instant)}</option>)}</TextField>}
    <Button type="submit" variant="contained" disabled={pending || !dirty}>{pending ? 'Сохраняем…' : 'Сохранить расписание'}</Button>
  </Stack>;
}
