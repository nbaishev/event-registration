import { Alert, Button, Stack, TextField, Typography } from '@mui/material';
import { useQueryClient } from '@tanstack/react-query';
import { useEffect, useRef, useState, type FormEvent } from 'react';
import { ApiError } from '../../api/client';
import { eventKeys, patchEvent, publicEventKey, type EventResponse } from './api';

const validationMessage = 'Укажите целое число мест от 1 до 2 147 483 647';
const retryMessage = 'Не удалось сохранить количество мест. Повторите попытку.';

export function EventCapacityForm({ event }: { event: EventResponse }) {
  const [capacity, setCapacity] = useState(String(event.capacity));
  const previous = useRef(String(event.capacity));
  const [pending, setPending] = useState(false);
  const saving = useRef(false);
  const [error, setError] = useState<string>();
  const client = useQueryClient();
  useEffect(() => {
    const incoming = String(event.capacity);
    const baseline = previous.current;
    setCapacity(current => current === baseline ? incoming : current);
    previous.current = incoming;
  }, [event.capacity]);

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (saving.current) return;
    setError(undefined);
    const value = Number(capacity);
    if (!/^\d+$/.test(capacity) || !Number.isSafeInteger(value) || value < 1 || value > 2147483647) {
      setError(validationMessage);
      return;
    }
    if (value === event.capacity) return;
    saving.current = true;
    setPending(true);
    try {
      const saved = await patchEvent(event.id, { capacity: value });
      const key = eventKeys.detail(saved.owner_id, saved.id);
      await client.cancelQueries({ queryKey: key, exact: true });
      previous.current = String(saved.capacity);
      setCapacity(String(saved.capacity));
      client.setQueryData(key, saved);
      void client.invalidateQueries({ queryKey: eventKeys.mine(saved.owner_id) });
      void client.invalidateQueries({ queryKey: publicEventKey(saved.slug), exact: true });
    } catch (cause) {
      setError(cause instanceof ApiError ? {
        CAPACITY_BELOW_CONFIRMED: 'Количество мест не может быть меньше числа подтверждённых участников.',
        EVENT_ALREADY_STARTED: 'Мероприятие уже началось. Количество мест изменить нельзя.',
        EVENT_CANCELLED: 'Мероприятие отменено. Количество мест изменить нельзя.',
        EVENT_NOT_EDITABLE: 'Нельзя изменить количество мест в текущем состоянии мероприятия.',
        EVENT_NOT_OWNER: 'Нет доступа к этому мероприятию.',
        EVENT_NOT_FOUND: 'Мероприятие не найдено.',
        VALIDATION_ERROR: validationMessage,
        CSRF_INVALID: 'Защита запроса обновлена. Повторите попытку.',
        SERVICE_UNAVAILABLE: retryMessage,
      }[cause.code] ?? retryMessage : retryMessage);
    } finally {
      saving.current = false;
      setPending(false);
    }
  }

  return <Stack component="form" noValidate onSubmit={submit} spacing={2}>
    <Typography component="h2" variant="h6">Изменить количество мест</Typography>
    <Typography color="text.secondary">При увеличении количества мест участники из списка ожидания получат свободные места по очереди.</Typography>
    {error && <Alert severity="error">{error}</Alert>}
    <TextField label="Количество мест" type="number" value={capacity} onChange={e => setCapacity(e.target.value)} disabled={pending} slotProps={{ htmlInput: { min: 1, max: 2147483647, step: 1 } }} />
    <Button type="submit" variant="contained" disabled={pending || Number(capacity) === event.capacity}>{pending ? 'Сохраняем…' : 'Сохранить количество мест'}</Button>
  </Stack>;
}
