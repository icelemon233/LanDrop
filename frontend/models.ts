export interface SharedFile { id: string; name: string; size: number; modified: number; extension: string; source: string; folder: string | null }
export interface Folder { id: string; path: string; name: string; error: string; count: number; status?: 'checking' | 'ready' }
export interface Device { id: string; name: string; seen: number; peer: string }
export interface Transfer { id: string; name: string; size: number; direction: 'sent' | 'received'; device: string; time: number }
export interface Snapshot {
  role: 'admin' | 'phone'; computer: string; files: SharedFile[]; version: string; warning: string;
  pairUrl?: string; addresses?: string[]; address?: string; port?: number; inboxPath?: string;
  folders?: Folder[]; devices?: Device[]; history?: Transfer[]; received?: SharedFile[];
  settingsStatus?: { protected: boolean; reason: string }; activeTransfers?: number;
  testMode: boolean; scanning?: boolean;
  desktop?: { closeBehavior: 'tray' | 'exit'; trayAvailable: boolean };
}
export type UploadPhase = 'queued' | 'receiving' | 'saving' | 'completed' | 'cancelled' | 'failed';
export interface UploadStatus { id: string; name: string; size: number; shared: boolean; phase: UploadPhase; received: number; savedName: string; error: string }
