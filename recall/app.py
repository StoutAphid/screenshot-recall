import json
import logging
import os
import subprocess
import sys
import time
from contextlib import asynccontextmanager
from datetime import date, datetime, time as daytime, timedelta
from functools import partial
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from .engine import Engine
from .store import Store

ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseModel):
    folder: str


def public(row):
    return {k: v for k,v in row.items() if k not in {'hash', 'size', 'active'}} | {'tags': json.loads(row['tags']), 'boxes': json.loads(row['boxes'])}


def create_app(data_dir=None, start_engine=True):
    store = Store(Path(data_dir or ROOT / 'data'))
    engine = Engine(store)

    @asynccontextmanager
    async def lifespan(app):
        if start_engine:
            engine.start()
        yield
        engine.stop()

    app = FastAPI(title='Screenshot Recall', lifespan=lifespan)
    app.state.store, app.state.engine = store, engine

    @app.middleware('http')
    async def local_only(request: Request, call_next):
        # Block cross-origin writes and DNS rebinding to the local file service.
        from starlette.responses import JSONResponse
        if request.headers.get('host', '').split(':')[0] not in {'127.0.0.1','localhost','testserver'}:
            return JSONResponse({'detail': 'Local access only'}, status_code=403)
        origin = request.headers.get('origin')
        if origin and origin not in {'http://127.0.0.1:8765','http://localhost:8765','http://127.0.0.1:5173','http://localhost:5173'}:
            return JSONResponse({'detail': 'Origin not allowed'}, status_code=403)
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        return response

    @app.get('/api/status')
    def status():
        return {**engine.status(), 'application': 'screenshot-recall', 'server_pid': os.getpid(), 'environment': str(Path(sys.prefix).resolve())}

    @app.get('/api/settings')
    def settings():
        return store.settings()

    @app.put('/api/settings')
    def set_settings(value: Settings):
        folder = Path(value.folder).expanduser()
        if not folder.is_absolute() or not folder.is_dir():
            raise HTTPException(400, 'Choose an existing absolute folder path.')
        store.save_settings(folder=str(folder.resolve()))
        engine.wake.set()
        return store.settings()

    @app.post('/api/indexing/{action}')
    def indexing(action: str):
        if action in {'pause', 'resume'}:
            store.save_settings(paused=action=='pause')
        elif action == 'retry':
            with store.connect() as db:
                db.execute("UPDATE images SET ocr=CASE WHEN ocr='failed' THEN 'pending' ELSE ocr END,error='' WHERE active=1")
            engine.retry_after.clear()
        elif action != 'rescan':
            raise HTTPException(404)
        engine.wake.set()
        return {'ok': True}

    @app.get('/api/search')
    async def search(q: str='', start: date | None=None, end: date | None=None, offset: int=0, limit: int=60, state: str='all'):
        if len(q)>500 or offset<0 or not 1<=limit<=120 or state not in {'all','ready','pending'}:
            raise HTTPException(400,'Invalid query or pagination.')
        if start and end and start>end:
            raise HTTPException(400,'Start date must precede end date.')
        started = time.perf_counter()
        vector, warning = None, None
        if q.strip() and engine.models.get('embedding'):
            if q not in engine.ollama.query_cache:
                engine.search_priority_until = time.monotonic()+8
            try:
                # Do not let an indexing inference hold a search request indefinitely.
                if engine.ollama.inference_lock.locked() and q not in engine.ollama.query_cache:
                    warning = 'AI is indexing an image. Showing keyword results; try again shortly for semantic results.'
                else:
                    vector = (await run_in_threadpool(partial(engine.ollama.embed, [q], query=True)))[0]
            except Exception:
                warning = 'Semantic search is temporarily unavailable. Showing keyword results.'
        elif q.strip():
            warning = 'Embedding model unavailable. Showing keyword results.'
        low = datetime.combine(start,daytime.min).timestamp() if start else None
        high = datetime.combine(end+timedelta(days=1),daytime.min).timestamp() if end else None
        results,total = await run_in_threadpool(partial(store.search,q.strip(),vector,low,high,offset,limit,state))
        return {'items': [public(r) for r in results], 'total': total, 'mode': 'hybrid' if vector is not None else 'keyword', 'warning': warning, 'elapsed_ms': round((time.perf_counter()-started)*1000)}

    def get_image(image_id):
        rows = store.rows('SELECT * FROM images WHERE id=? AND active=1',(image_id,))
        if not rows:
            raise HTTPException(404,'Image not indexed.')
        row = rows[0]
        path = Path(row['path'])
        if path.parent.resolve()!=Path(store.settings()['folder']).resolve() or not path.is_file() or path.is_symlink():
            raise HTTPException(404,'Source image is unavailable.')
        return row,path

    @app.get('/api/images/{image_id}')
    def image_detail(image_id: int):
        row,_ = get_image(image_id)
        return public(row)

    @app.get('/api/images/{image_id}/thumbnail')
    def thumbnail(image_id: int):
        _,path = get_image(image_id)
        thumb = store.root / 'thumbs' / f'{image_id}.jpg'
        return FileResponse(thumb if thumb.is_file() else path)

    @app.get('/api/images/{image_id}/original')
    def original(image_id: int):
        _,path = get_image(image_id)
        return FileResponse(path)

    @app.post('/api/images/{image_id}/reveal')
    def reveal(image_id: int):
        _,path = get_image(image_id)
        if os.name != 'nt':
            raise HTTPException(400,'Explorer is available on Windows only.')
        subprocess.Popen(['explorer.exe', f'/select,{path}'])
        return {'ok': True}

    if (ROOT / 'dist').is_dir():
        app.mount('/', StaticFiles(directory=ROOT / 'dist',html=True),name='ui')
    else:
        @app.get('/')
        def missing_frontend():
            return {'message':'Run npm install and npm run build, then restart. For development: npm run dev.'}
    return app


logging.basicConfig(level=logging.INFO)
app = create_app()
