import { ApiError, getState } from './api.js';
import type { Snapshot } from './models.js';

export type ConnectionPhase = 'starting' | 'connected' | 'reconnecting' | 'unauthorized' | 'stopped';
export interface Connection { phase: ConnectionPhase; snapshot: Snapshot | null; error: string }

export class SessionController {
  connection: Connection = { phase: 'starting', snapshot: null, error: '' };
  epoch = 0;
  private revision = 0;
  private pending: Promise<void> | null = null;
  private controller: AbortController | null = null;
  constructor(private notify: (connection: Connection) => void, private load = getState, private desktop = false) {}

  private publish(connection: Connection): void { this.connection = connection; this.notify(connection); }

  connect(bootstrap: (signal: AbortSignal) => Promise<void>): Promise<void> {
    this.epoch++; this.revision++; this.controller?.abort(); this.pending = null;
    this.publish({ phase: 'starting', snapshot: null, error: '' });
    return this.execute(bootstrap);
  }

  refresh(): Promise<void> {
    if (this.connection.phase === 'stopped') return Promise.resolve();
    return this.pending ?? this.execute();
  }

  async invalidate(): Promise<void> {
    const epoch = this.epoch;
    this.revision++;
    if (this.pending) await this.pending;
    if (epoch === this.epoch) await this.refresh();
  }

  private execute(bootstrap?: (signal: AbortSignal) => Promise<void>): Promise<void> {
    const epoch = this.epoch, revision = this.revision;
    const controller = new AbortController(); this.controller = controller;
    const task = (async () => {
      try {
        if (bootstrap) await bootstrap(controller.signal);
        const snapshot = await this.load(controller.signal);
        if (epoch !== this.epoch || revision !== this.revision || controller.signal.aborted) return;
        if (this.desktop && snapshot.role !== 'admin') throw new ApiError('请重新打开电脑端恢复登录。', 401, 'session-expired');
        this.publish({ phase: 'connected', snapshot, error: '' });
      } catch (error) {
        if (epoch !== this.epoch || revision !== this.revision || controller.signal.aborted) return;
        if (error instanceof ApiError && [401,403].includes(error.status)) this.publish({ phase: 'unauthorized', snapshot: null, error: error.message });
        else this.publish({ phase: 'reconnecting', snapshot: this.connection.snapshot, error: error instanceof Error ? error.message : '连接中断，请重试。' });
      }
    })();
    const pending = task.finally(() => { if (this.pending === pending) this.pending = null; });
    this.pending = pending; return pending;
  }

  stop(): void {
    this.epoch++; this.controller?.abort(); this.pending = null;
    this.publish({ phase: 'stopped', snapshot: null, error: '' });
  }
}
