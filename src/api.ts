import { invoke } from '@tauri-apps/api/core';
import type { Dashboard, Health, SyncPreview } from './types';

async function call<T>(method: string, payload: Record<string, unknown> = {}): Promise<T> {
  return invoke<T>('worker_command', { method, payload });
}

export const api = {
  dashboard: () => call<Dashboard>('dashboard'),
  health: () => call<Health>('health_check'),
  importPublicProfile: (url: string) => call<Dashboard>('import_public_profile', { url }),
  importPlaylist: (url: string) => call<Dashboard>('import_playlist_url', { url }),
  seedDemo: () => call<Dashboard>('seed_demo'),
  queueTrack: (videoId: string) => call<Dashboard>('queue_track', { video_id: videoId }),
  queuePlaylist: (playlistId: string, missingOnly: boolean) => call<Dashboard>('queue_playlist', { playlist_id: playlistId, missing_only: missingOnly }),
  startQueue: () => invoke<Dashboard>('start_queue'),
  openLibrary: () => invoke<Dashboard>('open_library'),
  repairLibraryMetadata: () => call<Dashboard>('repair_library_metadata'),
  resetAndResyncLibrary: () => call<Dashboard>('reset_and_resync_library'),
  cancelJob: (jobId: string) => call<Dashboard>('cancel_job', { job_id: jobId }),
  retryJob: (jobId: string) => call<Dashboard>('retry_job', { job_id: jobId }),
  setLoaded: (playlistId: string, loaded: boolean) => call<Dashboard>('set_loaded_playlist', { playlist_id: playlistId, loaded }),
  syncPreview: (mountPath: string) => call<SyncPreview>('sync_preview', { mount_path: mountPath }),
  syncApply: (mountPath: string) => call<SyncPreview>('sync_apply', { mount_path: mountPath }),
  syncStatus: (mountPath: string) => call<{ active: boolean; state: string; completed: number; total: number; current?: string }>('sync_status', { mount_path: mountPath }),
};
