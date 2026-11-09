import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Check, CircleAlert, Disc3, Download, FolderOpen, HardDrive, Library, ListMusic, ListPlus,
  LoaderCircle, Music2, Play, RefreshCw, Search, Settings, Trash2, X,
} from 'lucide-react';
import { api } from './api';
import type { Dashboard, Job, Playlist, SyncPreview, Track } from './types';

type View = 'library' | 'queue' | 'device' | 'settings';

const bytes = (n: number) => {
  if (!n) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB'];
  const p = Math.min(Math.floor(Math.log(n) / Math.log(1024)), units.length - 1);
  return `${(n / 1024 ** p).toFixed(p > 1 ? 1 : 0)} ${units[p]}`;
};

const relative = (stamp?: string) => stamp ? new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric' }).format(new Date(stamp)) : '—';

function Downloaded({ status }: { status: Track['local_status'] }) {
  const labels = { ready: 'Downloaded', queued: 'Queued', downloading: 'Downloading', missing: 'Not downloaded', failed: 'Failed', unavailable: 'Unavailable' };
  return <span className={`downloaded ${status}`} title={labels[status]} aria-label={labels[status]}><Download size={16} /></span>;
}

export default function App() {
  const [data, setData] = useState<Dashboard>();
  const [view, setView] = useState<View>('library');
  const [selectedPlaylist, setSelectedPlaylist] = useState<string>();
  const [selectedTrack, setSelectedTrack] = useState<Track>();
  const [search, setSearch] = useState('');
  const [importUrl, setImportUrl] = useState('');
  const [profileUrl, setProfileUrl] = useState(import.meta.env.VITE_DEFAULT_PROFILE_URL ?? '');
  const [mountPath, setMountPath] = useState('/Volumes/ECHO_NANO');
  const [preview, setPreview] = useState<SyncPreview>();
  const [syncProgress, setSyncProgress] = useState<{ state: string; completed: number; total: number; current?: string }>();
  const [trackLimit, setTrackLimit] = useState(100);
  const [busy, setBusy] = useState<string>();
  const [notice, setNotice] = useState<string>();
  const [error, setError] = useState<string>();
  const [confirmReset, setConfirmReset] = useState(false);
  const [deleteCollection, setDeleteCollection] = useState<Playlist>();

  const reload = useCallback(async () => {
    try { setData(await api.dashboard()); setError(undefined); }
    catch (e) { setError(String(e)); }
  }, []);
  useEffect(() => {
    void api.bootstrapDependencies().then((dashboard) => { setData(dashboard); setError(undefined); }).catch((e) => setError(String(e)));
  }, []);
  useEffect(() => { setTrackLimit(100); }, [selectedPlaylist, view, search]);

  const work = async (label: string, fn: () => Promise<Dashboard | SyncPreview>) => {
    setBusy(label); setError(undefined);
    try {
      const result = await fn();
      if ('playlists' in result) { setData(result); if (result.sync_notice) setNotice(result.sync_notice); }
      else { setPreview(result); await reload(); }
    } catch (e) { setError(String(e)); }
    finally { setBusy(undefined); }
  };
  const resetLibrary = async () => {
    setBusy('reset'); setError(undefined); setNotice('Clearing library…');
    try {
      setData(await api.resetAndResyncLibrary());
      setSelectedPlaylist(undefined); setSelectedTrack(undefined);
      setNotice('Library cleared.');
    } catch (e) { setError(String(e)); }
    finally { setBusy(undefined); }
  };
  useEffect(() => {
    if (busy !== 'sync') return;
    const update = () => api.syncStatus(mountPath).then((status) => setSyncProgress(status)).catch(() => undefined);
    update();
    const timer = window.setInterval(update, 500);
    return () => window.clearInterval(timer);
  }, [busy, mountPath]);
  useEffect(() => {
    if (busy !== 'download' && busy !== 'repair' && busy !== 'profile' && busy !== 'reset') return;
    const timer = window.setInterval(() => { void api.dashboard().then(setData).catch(() => undefined); }, 650);
    return () => window.clearInterval(timer);
  }, [busy]);

  const playlists = data?.playlists ?? [];
  const activePlaylist = playlists.find((item) => item.id === selectedPlaylist) ?? playlists[0];
  const activeJobs = data?.jobs ?? [];
  const queueJobs = activeJobs.filter((job) => !['completed', 'cancelled'].includes(job.state));
  const activeQueueCount = queueJobs.filter((job) => ['queued', 'running', 'retry'].includes(job.state)).length;
  useEffect(() => {
    if (!activeQueueCount) return;
    const timer = window.setInterval(() => { void api.dashboard().then(setData).catch(() => undefined); }, 650);
    return () => window.clearInterval(timer);
  }, [activeQueueCount]);

  const displayTracks = useMemo(() => {
    let tracks = data?.tracks ?? [];
    if (view === 'library') tracks = tracks.filter((track) => track.playlist_id === activePlaylist?.id);
    return tracks.filter((track) => `${track.title} ${track.artist} ${track.album ?? ''}`.toLowerCase().includes(search.toLowerCase()));
  }, [data, view, search, activePlaylist?.id]);
  const activeTrack = view === 'library' ? selectedTrack ?? displayTracks[0] : undefined;
  const visibleTracks = displayTracks.slice(0, trackLimit);
  const queueCount = activeQueueCount;

  if (!data) return <main className="boot">{error ? <><CircleAlert size={24} /><strong>Could not open library</strong><p>{error}</p><button className="button ghost" onClick={() => void reload()}>Try again</button></> : <><LoaderCircle className="spin" size={24} />Loading…</>}</main>;

  const nav = [
    ['library', ListMusic, 'Library'], ['queue', ListPlus, 'Queue'],
    ['device', HardDrive, 'Device'], ['settings', Settings, 'Settings'],
  ] as const;
  const activityLabel: Record<string, string> = { profile: 'Syncing', import: 'Importing', download: 'Downloading', repair: 'Repairing', reset: 'Clearing', preview: 'Preparing', sync: 'Syncing', load: 'Updating', queue: 'Updating', setup: 'Setting up tools' };

  return <main className="app-shell">
    <aside className="sidebar">
      <div className="brand"><span className="brand-mark"><Disc3 size={18} /></span><span>Digital Audio Manager</span></div>
      <nav>{nav.map(([key, Icon, label]) => <button key={key} className={view === key ? 'nav-item active' : 'nav-item'} onClick={() => setView(key)}><Icon size={17} /><span>{label}</span>{key === 'queue' && queueCount > 0 && <b>{queueCount}</b>}</button>)}</nav>
      <div className="collection-label">Library</div>
      <PlaylistList playlists={playlists} activeId={activePlaylist?.id} active={view === 'library'} onSelect={(id) => { setSelectedPlaylist(id); setSelectedTrack(undefined); setView('library'); }} onDelete={setDeleteCollection} />
    </aside>

    <section className="workspace">
      <header className="workspace-header">
        <div>{view === 'device' ? <h1>Device</h1> : view === 'settings' ? <h1>Settings</h1> : view === 'queue' ? <><h1>Queue</h1><p className="subhead">{queueJobs.length} jobs</p></> : <><h1>{activePlaylist?.title ?? 'Library'}</h1><p className="subhead">{displayTracks.length} tracks</p></>}</div>
        <div className="header-actions">{view === 'library' && <><button className="button ghost" disabled={Boolean(busy)} onClick={() => work('refresh', () => api.importPublicProfile(data.public_profile_url ?? profileUrl))}><RefreshCw size={15} />Refresh</button><button className="button ghost" disabled={!activePlaylist || Boolean(busy)} onClick={() => activePlaylist && work('queue', () => api.queuePlaylist(activePlaylist.id, true))}><ListPlus size={15} />Add missing</button><button className="button primary" disabled={!activePlaylist || Boolean(busy)} onClick={() => activePlaylist && work('queue', async () => { await api.queuePlaylist(activePlaylist.id, true); return api.startQueue(); })}><Download size={15} />Download missing</button></>}</div>
      </header>

      {error && <div className="banner error"><CircleAlert size={16} /><span>{error}</span><button onClick={() => setError(undefined)}><X size={15} /></button></div>}
      {notice && <div className="banner notice"><CircleAlert size={16} /><span>{notice}</span><button onClick={() => setNotice(undefined)}><X size={15} /></button></div>}
      {(busy || data.activity) && <div className="activity-progress"><div><LoaderCircle className="spin" size={15} /><span>{data.activity?.label ?? activityLabel[busy ?? ''] ?? 'Working'}{data.activity?.total ? ` · ${data.activity.completed}/${data.activity.total}` : ''}</span></div><i style={{ width: `${data.activity?.total ? Math.max(5, (data.activity.completed / data.activity.total) * 100) : 38}%` }} /></div>}

      {view === 'device' ? <DevicePanel mountPath={mountPath} setMountPath={setMountPath} preview={preview} busy={busy} syncProgress={syncProgress} onPreview={() => work('preview', () => api.syncPreview(mountPath))} onApply={() => work('sync', () => api.syncApply(mountPath))} onOpenLibrary={() => work('library', api.openLibrary)} playlists={playlists.filter((playlist) => playlist.kind === 'collection')} onLoad={(id, loaded) => work('load', () => api.setLoaded(id, loaded))} />
        : view === 'settings' ? <SettingsPanel health={data.health} importUrl={importUrl} setImportUrl={setImportUrl} profileUrl={profileUrl} setProfileUrl={setProfileUrl} busy={busy} onProfile={() => work('profile', () => api.importPublicProfile(profileUrl))} onImport={() => work('import', () => api.importToUnsorted(importUrl))} onRepair={() => work('repair', api.repairLibraryMetadata)} onBootstrap={() => work('setup', api.bootstrapDependencies)} onReset={() => setConfirmReset(true)} />
        : view === 'queue' ? <><div className="toolbar queue-toolbar"><p>{queueJobs.length ? 'Downloads waiting or needing attention.' : 'No downloads are waiting.'}</p><button className="button primary" disabled={!queueCount || Boolean(busy)} onClick={() => work('queue', api.startQueue)}>{busy === 'queue' ? <LoaderCircle className="spin" size={15} /> : <Play size={15} />}Run queue</button></div><QueueTable jobs={queueJobs} busy={busy} onCancel={(id) => work('cancel', () => api.cancelJob(id))} onRetry={(id) => work('retry', () => api.retryJob(id))} /></>
        : <><div className="toolbar"><label className="search"><Search size={16} /><input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Filter this library" /></label></div><TrackTable tracks={visibleTracks} total={displayTracks.length} selected={activeTrack?.id} onSelect={setSelectedTrack} onMore={() => setTrackLimit((count) => Math.min(count + 100, displayTracks.length))} onQueue={(videoId) => work('queue', () => api.queueTrack(videoId))} busy={busy} /></>}
    </section>

    <aside className="inspector">
      <div className="inspector-title">{activeTrack ? 'Track' : 'Queue'}</div>
      {activeTrack ? <TrackInspector track={activeTrack} busy={busy} onQueue={() => work('queue', () => api.queueTrack(activeTrack.video_id))} onDownload={() => work('queue', async () => { await api.queueTrack(activeTrack.video_id); return api.startQueue(); })} /> : <p className="empty-copy">No track selected.</p>}
      <div className="rule" />
      <div className="queue-heading"><span>Queue</span><small>{queueJobs.length}</small></div>
      <div className="job-list">{queueJobs.length ? queueJobs.slice(0, 5).map((job) => <JobRow key={job.id} job={job} busy={busy} onCancel={() => work('cancel', () => api.cancelJob(job.id))} onRetry={() => work('retry', () => api.retryJob(job.id))} />) : <p className="empty-copy">Empty.</p>}</div>
    </aside>
    {confirmReset && <div className="confirm-backdrop" role="dialog" aria-modal="true"><div className="confirm-dialog"><h2>Reset library?</h2><p>Deletes local downloads, metadata, queue, and playlists. Device files stay unchanged.</p><div><button className="button ghost" onClick={() => setConfirmReset(false)}>Cancel</button><button className="button danger" onClick={() => { setConfirmReset(false); void resetLibrary(); }}><X size={15} />Reset</button></div></div></div>}
    {deleteCollection && <div className="confirm-backdrop" role="dialog" aria-modal="true"><div className="confirm-dialog"><h2>Remove {deleteCollection.title}?</h2><p>This removes the collection from Library. Downloaded audio and queued jobs stay available.</p><div><button className="button ghost" onClick={() => setDeleteCollection(undefined)}>Cancel</button><button className="button danger" onClick={() => { const id = deleteCollection.id; setDeleteCollection(undefined); void work('delete', () => api.deleteLibraryCollection(id)); }}><Trash2 size={15} />Remove</button></div></div></div>}
  </main>;
}

function PlaylistList({ playlists, activeId, active, onSelect, onDelete }: { playlists: Playlist[]; activeId?: string; active: boolean; onSelect: (id: string) => void; onDelete: (playlist: Playlist) => void }) {
  const [limit, setLimit] = useState(80);
  useEffect(() => setLimit(80), [playlists.length]);
  const visible = playlists.slice(0, limit);
  return <div className="playlist-list" onScroll={(event) => { const target = event.currentTarget; if (target.scrollTop + target.clientHeight >= target.scrollHeight - 48) setLimit((count) => Math.min(count + 80, playlists.length)); }}>{visible.map((playlist) => <div key={playlist.id} className="playlist-item"><button className={activeId === playlist.id && active ? 'playlist active' : 'playlist'} onClick={() => onSelect(playlist.id)}><span>{playlist.loaded ? <Check size={14} /> : <Library size={14} />}</span><em>{playlist.title}</em><small>{playlist.track_count}</small></button>{playlist.kind === 'collection' && <button className="playlist-delete" aria-label={`Remove ${playlist.title} from Library`} onClick={() => onDelete(playlist)}><Trash2 size={14} /></button>}</div>)}{visible.length < playlists.length && <p className="list-tail">{visible.length} / {playlists.length}</p>}</div>;
}

function TrackTable({ tracks, total, selected, onSelect, onMore, onQueue, busy }: { tracks: Track[]; total: number; selected?: string; onSelect: (t: Track) => void; onMore: () => void; onQueue: (id: string) => void; busy?: string }) {
  if (!tracks.length) return <div className="empty-state"><Music2 size={24} /><h2>No tracks</h2></div>;
  return <div className="track-table" onScroll={(event) => { const target = event.currentTarget; if (target.scrollTop + target.clientHeight >= target.scrollHeight - 110) onMore(); }}><div className="table-head"><span>#</span><span>Title</span><span>Album</span><span>Time</span><span className="downloaded-head">Downloaded</span><span /></div>{tracks.map((track) => <div role="button" tabIndex={0} className={selected === track.id ? 'track-row selected' : 'track-row'} key={track.id} onClick={() => onSelect(track)} onKeyDown={(e) => e.key === 'Enter' && onSelect(track)}><span className="track-no">{String(track.position).padStart(2, '0')}</span><span className="track-title"><span className="cover">{track.artwork_url ? <img src={track.artwork_url} alt="" /> : <Music2 size={17} />}</span><span><strong>{track.title}</strong><small>{track.artist}</small></span></span><span className="album">{track.album ?? '—'}</span><span>{track.duration ?? '—'}</span><Downloaded status={track.local_status} />{!['ready', 'unavailable'].includes(track.local_status) && <button className="row-action" aria-label={`Add ${track.title} to queue`} disabled={Boolean(busy)} onClick={(e) => { e.stopPropagation(); onQueue(track.video_id); }}><ListPlus size={16} /></button>}</div>)}{tracks.length < total && <div className="table-tail">{tracks.length} / {total}</div>}</div>;
}

function TrackInspector({ track, busy, onQueue, onDownload }: { track: Track; busy?: string; onQueue: () => void; onDownload: () => void }) {
  const canDownload = !['ready', 'unavailable'].includes(track.local_status);
  const status = track.local_status === 'ready' ? 'Downloaded' : track.local_status === 'unavailable' ? 'Unavailable' : 'Not downloaded';
  return <div className="track-inspector"><div className="large-cover">{track.artwork_url ? <img src={track.artwork_url} alt="" /> : <Music2 size={32} />}</div><h2>{track.title}</h2><p>{track.artist}</p><dl><div><dt>Status</dt><dd>{status}</dd></div></dl>{canDownload && <div className="track-actions"><button className="button ghost full" disabled={Boolean(busy)} onClick={onQueue}><ListPlus size={15} />Add to queue</button><button className="button primary full" disabled={Boolean(busy)} onClick={onDownload}><Download size={15} />Download</button></div>}</div>;
}

function JobRow({ job, busy, onCancel, onRetry }: { job: Job; busy?: string; onCancel: () => void; onRetry: () => void }) {
  const action = job.state === 'failed' ? <button aria-label="Retry" onClick={onRetry} disabled={Boolean(busy)}><RefreshCw size={14} /></button> : ['queued', 'running', 'retry'].includes(job.state) ? <button aria-label="Cancel" onClick={onCancel} disabled={Boolean(busy)}><X size={14} /></button> : null;
  return <div className="job"><span className={`job-state ${job.state}`} /> <div><strong>{job.title}</strong><small>{job.state === 'failed' ? job.error_message ?? 'Needs review' : `${job.state} · ${job.attempts} attempt${job.attempts === 1 ? '' : 's'}`}</small></div>{action}</div>;
}

function QueueTable({ jobs, busy, onCancel, onRetry }: { jobs: Job[]; busy?: string; onCancel: (id: string) => void; onRetry: (id: string) => void }) {
  if (!jobs.length) return <div className="empty-state"><ListPlus size={24} /><h2>Queue is empty</h2><p>Import a playlist or album to Unsorted, then add its missing tracks.</p></div>;
  return <div className="track-table queue-table"><div className="table-head"><span>Status</span><span>Track</span><span>Artist</span><span>Attempts</span><span>Error</span><span /></div>{jobs.map((job) => <div className="track-row queue-row" key={job.id}><span className={`queue-state ${job.state}`}><i />{job.state}</span><strong>{job.title}</strong><span className="queue-artist">{job.artist}</span><span>{job.attempts}</span><span className="queue-error">{job.state === 'failed' ? job.error_message ?? 'Needs review' : '—'}</span>{job.state === 'failed' ? <button className="row-action" aria-label={`Retry ${job.title}`} disabled={Boolean(busy)} onClick={() => onRetry(job.id)}><RefreshCw size={16} /></button> : <button className="row-action" aria-label={`Cancel ${job.title}`} disabled={Boolean(busy)} onClick={() => onCancel(job.id)}><X size={16} /></button>}</div>)}</div>;
}

function SettingsPanel({ health, importUrl, setImportUrl, profileUrl, setProfileUrl, busy, onProfile, onImport, onRepair, onBootstrap, onReset }: { health: Dashboard['health']; importUrl: string; setImportUrl: (s: string) => void; profileUrl: string; setProfileUrl: (s: string) => void; busy?: string; onProfile: () => void; onImport: () => void; onRepair: () => void; onBootstrap: () => void; onReset: () => void }) {
  const missingManagedTools = ['yt_dlp', 'node'].some((name) => !health.dependencies[name]?.available);
  return <div className="settings-panel"><section><h2>Profile URL</h2><div className="import-row"><input value={profileUrl} onChange={(e) => setProfileUrl(e.target.value)} placeholder="Profile URL" /><button className="button primary" disabled={!profileUrl || Boolean(busy)} onClick={onProfile}>Sync</button></div></section><section><h2>Quick import</h2><p>Paste a public YouTube Music playlist or album. Tracks are saved to Unsorted and added to Queue.</p><div className="import-row"><input value={importUrl} onChange={(e) => setImportUrl(e.target.value)} placeholder="Public playlist or album URL" /><button className="button primary" disabled={!importUrl || Boolean(busy)} onClick={onImport}>Import & queue</button></div></section><section><h2>Library</h2><div className="settings-actions"><button className="button ghost" disabled={Boolean(busy)} onClick={onRepair}><RefreshCw size={15} />Repair metadata</button><button className="button danger" disabled={Boolean(busy)} onClick={onReset}><X size={15} />Reset local library</button></div></section><section className="health"><div><h2>Tools</h2>{missingManagedTools && <button className="button ghost" disabled={Boolean(busy)} onClick={onBootstrap}><RefreshCw size={15} />Set up tools</button>}</div>{Object.entries(health.dependencies).map(([name, value]) => <div className="health-row" key={name}><span>{name}</span><span className={value.available ? 'health-ok' : 'health-missing'}>{value.available ? 'Ready' : value.detail || 'Missing'}</span></div>)}</section></div>;
}

function DevicePanel({ mountPath, setMountPath, preview, busy, syncProgress, onPreview, onApply, onOpenLibrary, playlists, onLoad }: { mountPath: string; setMountPath: (s: string) => void; preview?: SyncPreview; busy?: string; syncProgress?: { state: string; completed: number; total: number; current?: string }; onPreview: () => void; onApply: () => void; onOpenLibrary: () => void; playlists: Playlist[]; onLoad: (id: string, loaded: boolean) => void }) {
  return <div className="device-panel"><section className="device-hero"><div className="device-icon"><HardDrive size={25} /></div><div><h2>Echo Nano</h2></div><button className="button ghost library-button" disabled={Boolean(busy)} onClick={onOpenLibrary}><FolderOpen size={15} />Open library</button></section><section className="mount-row"><label>Volume<input value={mountPath} onChange={(e) => setMountPath(e.target.value)} /></label><button className="button ghost" disabled={Boolean(busy)} onClick={onPreview}>{busy === 'preview' ? <LoaderCircle className="spin" size={15} /> : <RefreshCw size={15} />}Preview</button><button className="button primary" disabled={!preview || Boolean(busy)} onClick={onApply}>{busy === 'sync' ? <LoaderCircle className="spin" size={15} /> : <HardDrive size={15} />}Sync</button></section>{busy === 'sync' && <section className="sync-live"><div><LoaderCircle className="spin" size={17} /><strong>{syncProgress?.state === 'applying' ? 'Applying' : 'Preparing'}</strong><span>{syncProgress?.total ? `${syncProgress.completed} / ${syncProgress.total}` : 'Starting'}</span></div><div className="progress-track"><i style={{ width: `${syncProgress?.total ? (syncProgress.completed / syncProgress.total) * 100 : 5}%` }} /></div><small>{syncProgress?.current}</small></section>}<section><div className="section-heading"><h2>Library collections</h2><span className="cap">8,000 max</span></div><div className="loaded-list">{playlists.map((playlist) => <label className="loaded-row" key={playlist.id}><input type="checkbox" checked={playlist.loaded} onChange={(e) => onLoad(playlist.id, e.target.checked)} /><span><strong>{playlist.title}</strong><small>{playlist.track_count}</small></span><span>{playlist.loaded ? 'On' : 'Off'}</span></label>)}</div></section>{preview && <section className="preview"><div className="section-heading"><h2>Preview</h2><span className={preview.warnings.length ? 'warn-pill' : 'ok-pill'}>{preview.warnings.length ? `${preview.warnings.length} warnings` : 'Ready'}</span></div><div className="metrics"><div><strong>{preview.files_to_copy}</strong><span>add</span></div><div><strong>{preview.files_to_remove}</strong><span>remove</span></div><div><strong>{bytes(preview.projected_bytes)}</strong><span>size</span></div><div><strong>{preview.physical_files_after}</strong><span>files</span></div></div>{preview.warnings.map((warning) => <p className="warning" key={warning}><CircleAlert size={15} />{warning}</p>)}</section>}</div>;
}
