import React, { useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { Search, SlidersHorizontal, ScanLine, ArrowUpRight, X, Copy, FolderOpen, Pause, Play, RefreshCw, Check, Image as ImageIcon, ChevronRight, HardDrive, Sparkles, LoaderCircle } from 'lucide-react';
import './style.css';
type Shot = {
    id: number;
    name: string;
    path: string;
    mtime: number;
    width: number;
    height: number;
    text: string;
    description: string;
    tags: string[];
    ocr: string;
    vision: string;
    embedding: string;
    error: string;
};
type Status = {
    total: number;
    ocr: number;
    described: number;
    embedded: number;
    failed: number;
    paused: boolean;
    current: string;
    folder: string;
    error: string;
    per_minute: number;
    models: {
        online: boolean;
        vision: boolean;
        embedding: boolean;
    };
};
type Results = {
    items: Shot[];
    total: number;
    elapsed_ms: number;
    mode: string;
    warning: string | null;
};
async function api<T>(path: string, init?: RequestInit): Promise<T> {
    const r = await fetch('/api' + path, { ...init, headers: { 'Content-Type': 'application/json', ...init?.headers } });
    if (!r.ok) {
        const b = await r.json().catch(() => ({ detail: r.statusText }));
        throw Error(b.detail || 'Request failed');
    }
    return r.json();
}
const stamp = (n: number) => new Date(n * 1000).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
function App() {
    const [status, setStatus] = useState<Status | null>(null), [result, setResult] = useState<Results | null>(null);
    const [query, setQuery] = useState(''), [submitted, setSubmitted] = useState(''), [start, setStart] = useState(''), [end, setEnd] = useState('');
    const [selected, setSelected] = useState<Shot | null>(null), [settings, setSettings] = useState(false), [folder, setFolder] = useState('');
    const [busy, setBusy] = useState(false), [error, setError] = useState(''), [copied, setCopied] = useState(false);
    const [tab, setTab] = useState('all');
    const request = useRef(0);
    const searchRef = useRef<HTMLInputElement>(null);
    async function refreshStatus() { try {
        const s = await api<Status>('/status');
        setStatus(s);
    }
    catch (e) {
        setError(String(e));
    } }
    async function search(q = submitted, offset = 0) {
        const id = ++request.current;
        setBusy(true);
        setError('');
        try {
            const p = new URLSearchParams({ q, offset: String(offset), state: tab });
            if (start)
                p.set('start', start);
            if (end)
                p.set('end', end);
            const r = await api<Results>('/search?' + p);
            if (id === request.current)
                setResult(prev => offset && prev ? { ...r, items: [...prev.items, ...r.items] } : r);
        }
        catch (e) {
            if (id === request.current)
                setError(String(e));
        }
        finally {
            if (id === request.current)
                setBusy(false);
        }
    }
    useEffect(() => { refreshStatus(); const timer = setInterval(refreshStatus, 3000); return () => clearInterval(timer); }, []);
    useEffect(() => { search(); }, [submitted, start, end, tab]);
    useEffect(() => { if (!submitted && !selected && !busy)
        search(); }, [status?.ocr]);
    useEffect(() => { if (result?.warning && submitted && status?.models.embedding) {
        const t = setTimeout(() => search(), 3000);
        return () => clearTimeout(t);
    } }, [result, submitted, status?.models.embedding]);
    useEffect(() => { if (!selected && !settings)
        return; const old = document.activeElement as HTMLElement; const modal = document.querySelector<HTMLElement>('.overlay:last-child .modal'); modal?.querySelector<HTMLElement>('button,input')?.focus(); function trap(e: KeyboardEvent) { if (e.key !== 'Tab' || !modal)
        return; const nodes = Array.from(modal.querySelectorAll<HTMLElement>('button:not(:disabled),input,a[href]')); const first = nodes[0], last = nodes[nodes.length - 1]; if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last?.focus();
    }
    else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first?.focus();
    } } document.addEventListener('keydown', trap); return () => { document.removeEventListener('keydown', trap); old?.focus(); }; }, [!!selected, settings]);
    useEffect(() => { function key(e: KeyboardEvent) { if (e.key === 'Escape') {
        setSelected(null);
        setSettings(false);
    } if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault();
        searchRef.current?.focus();
    } } document.addEventListener('keydown', key); return () => document.removeEventListener('keydown', key); }, []);
    async function action(name: string) { try {
        await api('/indexing/' + name, { method: 'POST' });
        refreshStatus();
    }
    catch (e) {
        setError(String(e));
    } }
    async function saveFolder() { try {
        await api('/settings', { method: 'PUT', body: JSON.stringify({ folder }) });
        setSettings(false);
        await refreshStatus();
        setTimeout(() => search(), 1500);
    }
    catch (e) {
        setError(String(e));
    } }
    async function openShot(shot: Shot) { setSelected(shot); setCopied(false); try {
        setSelected(await api<Shot>('/images/' + shot.id));
    }
    catch (e) {
        setError(String(e));
    } }
    const shown = result?.items || [];
    const remaining = status ? Math.max(0, status.total - status.embedded) : 0;
    return <div className="shell">
    <aside className="sidebar">
      <a className="brand" href="/" aria-label="Recall home"><span className="brand-icon"><ScanLine size={22}/></span>recall<span className="brand-dot">.</span></a>
      <div className="workspace-label">YOUR WORKSPACE</div>
      <button className="nav active" onClick={() => { setSubmitted(''); setQuery(''); setStart(''); setEnd(''); setTab('all'); }}><ImageIcon size={18}/>Screenshot library<span>{status?.total.toLocaleString() || '0'}</span></button>
      <div className="sidebar-note"><div className="small-orbit"><Sparkles size={20}/></div><strong>A little less searching.<br />A little more finding.</strong><p>Every screenshot has a story.<br />Find it with a few words.</p></div>
      <div className="sidebar-bottom"><div className="local-indicator"><span />LOCAL & PRIVATE</div><p>Your memories stay on this device.</p><button className="nav settings-link" onClick={() => { setFolder(status?.folder || ''); setSettings(true); }}><SlidersHorizontal size={17}/>Settings<ChevronRight size={15}/></button></div>
    </aside>
    <main>
      <header><div className="breadcrumb">Workspace<ChevronRight size={13}/><span>Screenshot library</span></div><button className="icon-button" aria-label="Open settings" onClick={() => { setFolder(status?.folder || ''); setSettings(true); }}><SlidersHorizontal size={18}/></button></header>
      <section className="intro"><div className="eyebrow"><span />YOUR PERSONAL VISUAL MEMORY</div><h1>You’ve seen it before.<br /><span>Find it again.</span></h1><p>Search your screenshots by what they say. Or what you remember.</p></section>
      <form className="search-box" onSubmit={e => { e.preventDefault(); if (query === submitted)
        search(query);
    else
        setSubmitted(query); }}><Search size={22}/><input ref={searchRef} value={query} onChange={e => setQuery(e.target.value)} placeholder='Try “Python error” or “a diagram with three servers”' aria-label="Search screenshots"/><kbd>Ctrl K</kbd><button className="search-submit" disabled={busy} aria-label="Search">{busy ? <LoaderCircle className="spin" size={19}/> : <ArrowUpRight size={21}/>}</button></form>
      <div className="suggestions"><span>A little inspiration</span>{['Python error', 'Architecture diagram', 'Code snippet'].map(s => <button key={s} onClick={() => { setQuery(s); setSubmitted(s); }}>{s}<ArrowUpRight size={12}/></button>)}</div>
      <section className="index-banner"><div className={'index-icon ' + (status?.paused ? 'muted' : '')}><ScanLine size={23}/></div><div className="index-info"><strong>{status?.paused ? 'Indexing paused' : status?.current ? 'Making sense of your screenshots' : remaining ? 'Your library is taking shape' : 'Your library, remembered'}</strong><p>{status ? `${status.ocr.toLocaleString()} text indexed · ${status.described.toLocaleString()} described · ${status.embedded.toLocaleString()} searchable by meaning` : 'Connecting to your local library…'}</p><div className="progress"><i style={{ width: `${status?.total ? status.embedded / status.total * 100 : 0}%` }}/></div></div><div className="index-count"><span>{status?.total ? Math.round(status.embedded / status.total * 100) : 0}%</span><small>{remaining.toLocaleString()} remaining</small></div><button className="icon-button" title={status?.paused ? 'Resume indexing' : 'Pause indexing'} aria-label={status?.paused ? 'Resume indexing' : 'Pause indexing'} onClick={() => action(status?.paused ? 'resume' : 'pause')}>{status?.paused ? <Play size={17}/> : <Pause size={17}/>}</button></section>
      {error && <div className="alert" role="alert">{error}<button onClick={() => setError('')} aria-label="Dismiss error"><X size={15}/></button></div>}
      {result?.warning && submitted && <div className="notice">{result.warning}<button onClick={() => search()}>Try again</button></div>}
      <section className="library"><div className="library-heading"><div><h2>{submitted ? 'Search results' : 'Your screenshots'}<span>{result?.total.toLocaleString() || 0}</span></h2><p>{submitted ? `Matches for “${submitted}” · ${result?.mode === 'hybrid' ? 'Text + meaning' : 'Text search'} · ${result?.elapsed_ms || 0} ms` : 'The things you saved, ready to rediscover.'}</p></div><button className="subtle-button" onClick={() => { action('rescan'); search(); }}><RefreshCw size={14}/>Refresh</button></div>
      <div className="filters"><div className="tabs">{[['all', 'All screenshots'], ['ready', 'AI ready'], ['pending', 'Processing']].map(([v, l]) => <button key={v} className={tab === v ? 'selected' : ''} onClick={() => setTab(v)}>{l}</button>)}</div><div className="date-filter"><label>File date <input type="date" value={start} onChange={e => setStart(e.target.value)} aria-label="File date from"/></label><span>—</span><input type="date" value={end} onChange={e => setEnd(e.target.value)} aria-label="File date through"/>{(start || end) && <button className="clear-date" aria-label="Clear dates" onClick={() => { setStart(''); setEnd(''); }}><X size={13}/></button>}</div></div>
      <div className="grid">{shown.map(s => <button className="shot-card" key={s.id} onClick={() => openShot(s)}><div className="shot-image"><img loading="lazy" src={`/api/images/${s.id}/thumbnail?v=${s.mtime}`} alt={s.description || s.name}/><span className={'shot-badge ' + (s.embedding === 'done' ? 'ready' : '')}>{s.embedding === 'done' ? <><Sparkles size={10}/>AI ready</> : s.ocr === 'failed' ? 'Needs attention' : 'Processing'}</span><span className="image-open"><ArrowUpRight size={18}/></span></div><div className="shot-meta"><strong title={s.name}>{s.name}</strong><span>{stamp(s.mtime)}<i>·</i>{s.width ? `${s.width} × ${s.height}` : 'Awaiting scan'}</span>{submitted && <p>{s.text || s.description || 'Awaiting analysis'}</p>}</div></button>)}</div>
      {!shown.length && !busy && <div className="empty"><ScanLine size={35}/><h3>{submitted ? 'No screenshots found' : 'Your library starts here'}</h3><p>{submitted ? 'Try different words, clear the date filter, or wait for indexing.' : 'Images will appear as the folder scan completes. Check Settings for your folder and model status.'}</p></div>}
      {busy && !shown.length && <div className="empty"><LoaderCircle className="spin"/><p>Searching your visual memory…</p></div>}
      {result && result.items.length < result.total && <button className="load-more" disabled={busy} onClick={() => search(submitted, result.items.length)}>{busy ? 'Loading…' : 'Load more screenshots'}</button>}
      <footer><span><HardDrive size={13}/>Stored locally. Searchable by you.</span><span>{status?.models.online ? 'Ollama connected' : 'Ollama offline'}<i className={status?.models.online ? 'online' : 'offline'}/></span></footer></section>
    </main>
    {selected && <div className="overlay" onClick={() => setSelected(null)}><section className="preview modal" role="dialog" aria-modal="true" aria-label="Screenshot details" onClick={e => e.stopPropagation()}><button className="close icon-button" onClick={() => setSelected(null)} aria-label="Close preview"><X /></button><div className="preview-image"><img src={`/api/images/${selected.id}/original`} alt={selected.description || selected.name}/></div><div className="preview-info"><span className="eyebrow">SCREENSHOT DETAILS</span><h2>{selected.name}</h2><p className="meta">File date · {stamp(selected.mtime)} · {selected.width} × {selected.height}</p><button className="subtle-button" onClick={async () => { try {
        await api(`/images/${selected.id}/reveal`, { method: 'POST' });
    }
    catch (e) {
        setError(String(e));
    } }}><FolderOpen size={15}/>Reveal in Explorer</button><h3><Sparkles size={15}/>Visual description</h3><p>{selected.description || 'Description is waiting for local AI processing.'}</p><div className="tags">{selected.tags.map((t, i) => <span key={i}>{t}</span>)}</div><div className="ocr-heading"><h3>Extracted text</h3><button className="subtle-button" disabled={!selected.text} onClick={async () => { try {
        await navigator.clipboard.writeText(selected.text);
        setCopied(true);
    }
    catch (e) {
        setError(String(e));
    } }}>{copied ? <Check size={14}/> : <Copy size={14}/>} {copied ? 'Copied' : 'Copy'}</button></div><pre>{selected.text || 'No text extracted yet.'}</pre>{selected.error && <p className="error-text">{selected.error}</p>}</div></section></div>}
    {settings && <div className="overlay" onClick={() => setSettings(false)}><section className="settings modal" role="dialog" aria-modal="true" aria-label="Settings" onClick={e => e.stopPropagation()}><button className="close icon-button" onClick={() => setSettings(false)} aria-label="Close settings"><X /></button><span className="eyebrow">MAKE YOURSELF AT HOME</span><h2>Your local setup</h2><p>One folder. A private, searchable memory.</p><label className="setting-label">Screenshot folder<input value={folder} onChange={e => setFolder(e.target.value)}/></label><p className="hint">Indexes supported images directly in this folder. Original files stay untouched.</p><div className="model-row"><span>Image understanding<small>gemma4:e2b</small></span><b className={status?.models.vision ? 'ok' : 'not-ready'}>{status?.models.vision ? 'Ready' : 'Unavailable'}</b></div><div className="model-row"><span>Semantic search<small>embeddinggemma:300m</small></span><b className={status?.models.embedding ? 'ok' : 'not-ready'}>{status?.models.embedding ? 'Ready' : 'Unavailable'}</b></div>{!status?.models.embedding && <p className="hint">Setup command: <code>ollama pull embeddinggemma:300m</code></p>}<div className="model-row"><span>Indexing<small>{status?.current || `${status?.per_minute || 0} AI jobs/min this session`}</small></span><button className="subtle-button" onClick={() => action(status?.paused ? 'resume' : 'pause')}>{status?.paused ? 'Resume' : 'Pause'}</button></div><div className="model-row"><span>Processing errors<small>{status?.failed || 0} images need attention</small></span><button className="subtle-button" onClick={() => action('retry')}>Retry</button></div>{status?.error && <p className="error-text">{status.error}</p>}{error && <p className="error-text">{error}</p>}<div className="settings-actions"><button className="subtle-button" onClick={() => setSettings(false)}>Cancel</button><button className="primary-button" onClick={saveFolder}>Save settings<ArrowUpRight size={16}/></button></div></section></div>}
  </div>;
}
createRoot(document.getElementById('root')!).render(<React.StrictMode><App /></React.StrictMode>);
