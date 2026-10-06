import { Alert, Button, Paper, Stack, TextField, Typography } from '@mui/material';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useMemo, useRef, useState, type FormEvent } from 'react';
import { useNavigate, useOutletContext, useParams } from 'react-router';
import { ApiError } from '../../api/client';
import { eventKeys, getEvent, patchEvent, type EventPatchRequest, type EventResponse, type EventSummary } from './api';
import { localTimeCandidates, offsetLabel, resolveLocalTime, toLocalDateTimeInput } from './event-time';

function candidates(local: string, timezone: string) {
  try { return localTimeCandidates(local, timezone); } catch { return []; }
}

function choiceFor(instant: string, local: string, timezone: string) {
  return candidates(local, timezone).find(candidate => Date.parse(candidate) === Date.parse(instant)) ?? '';
}

type EditValues = {
  title: string;
  description: string;
  timezone: string;
  starts: string;
  ends: string;
  capacity: string;
  startChoice: string;
  endChoice: string;
};

function valuesFor(event: EventResponse): EditValues {
  const starts = toLocalDateTimeInput(event.starts_at, event.timezone);
  const ends = toLocalDateTimeInput(event.ends_at, event.timezone);
  return {
    title: event.title,
    description: event.description,
    timezone: event.timezone,
    starts,
    ends,
    capacity: String(event.capacity),
    startChoice: choiceFor(event.starts_at, starts, event.timezone),
    endChoice: choiceFor(event.ends_at, ends, event.timezone),
  };
}

function EditForm({ event }: { event: EventResponse }) {
  const initialValues = valuesFor(event);
  const [values, setValues] = useState(initialValues);
  const previousValues = useRef(initialValues);
  useEffect(() => {
    const incoming = valuesFor(event);
    const previous = previousValues.current;
    setValues(current => ({
      title: current.title === previous.title ? incoming.title : current.title,
      description: current.description === previous.description ? incoming.description : current.description,
      timezone: current.timezone === previous.timezone ? incoming.timezone : current.timezone,
      starts: current.starts === previous.starts ? incoming.starts : current.starts,
      ends: current.ends === previous.ends ? incoming.ends : current.ends,
      capacity: current.capacity === previous.capacity ? incoming.capacity : current.capacity,
      startChoice: current.startChoice === previous.startChoice ? incoming.startChoice : current.startChoice,
      endChoice: current.endChoice === previous.endChoice ? incoming.endChoice : current.endChoice,
    }));
    previousValues.current = incoming;
  }, [event]);
  const { title, description, timezone, starts, ends, capacity, startChoice, endChoice } = values;
  const setField = <K extends keyof EditValues>(field: K, value: EditValues[K]) => {
    setValues(current => ({ ...current, [field]: value }));
  };
  const [pending, setPending] = useState(false), [error, setError] = useState<string>();
  const startCandidates = useMemo(() => candidates(starts, timezone), [starts, timezone]);
  const endCandidates = useMemo(() => candidates(ends, timezone), [ends, timezone]);
  const client = useQueryClient(), navigate = useNavigate();

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); if (pending) return;
    setError(undefined);
    const regenerate = (e.nativeEvent as SubmitEvent).submitter instanceof HTMLElement
      && (e.nativeEvent as SubmitEvent).submitter?.getAttribute('data-action') === 'regenerate';
    let body: EventPatchRequest;
    try {
      const normalizedTitle = title.trim();
      if ([...normalizedTitle].length < 1 || [...normalizedTitle].length > 200) throw new Error('Название должно содержать от 1 до 200 символов');
      if ([...description].length < 1 || [...description].length > 10000) throw new Error('Описание должно содержать от 1 до 10 000 символов');
      if (!/^\d+$/.test(capacity) || !Number.isSafeInteger(Number(capacity)) || Number(capacity) < 1 || Number(capacity) > 2147483647) throw new Error('Количество мест должно быть целым числом от 1 до 2 147 483 647');
      const starts_at = starts === toLocalDateTimeInput(event.starts_at, event.timezone) && timezone === event.timezone
        && (!startChoice || Date.parse(startChoice) === Date.parse(event.starts_at))
        ? event.starts_at : resolveLocalTime(starts, timezone, startChoice);
      const ends_at = ends === toLocalDateTimeInput(event.ends_at, event.timezone) && timezone === event.timezone
        && (!endChoice || Date.parse(endChoice) === Date.parse(event.ends_at))
        ? event.ends_at : resolveLocalTime(ends, timezone, endChoice);
      if (Date.parse(ends_at) <= Date.parse(starts_at)) throw new Error('Окончание должно быть позже начала');
      body = {};
      if (normalizedTitle !== event.title) body.title = normalizedTitle;
      if (description !== event.description) body.description = description;
      if (Date.parse(starts_at) !== Date.parse(event.starts_at)) body.starts_at = starts_at;
      if (Date.parse(ends_at) !== Date.parse(event.ends_at)) body.ends_at = ends_at;
      if (timezone !== event.timezone) body.timezone = timezone;
      if (Number(capacity) !== event.capacity) body.capacity = Number(capacity);
      if (regenerate) body.regenerate_slug = true;
      if (Object.keys(body).length === 0) throw new Error('Нет изменений для сохранения');
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Проверьте данные формы'); return; }
    setPending(true);
    try {
      const updated = await patchEvent(event.id, body);
      const savedValues = valuesFor(updated);
      previousValues.current = savedValues;
      setValues(savedValues);
      client.setQueryData(eventKeys.detail(updated.owner_id, updated.id), updated);
      client.setQueryData<EventSummary[]>(eventKeys.mine(updated.owner_id), current => current?.map(item => item.id === updated.id ? {
        id: updated.id, title: updated.title, slug: updated.slug, starts_at: updated.starts_at,
        ends_at: updated.ends_at, timezone: updated.timezone, capacity: updated.capacity, status: updated.status,
      } : item));
      void client.invalidateQueries({ queryKey: eventKeys.mine(updated.owner_id) });
      navigate(`/organizer/events/${updated.id}`);
    } catch (cause) {
      setError(cause instanceof ApiError ? {
        VALIDATION_ERROR: 'Проверьте данные формы: даты и поля должны быть корректны',
        EVENT_ALREADY_STARTED: 'Начавшееся мероприятие нельзя менять по расписанию или количеству мест',
        EVENT_NOT_EDITABLE: 'Опубликованное мероприятие нельзя редактировать',
        EVENT_CANCELLED: 'Отменённое мероприятие нельзя редактировать',
        EVENT_NOT_OWNER: 'Нет доступа к этому мероприятию',
        EVENT_NOT_FOUND: 'Мероприятие не найдено',
        CSRF_INVALID: 'Защита запроса обновлена. Повторите попытку',
        SERVICE_UNAVAILABLE: 'Не удалось сохранить изменения. Повторите попытку',
      }[cause.code] ?? 'Не удалось сохранить изменения. Повторите попытку' : 'Не удалось сохранить изменения. Повторите попытку');
    } finally { setPending(false); }
  }

  return <Paper variant="outlined" sx={{ p: 4 }}><Stack component="form" noValidate onSubmit={submit} spacing={3}>
    <Typography component="h1" variant="h4">Редактировать мероприятие</Typography>
    <Typography color="text.secondary">Изменения сохраняются как черновик. Даты указаны в часовом поясе мероприятия.</Typography>
    {error && <Alert severity="error">{error}</Alert>}
    <TextField label="Название" required value={title} onChange={e => setField('title', e.target.value)} disabled={pending} helperText="От 1 до 200 символов" />
    <TextField label="Описание" required multiline minRows={4} value={description} onChange={e => setField('description', e.target.value)} disabled={pending} helperText="От 1 до 10 000 символов" />
    <TextField label="Часовой пояс IANA" required value={timezone} onChange={e => setValues(current => ({ ...current, timezone: e.target.value, startChoice: '', endChoice: '' }))} disabled={pending} helperText="Например, Asia/Almaty или Europe/Berlin" />
    <TextField label="Начало" type="datetime-local" required slotProps={{ inputLabel: { shrink: true } }} value={starts} onChange={e => setValues(current => ({ ...current, starts: e.target.value, startChoice: '' }))} disabled={pending} />
    {startCandidates.length > 1 && <TextField label="Смещение начала" select slotProps={{ select: { native: true }, inputLabel: { shrink: true } }} value={startChoice} onChange={e => setField('startChoice', e.target.value)} disabled={pending} helperText="Это время встречается дважды при смене часового пояса"><option value="">Выберите смещение</option>{startCandidates.map(instant => <option key={instant} value={instant}>{offsetLabel(starts, instant)}</option>)}</TextField>}
    <TextField label="Окончание" type="datetime-local" required slotProps={{ inputLabel: { shrink: true } }} value={ends} onChange={e => setValues(current => ({ ...current, ends: e.target.value, endChoice: '' }))} disabled={pending} />
    {endCandidates.length > 1 && <TextField label="Смещение окончания" select slotProps={{ select: { native: true }, inputLabel: { shrink: true } }} value={endChoice} onChange={e => setField('endChoice', e.target.value)} disabled={pending} helperText="Это время встречается дважды при смене часового пояса"><option value="">Выберите смещение</option>{endCandidates.map(instant => <option key={instant} value={instant}>{offsetLabel(ends, instant)}</option>)}</TextField>}
    <TextField label="Количество мест" type="number" required value={capacity} onChange={e => setField('capacity', e.target.value)} disabled={pending} />
    <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
      <Button type="submit" variant="contained" disabled={pending}>{pending ? 'Сохраняем…' : 'Сохранить изменения'}</Button>
      <Button type="submit" data-action="regenerate" variant="outlined" disabled={pending}>Обновить ссылку</Button>
    </Stack>
  </Stack></Paper>;
}

export function EventEditPage() {
  const ownerId = useOutletContext<string>();
  const { eventId = '' } = useParams();
  const query = useQuery({ queryKey: eventKeys.detail(ownerId, eventId), queryFn: ({ signal }) => getEvent(eventId, signal), retry: false });
  if (query.isPending) return <Typography role="status">Загружаем мероприятие…</Typography>;
  if (query.isError) {
    const code = query.error instanceof ApiError ? query.error.code : '';
    const message = code === 'EVENT_NOT_FOUND' ? 'Мероприятие не найдено' : code === 'EVENT_NOT_OWNER' ? 'Нет доступа к этому мероприятию' : 'Не удалось загрузить мероприятие';
    return <Alert severity="error">{message}</Alert>;
  }
  if (query.data.status !== 'DRAFT') return <Alert severity="error">Редактировать можно только черновик</Alert>;
  return <EditForm key={query.data.id} event={query.data} />;
}
