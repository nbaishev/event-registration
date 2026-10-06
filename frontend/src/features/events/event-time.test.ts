import { describe, expect, it } from 'vitest';
import { localTimeCandidates, resolveLocalTime, toLocalDateTimeInput } from './event-time';

describe('event local time conversion', () => {
  it('uses the selected timezone instead of the browser timezone', () => {
    expect(resolveLocalTime('2026-10-10T18:30', 'Asia/Almaty')).toBe('2026-10-10T13:30:00.000Z');
    expect(resolveLocalTime('2026-10-10T18:30', 'UTC')).toBe('2026-10-10T18:30:00.000Z');
    expect(resolveLocalTime('2026-10-10T18:30', 'Asia/Kathmandu')).toBe('2026-10-10T12:45:00.000Z');
  });
  it('rejects a nonexistent DST time instead of silently shifting it', () => {
    expect(localTimeCandidates('2027-03-14T02:30', 'America/New_York')).toEqual([]);
    expect(() => resolveLocalTime('2027-03-14T02:30', 'America/New_York')).toThrow('не существует');
  });
  it('requires explicit offset selection for an ambiguous DST time', () => {
    const local = '2026-11-01T01:30', zone = 'America/New_York';
    expect(localTimeCandidates(local, zone)).toEqual(['2026-11-01T05:30:00.000Z', '2026-11-01T06:30:00.000Z']);
    expect(() => resolveLocalTime(local, zone)).toThrow('Выберите');
    expect(resolveLocalTime(local, zone, '2026-11-01T06:30:00.000Z')).toBe('2026-11-01T06:30:00.000Z');
    expect(() => resolveLocalTime(local, zone, '2026-11-02T06:30:00.000Z')).toThrow();
  });
  it('prefills an ambiguous local time from its exact saved instant', () => {
    const instant = '2026-11-01T06:30:00Z', zone = 'America/New_York';
    const local = toLocalDateTimeInput(instant, zone);
    expect(local).toBe('2026-11-01T01:30');
    expect(resolveLocalTime(local, zone, localTimeCandidates(local, zone).find(
      candidate => Date.parse(candidate) === Date.parse(instant),
    ))).toBe('2026-11-01T06:30:00.000Z');
  });
  it('rejects invalid dates and IANA zones', () => {
    for (const local of ['', '2026-02-30T12:00', '2026-13-01T12:00', 'not-a-date']) {
      expect(() => resolveLocalTime(local, 'UTC')).toThrow();
    }
    expect(() => resolveLocalTime('2026-10-10T18:30', 'Not/AZone')).toThrow();
  });
});
