import type { Snapshot, SharedFile, Folder, Device, Transfer, UploadStatus } from './models.js';
export type { Snapshot, SharedFile, Folder, Device, Transfer, UploadStatus } from './models.js';

export class ApiError extends Error {
  constructor(message: string, public status: number, public code = 'request-failed') { super(message); }
}
const object = (value: unknown): value is Record<string, unknown> => Boolean(value) && typeof value === 'object' && !Array.isArray(value);
const text = (value: unknown): value is string => typeof value === 'string';
const number = (value: unknown): value is number => typeof value === 'number' && Number.isFinite(value);
const file = (value: unknown): value is SharedFile => object(value) && text(value.id) && /^[a-f0-9]{24}$/.test(value.id) && text(value.name) && number(value.size) && value.size >= 0 && number(value.modified) && text(value.extension) && text(value.source) && (value.folder === null || text(value.folder));
const folder = (value: unknown): value is Folder => object(value) && text(value.id) && text(value.path) && text(value.name) && text(value.error) && number(value.count) && value.count >= 0;
const device = (value: unknown): value is Device => object(value) && text(value.id) && text(value.name) && number(value.seen) && text(value.peer);
const transfer = (value: unknown): value is Transfer => object(value) && text(value.id) && text(value.name) && number(value.size) && ['sent','received'].includes(String(value.direction)) && text(value.device) && number(value.time);
const array = <T>(value: unknown, valid: (value: unknown) => value is T): value is T[] => Array.isArray(value) && value.every(valid);

export function parseSnapshot(value: unknown): Snapshot {
  if (!object(value) || !['admin','phone'].includes(String(value.role)) || !text(value.computer) || !text(value.version) || !text(value.warning) || typeof value.testMode !== 'boolean' || !array(value.files, file)) throw new ApiError('文件列表格式不完整，请刷新重试。', 502, 'response-invalid');
  if (value.role === 'admin') {
    if (!text(value.pairUrl) || !text(value.address) || !array(value.addresses, text) || !number(value.port) || !text(value.inboxPath) || !array(value.folders, folder) || !array(value.devices, device) || !array(value.history, transfer) || !array(value.received, file) || !object(value.settingsStatus) || typeof value.settingsStatus.protected !== 'boolean' || !text(value.settingsStatus.reason) || !number(value.activeTransfers)) throw new ApiError('电脑状态格式不完整，请重新打开程序。', 502, 'response-invalid');
    let url: URL;
    try { url = new URL(value.pairUrl); } catch { throw new ApiError('手机连接地址不正确。', 502, 'response-invalid'); }
    if (url.protocol !== 'http:' || url.pathname !== '/' || !url.hash.startsWith('#pair=') || url.username || url.password) throw new ApiError('手机连接地址不正确。', 502, 'response-invalid');
  }
  return value as unknown as Snapshot;
}

export function parseUpload(value: unknown): UploadStatus {
  if (!object(value) || !text(value.id) || !/^[a-f0-9]{32}$/.test(value.id) || !text(value.name) || !number(value.size) || typeof value.shared !== 'boolean' || !['queued','receiving','saving','completed','cancelled','failed'].includes(String(value.phase)) || !number(value.received) || value.received < 0 || value.received > value.size || !text(value.savedName) || !text(value.error)) throw new ApiError('发送结果格式不完整，请检查任务状态。', 502, 'response-invalid');
  return value as unknown as UploadStatus;
}

export async function request<T = unknown>(path: string, body?: object, options: { signal?: AbortSignal; timeout?: number } = {}): Promise<T> {
  const controller = new AbortController();
  const abort = (): void => controller.abort();
  options.signal?.addEventListener('abort', abort, { once: true });
  if (options.signal?.aborted) abort();
  const timer = setTimeout(abort, options.timeout ?? 20000);
  try {
    const response = await fetch(path, { method: body === undefined ? 'GET' : 'POST', headers: { 'X-LanDrop': '1', ...(body === undefined ? {} : { 'Content-Type': 'application/json' }) }, body: body === undefined ? undefined : JSON.stringify(body), signal: controller.signal, credentials: 'same-origin' });
    const data: unknown = await response.json();
    if (!response.ok) throw new ApiError(object(data) && text(data.error) ? data.error : '操作失败，请重试。', response.status, object(data) && text(data.code) ? data.code : 'request-failed');
    return data as T;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    if (options.signal?.aborted) throw new ApiError('请求已停止。', 499, 'request-aborted');
    throw new ApiError('连接中断，请检查电脑程序和 Wi-Fi，连接恢复后再试。', 0, 'network-unavailable');
  } finally { clearTimeout(timer); options.signal?.removeEventListener('abort', abort); }
}

export const getState = async (signal?: AbortSignal): Promise<Snapshot> => parseSnapshot(await request('/api/state', undefined, { signal }));
export const createUpload = async (id: string, file: File): Promise<UploadStatus> => parseUpload(await request('/api/uploads', { id, name: file.name, size: file.size }));
export const uploadStatus = async (id: string): Promise<UploadStatus> => parseUpload(await request(`/api/uploads/${id}`));
export const cancelUpload = async (id: string): Promise<UploadStatus> => parseUpload(await request(`/api/uploads/${id}/cancel`, {}));

export function upload(id: string, file: File, progress: (percent: number) => void): { promise: Promise<UploadStatus>; cancel: () => void } {
  const xhr = new XMLHttpRequest();
  const promise = new Promise<UploadStatus>((resolve, reject) => {
    xhr.open('POST', `/api/upload?id=${id}`); xhr.setRequestHeader('X-LanDrop', '1'); xhr.setRequestHeader('Content-Type', 'application/octet-stream');
    xhr.upload.onprogress = event => { if (event.lengthComputable) progress(Math.round(event.loaded / event.total * 100)); };
    xhr.onload = () => {
      try {
        const value: unknown = JSON.parse(xhr.responseText);
        if (xhr.status === 201) resolve(parseUpload(value));
        else reject(new ApiError(object(value) && text(value.error) ? value.error : '文件未能保存。', xhr.status, object(value) && text(value.code) ? value.code : 'upload-failed'));
      } catch (error) { reject(error instanceof ApiError ? error : new ApiError('发送结果未确认，请检查任务状态。', 502, 'response-invalid')); }
    };
    xhr.onerror = () => reject(new ApiError('连接中断，请检查发送结果。', 0, 'network-unavailable'));
    xhr.onabort = () => reject(new ApiError('发送已停止，正在确认结果。', 499, 'upload-aborted'));
    xhr.send(file);
  });
  return { promise, cancel: () => xhr.abort() };
}

export async function checkDownload(path: string): Promise<void> {
  const controller = new AbortController(); const timer = setTimeout(() => controller.abort(), 20000);
  try {
    const response = await fetch(path, { method: 'HEAD', credentials: 'same-origin', signal: controller.signal });
    if (!response.ok) {
      const messages: Record<number,string> = { 401: '连接已失效，请重新连接。', 403: '文件路径已改变，请在电脑上重新共享。', 404: '文件已移动或取消共享。', 409: '文件正在更新，请刷新列表后再下载。' };
      const encoded = response.headers.get('X-LanDrop-Error');
      let message = messages[response.status] ?? '暂时无法下载，请稍后重试。';
      try { if (encoded) message = decodeURIComponent(encoded); } catch { /* Use the status fallback. */ }
      throw new ApiError(message, response.status, response.headers.get('X-LanDrop-Code') ?? 'download-failed');
    }
  } catch (error) { if (error instanceof ApiError) throw error; throw new ApiError('无法连接电脑，请检查 Wi-Fi 后重试。', 0); }
  finally { clearTimeout(timer); }
}
