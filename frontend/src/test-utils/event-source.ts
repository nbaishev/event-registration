export class FakeEventSource {
  static instances: FakeEventSource[] = [];
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  closed = false;
  private listeners = new Map<string, () => void>();
  constructor(readonly url: string) { FakeEventSource.instances.push(this); }
  addEventListener(type: string, callback: () => void) { this.listeners.set(type, callback); }
  close() { this.closed = true; }
  open() { this.onopen?.(); }
  fail() { this.onerror?.(); }
  signal() { this.listeners.get('stats_changed')?.(); }
}
