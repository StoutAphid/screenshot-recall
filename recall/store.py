import json
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

import numpy as np


class Store:
    def __init__(self, root: Path):
        self.root = root
        root.mkdir(parents=True, exist_ok=True)
        (root / 'thumbs').mkdir(exist_ok=True)
        self.lock = threading.RLock()
        with self.connect() as db:
            db.executescript('''
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS images (
                id INTEGER PRIMARY KEY, path TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
                mtime REAL NOT NULL, size INTEGER NOT NULL, hash TEXT,
                width INTEGER, height INTEGER, text TEXT DEFAULT '', boxes TEXT DEFAULT '[]',
                description TEXT DEFAULT '', tags TEXT DEFAULT '[]',
                ocr TEXT DEFAULT 'pending', vision TEXT DEFAULT 'pending', embedding TEXT DEFAULT 'pending',
                error TEXT DEFAULT '', active INTEGER DEFAULT 1);
            CREATE INDEX IF NOT EXISTS hash_idx ON images(hash);
            CREATE VIRTUAL TABLE IF NOT EXISTS search USING fts5(name, text, description, content='images', content_rowid='id');
            CREATE TRIGGER IF NOT EXISTS images_ai AFTER INSERT ON images BEGIN
                INSERT INTO search(rowid,name,text,description) VALUES(new.id,new.name,new.text,new.description); END;
            CREATE TRIGGER IF NOT EXISTS images_ad AFTER DELETE ON images BEGIN
                INSERT INTO search(search,rowid,name,text,description) VALUES('delete',old.id,old.name,old.text,old.description); END;
            DROP TRIGGER IF EXISTS images_au;
            CREATE TRIGGER images_au AFTER UPDATE OF name,text,description ON images BEGIN
                INSERT INTO search(search,rowid,name,text,description) VALUES('delete',old.id,old.name,old.text,old.description);
                INSERT INTO search(rowid,name,text,description) VALUES(new.id,new.name,new.text,new.description); END;
            CREATE TABLE IF NOT EXISTS vectors(image_id INTEGER, chunk INTEGER, vector BLOB, PRIMARY KEY(image_id,chunk));
            CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
            ''')

    @contextmanager
    def connect(self):
        with self.lock:
            db = sqlite3.connect(self.root / 'recall.sqlite3', timeout=30)
            db.row_factory = sqlite3.Row
            try:
                yield db
                db.commit()
            except Exception:
                db.rollback()
                raise
            finally:
                db.close()

    def rows(self, sql, args=()):
        with self.connect() as db:
            return [dict(r) for r in db.execute(sql, args).fetchall()]

    def update(self, image_id, **fields):
        with self.connect() as db:
            db.execute('UPDATE images SET ' + ','.join(f'{k}=?' for k in fields) + ' WHERE id=?', (*fields.values(), image_id))

    def settings(self):
        return {r['key']: json.loads(r['value']) for r in self.rows('SELECT * FROM settings')}

    def save_settings(self, **values):
        with self.connect() as db:
            db.executemany('INSERT OR REPLACE INTO settings VALUES(?,?)', [(k, json.dumps(v)) for k, v in values.items()])

    def save_vectors(self, image_id, vectors):
        with self.connect() as db:
            db.execute('DELETE FROM vectors WHERE image_id=?', (image_id,))
            for i, vector in enumerate(vectors):
                v = np.array(vector, dtype=np.float32, copy=True)
                v /= max(float(np.linalg.norm(v)), 1e-12)
                db.execute('INSERT INTO vectors VALUES(?,?,?)', (image_id, i, v.tobytes()))
            db.execute("UPDATE images SET embedding='done',error='' WHERE id=?", (image_id,))

    def search(self, query='', vector=None, start=None, end=None, offset=0, limit=60, state='all'):
        conditions, args = ['active=1'], []
        if state == 'ready':
            conditions.append("embedding='done'")
        elif state == 'pending':
            conditions.append("(ocr!='done' OR vision!='done' OR embedding!='done')")
        if start is not None:
            conditions.append('mtime>=?'); args.append(start)
        if end is not None:
            conditions.append('mtime<?'); args.append(end)
        where = ' AND '.join(conditions)
        rows = self.rows('SELECT * FROM images WHERE ' + where + ' ORDER BY mtime DESC', args)
        if not query:
            return rows[offset:offset+limit], len(rows)
        allowed = {r['id'] for r in rows}
        import re
        tokens = re.findall(r'\w+', query, flags=re.UNICODE)
        lexical = []
        if tokens:
            expression = ' OR '.join('"' + t + '"' for t in tokens)
            lexical = [r['rowid'] for r in self.rows('SELECT rowid FROM search WHERE search MATCH ? ORDER BY rank', (expression,)) if r['rowid'] in allowed]
        semantic = []
        if vector is not None:
            q = np.asarray(vector, dtype=np.float32)
            q /= max(float(np.linalg.norm(q)), 1e-12)
            scores = {}
            for r in self.rows('SELECT * FROM vectors'):
                if r['image_id'] not in allowed:
                    continue
                v = np.frombuffer(r['vector'], dtype=np.float32)
                if len(v) == len(q):
                    score = float(v @ q)
                    scores[r['image_id']] = max(score, scores.get(r['image_id'], -1))
            semantic = sorted(scores, key=scores.get, reverse=True)[:200]
        fused = {}
        for ranking in [lexical, semantic]:
            for rank, image_id in enumerate(ranking):
                fused[image_id] = fused.get(image_id, 0) + 1 / (60 + rank + 1)
        ranked = sorted((r for r in rows if r['id'] in fused), key=lambda r: fused[r['id']], reverse=True)
        return ranked[offset:offset+limit], len(ranked)
