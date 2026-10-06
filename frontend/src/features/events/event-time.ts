// Match local wall time against possible instants; do not let Date silently normalize DST gaps.
function wallTime(formatter: Intl.DateTimeFormat, instant: number): number {
  const values: Record<string, number> = {};
  for (const part of formatter.formatToParts(instant)) if (part.type !== 'literal') values[part.type] = Number(part.value);
  return Date.UTC(values.year, values.month - 1, values.day, values.hour, values.minute);
}
export function localTimeCandidates(local: string, timezone: string): string[] {
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(local)) throw new Error('Укажите дату и время');
  const localEpoch = Date.parse(`${local}:00.000Z`);
  if (!Number.isFinite(localEpoch) || new Date(localEpoch).toISOString().slice(0, 16) !== local) throw new Error('Укажите корректную дату и время');
  let formatter: Intl.DateTimeFormat;
  try { formatter = new Intl.DateTimeFormat('en-GB', { timeZone: timezone, year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }); }
  catch { throw new Error('Укажите корректный часовой пояс IANA'); }
  const offsets = new Set<number>();
  // Sample both sides of nearby timezone transitions, including non-hour offsets.
  for (let hour = -36; hour <= 36; hour++) {
    const instant = localEpoch + hour * 3600000;
    offsets.add(wallTime(formatter, instant) - instant);
  }
  return [...offsets].map(offset => localEpoch - offset)
    .filter(instant => wallTime(formatter, instant) === localEpoch)
    .sort((a, b) => a - b).map(instant => new Date(instant).toISOString());
}
export function resolveLocalTime(local: string, timezone: string, selected?: string): string {
  const candidates = localTimeCandidates(local, timezone);
  if (!candidates.length) throw new Error('Это время не существует в выбранном часовом поясе');
  if (selected) {
    if (!candidates.includes(selected)) throw new Error('Выберите действующее смещение времени');
    return selected;
  }
  if (candidates.length > 1) throw new Error('Выберите смещение для неоднозначного времени');
  return candidates[0];
}
export function offsetLabel(local: string, instant: string): string {
  const minutes = (Date.parse(`${local}:00Z`) - Date.parse(instant)) / 60000;
  return `UTC${minutes < 0 ? '−' : '+'}${String(Math.floor(Math.abs(minutes) / 60)).padStart(2, '0')}:${String(Math.abs(minutes) % 60).padStart(2, '0')}`;
}
export function formatEventTime(instant: string, timezone: string): string {
  return new Intl.DateTimeFormat('ru-RU', { timeZone: timezone, dateStyle: 'medium', timeStyle: 'short' }).format(new Date(instant));
}
export function toLocalDateTimeInput(instant: string, timezone: string): string {
  const values: Record<string, string> = {};
  for (const part of new Intl.DateTimeFormat('en-CA', {
    timeZone: timezone, year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
  }).formatToParts(new Date(instant))) {
    if (part.type !== 'literal') values[part.type] = part.value;
  }
  return `${values.year}-${values.month}-${values.day}T${values.hour}:${values.minute}`;
}
