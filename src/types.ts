export type Track = {
  id: string;
  playlist_id: string;
  position: number;
  video_id: string;
  title: string;
  artist: string;
  album?: string;
  duration?: string;
  artwork_url?: string;
  local_status: 'missing' | 'ready' | 'failed' | 'queued' | 'downloading' | 'unavailable';
  media_path?: string;
};

export type Playlist = {
  id: string;
  title: string;
  source: string;
  kind: 'collection' | 'unsorted';
  track_count: number;
  loaded: boolean;
  updated_at: string;
};

export type Job = {
  id: string;
  video_id: string;
  title: string;
  artist: string;
  state: string;
  attempts: number;
  error_code?: string;
  error_message?: string;
  updated_at: string;
};

export type Health = {
  app_data: string;
  library_root: string;
  free_bytes: number;
  minimum_free_bytes: number;
  dependencies: Record<string, { available: boolean; path?: string; detail?: string }>;
};

export type Dashboard = {
  playlists: Playlist[];
  tracks: Track[];
  jobs: Job[];
  health: Health;
  public_profile_url?: string | null;
  sync_notice?: string | null;
  activity?: { label: string; completed: number; total: number } | null;
  device?: { name: string; mount_path: string; managed_root: string };
};

export type SyncPreview = {
  device: string;
  managed_root: string;
  files_to_copy: number;
  files_to_remove: number;
  projected_bytes: number;
  existing_bytes: number;
  duplicate_files: number;
  physical_files_after: number;
  shuffle_bias: string;
  warnings: string[];
  additions: string[];
  removals: string[];
};
