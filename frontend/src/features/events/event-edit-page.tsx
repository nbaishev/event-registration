import { Alert, Button, Paper, Stack, TextField, Typography } from '@mui/material';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useMemo, useState, type FormEvent } from 'react';
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

function EditForm({ event }: { event: EventResponse }) {
  const initialStarts = toLocalDateTimeInput(event.starts_at, event.timezone);
  const initialEnds = toLocalDateTimeInput(event.ends_at, event.timezone);
  const [title, setTitle] = useState(event.title), [description, setDescription] = useState(event.description);
  const [timezone, setTimezone] = useState(event.timezone);
  const [starts, setStarts] = useState(initialStarts);
  const [ends, setEnds] = useState(initialEnds);
  const [capacity, setCapacity] = useState(String(event.capacity));
  const [startChoice, setStartChoice] = useState(() => choiceFor(event.starts_at, initialStarts, event.timezone));
  const [endChoice, setEndChoice] = useState(() => choiceFor(event.ends_at, initialEnds, event.timezone));
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
      const starts_at = starts === initialStarts && timezone === event.timezone
        && (!startChoice || Date.parse(startChoice) === Date.parse(event.starts_at))
        ? event.starts_at : resolveLocalTime(starts, timezone, startChoice);
      const ends_at = ends === initialEnds && timezone === event.timezone
        && (!endChoice || Date.parse(endChoice) === Date.parse(event.ends_at))
        ? event.ends_at : resolveLocalTime(ends, timezone, endChoice);
      if (Date.parse(ends_at) <= Date.parse(starts_at)) throw new Error('Окончание должно быть позже начала');
      body = { title: normalizedTitle, description, starts_at, ends_at, timezone, capacity: Number(capacity), regenerate_slug: regenerate };
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Проверьте данные формы'); return; }
    setPending(true);
    try {
      const updated = await patchEvent(event.id, body);
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
    <TextField label="Название" required value={title} onChange={e => setTitle(e.target.value)} disabled={pending} helperText="От 1 до 200 символов" />
    <TextField label="Описание" required multiline minRows={4} value={description} onChange={e => setDescription(e.target.value)} disabled={pending} helperText="От 1 до 10 000 символов" />
    <TextField label="Часовой пояс IANA" required value={timezone} onChange={e => { setTimezone(e.target.value); setStartChoice(''); setEndChoice(''); }} disabled={pending} helperText="Например, Asia/Almaty или Europe/Berlin" />
    <TextField label="Начало" type="datetime-local" required slotProps={{ inputLabel: { shrink: true } }} value={starts} onChange={e => { setStarts(e.target.value); setStartChoice(''); }} disabled={pending} />
    {startCandidates.length > 1 && <TextField label="Смещение начала" select slotProps={{ select: { native: true }, inputLabel: { shrink: true } }} value={startChoice} onChange={e => setStartChoice(e.target.value)} disabled={pending} helperText="Это время встречается дважды при смене часового пояса"><option value="">Выберите смещение</option>{startCandidates.map(instant => <option key={instant} value={instant}>{offsetLabel(starts, instant)}</option>)}</TextField>}
    <TextField label="Окончание" type="datetime-local" required slotProps={{ inputLabel: { shrink: true } }} value={ends} onChange={e => { setEnds(e.target.value); setEndChoice(''); }} disabled={pending} />
    {endCandidates.length > 1 && <TextField label="Смещение окончания" select slotProps={{ select: { native: true }, inputLabel: { shrink: true } }} value={endChoice} onChange={e => setEndChoice(e.target.value)} disabled={pending} helperText="Это время встречается дважды при смене часового пояса"><option value="">Выберите смещение</option>{endCandidates.map(instant => <option key={instant} value={instant}>{offsetLabel(ends, instant)}</option>)}</TextField>}
    <TextField label="Количество мест" type="number" required value={capacity} onChange={e => setCapacity(e.target.value)} disabled={pending} />
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
