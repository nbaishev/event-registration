import { Alert, Button, Paper, Stack, TextField, Typography } from '@mui/material';
import { useQueryClient } from '@tanstack/react-query';
import { useMemo, useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router';
import { ApiError } from '../../api/client';
import { createEvent, eventKeys, type EventCreateRequest } from './api';
import { localTimeCandidates, offsetLabel, resolveLocalTime } from './event-time';
function candidates(local: string, timezone: string) {
  try { return localTimeCandidates(local, timezone); } catch { return []; }
}
export function EventCreatePage() {
  const [title, setTitle] = useState(''), [description, setDescription] = useState('');
  const [starts, setStarts] = useState(''), [ends, setEnds] = useState('');
  const [timezone, setTimezone] = useState(() => Intl.DateTimeFormat().resolvedOptions().timeZone);
  const [capacity, setCapacity] = useState('1');
  const [startChoice, setStartChoice] = useState(''), [endChoice, setEndChoice] = useState('');
  const [pending, setPending] = useState(false), [error, setError] = useState<string>();
  const startCandidates = useMemo(() => candidates(starts, timezone), [starts, timezone]);
  const endCandidates = useMemo(() => candidates(ends, timezone), [ends, timezone]);
  const client = useQueryClient(), navigate = useNavigate();
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); if (pending) return;
    setError(undefined);
    let body: EventCreateRequest;
    try {
      const normalizedTitle = title.trim();
      if ([...normalizedTitle].length < 1 || [...normalizedTitle].length > 200) throw new Error('Название должно содержать от 1 до 200 символов');
      if ([...description].length < 1 || [...description].length > 10000) throw new Error('Описание должно содержать от 1 до 10 000 символов');
      if (!/^\d+$/.test(capacity) || !Number.isSafeInteger(Number(capacity)) || Number(capacity) < 1 || Number(capacity) > 2147483647) throw new Error('Количество мест должно быть целым числом от 1 до 2 147 483 647');
      const starts_at = resolveLocalTime(starts, timezone, startChoice), ends_at = resolveLocalTime(ends, timezone, endChoice);
      if (Date.parse(ends_at) <= Date.parse(starts_at)) throw new Error('Окончание должно быть позже начала');
      body = { title: normalizedTitle, description, starts_at, ends_at, timezone, capacity: Number(capacity) };
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Проверьте данные формы'); return; }
    setPending(true);
    try {
      const event = await createEvent(body);
      client.setQueryData(eventKeys.detail(event.owner_id, event.id), event);
      void client.invalidateQueries({ queryKey: eventKeys.mine(event.owner_id) });
      navigate(`/organizer/events/${event.id}`);
    } catch (cause) {
      setError(cause instanceof ApiError && cause.code === 'VALIDATION_ERROR' ? 'Проверьте данные формы: начало должно быть в будущем, даты и поля должны быть корректны' : cause instanceof ApiError && cause.code === 'CSRF_INVALID' ? 'Защита запроса обновлена. Повторите попытку' : 'Не удалось создать мероприятие. Повторите попытку');
    } finally { setPending(false); }
  }
  return <Paper variant="outlined" sx={{ p: 4 }}><Stack component="form" noValidate onSubmit={submit} spacing={3}>
    <Typography component="h1" variant="h4">Создать мероприятие</Typography>
    <Typography color="text.secondary">Сохраним мероприятие как черновик. Даты указываются в выбранном часовом поясе.</Typography>
    {error && <Alert severity="error">{error}</Alert>}
    <TextField label="Название" required value={title} onChange={e => setTitle(e.target.value)} disabled={pending} helperText="От 1 до 200 символов" />
    <TextField label="Описание" required multiline minRows={4} value={description} onChange={e => setDescription(e.target.value)} disabled={pending} helperText="От 1 до 10 000 символов" />
    <TextField label="Часовой пояс IANA" required value={timezone} onChange={e => { setTimezone(e.target.value); setStartChoice(''); setEndChoice(''); }} disabled={pending} helperText="Например, Asia/Almaty или Europe/Berlin" />
    <TextField label="Начало" type="datetime-local" required slotProps={{ inputLabel: { shrink: true } }} value={starts} onChange={e => { setStarts(e.target.value); setStartChoice(''); }} disabled={pending} />
    {startCandidates.length > 1 && <TextField label="Смещение начала" select slotProps={{ select: { native: true }, inputLabel: { shrink: true } }} value={startChoice} onChange={e => setStartChoice(e.target.value)} disabled={pending} helperText="Это время встречается дважды при смене часового пояса"><option value="">Выберите смещение</option>{startCandidates.map(instant => <option key={instant} value={instant}>{offsetLabel(starts, instant)}</option>)}</TextField>}
    <TextField label="Окончание" type="datetime-local" required slotProps={{ inputLabel: { shrink: true } }} value={ends} onChange={e => { setEnds(e.target.value); setEndChoice(''); }} disabled={pending} />
    {endCandidates.length > 1 && <TextField label="Смещение окончания" select slotProps={{ select: { native: true }, inputLabel: { shrink: true } }} value={endChoice} onChange={e => setEndChoice(e.target.value)} disabled={pending} helperText="Это время встречается дважды при смене часового пояса"><option value="">Выберите смещение</option>{endCandidates.map(instant => <option key={instant} value={instant}>{offsetLabel(ends, instant)}</option>)}</TextField>}
    <TextField label="Количество мест" type="number" required value={capacity} onChange={e => setCapacity(e.target.value)} disabled={pending} />
    <Button type="submit" variant="contained" disabled={pending}>{pending ? 'Сохраняем…' : 'Создать черновик'}</Button>
  </Stack></Paper>;
}
