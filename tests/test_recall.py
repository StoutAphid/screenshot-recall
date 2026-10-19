import json
import os
import time
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from recall.app import create_app
from recall.engine import Engine, chunks
from recall.store import Store


@pytest.fixture
def setup(tmp_path):
    folder = tmp_path / 'shots'; folder.mkdir()
    store = Store(tmp_path / 'data')
    store.save_settings(folder=str(folder),paused=False)
    engine = Engine(store)
    return folder,store,engine


def image(folder,name='shot.png',color='white'):
    path=folder/name
    Image.new('RGB',(120,80),color).save(path)
    return path


def settled(engine):
    engine.scan()
    engine.stable={k:(v[0],v[1]-2) for k,v in engine.stable.items()}
    engine.scan()


def test_stability_changes_and_deletion(setup):
    folder,store,engine=setup
    path=image(folder)
    engine.scan()
    assert store.rows('SELECT * FROM images')==[]
    settled(engine)
    row=store.rows('SELECT * FROM images')[0]
    engine.extract=lambda image:('ModuleNotFoundError: pandas', [[[0,0],[1,0],[1,1],[0,1]]])
    engine.process_ocr(row)
    assert store.search('ModuleNotFoundError')[1]==1
    settled(engine)
    assert store.rows('SELECT ocr FROM images')[0]['ocr']=='done'
    image(folder,color='blue')
    os.utime(path,(time.time()+2,time.time()+2))
    settled(engine)
    assert store.rows('SELECT ocr FROM images')[0]['ocr']=='pending'
    assert store.search('ModuleNotFoundError')[1]==0
    path.unlink();engine.scan()
    assert store.search()[1]==0


def test_duplicate_reuse_and_resume(setup):
    folder,store,engine=setup
    image(folder,'a.png');image(folder,'b.png')
    settled(engine)
    calls=[]
    engine.extract=lambda image:(calls.append(1) or 'Error 403',[])
    for row in store.rows('SELECT * FROM images'):
        engine.process_ocr(row)
    assert len(calls)==1
    restarted=Engine(Store(store.root))
    settled(restarted)
    assert len(store.rows("SELECT * FROM images WHERE ocr='done' AND vision='pending'"))==2


def test_hybrid_chunks_and_date(setup):
    folder,store,engine=setup
    image(folder,'one.png');image(folder,'two.png',color='red')
    settled(engine)
    rows=store.rows('SELECT * FROM images ORDER BY id')
    store.update(rows[0]['id'],text='Python import error',mtime=100)
    store.update(rows[1]['id'],description='Red sneaker on white background',mtime=200)
    readonly = np.frombuffer(np.array([1,0],dtype=np.float32).tobytes(),dtype=np.float32)
    store.save_vectors(rows[0]['id'],[readonly,[.8,.2]])
    store.save_vectors(rows[1]['id'],[[0,1]])
    result,total=store.search('scarlet shoes',[0,1])
    assert result[0]['id']==rows[1]['id']
    assert total==2 # chunks never duplicate results
    assert store.search('Python')[0][0]['id']==rows[0]['id']
    assert store.search(start=150,end=250)[1]==1
    assert chunks('a'*4000)[-1]
    assert 'z' in chunks('a'*4000+'z')[-1]
    # Punctuation cannot escape the FTS expression.
    assert store.search('" OR * : -')[1]==0


def test_api_offline_and_access(setup,monkeypatch):
    folder,store,engine=setup
    image(folder)
    settled(engine)
    row=store.rows('SELECT * FROM images')[0]
    store.update(row['id'],text='ModuleNotFoundError')
    app=create_app(store.root,start_engine=False)
    with TestClient(app) as client:
        r=client.get('/api/search?q=ModuleNotFoundError').json()
        assert r['total']==1 and r['mode']=='keyword' and r['warning']
        assert client.get('/api/images/999/original').status_code==404
        assert client.get('/api/images/1/original').status_code==200
        assert client.get('/api/search?start=2026-10-20&end=2026-10-19').status_code==400
        assert client.post('/api/indexing/pause').json()['ok']
        assert client.get('/api/status').json()['paused']
        assert client.put('/api/settings',json={'folder':'relative'}).status_code==400
        assert client.post('/api/indexing/resume',headers={'Origin':'https://evil.example'}).status_code==403
        assert client.get('/api/status',headers={'Host':'evil.example'}).status_code==403
        assert client.post('/api/indexing/retry').status_code==200
        import recall.app as module
        launched=[]
        monkeypatch.setattr(module.os,'name','nt')
        monkeypatch.setattr(module.subprocess,'Popen',lambda args:launched.append(args))
        assert client.post('/api/images/1/reveal').status_code==200
        assert launched[0][0]=='explorer.exe' and launched[0][1].startswith('/select,')
        assert client.get('/api/search?state=ready').json()['total']==0
        other=folder.parent/'other';other.mkdir()
        assert client.put('/api/settings',json={'folder':str(other)}).status_code==200
        assert client.get('/api/images/1/original').status_code==404


def test_partial_ai_recovery(setup):
    folder,store,engine=setup
    image(folder);settled(engine)
    row=store.rows('SELECT * FROM images')[0]
    engine.extract=lambda image:('hello',[])
    engine.process_ocr(row)
    class Fake:
        def describe(self,image,context=''):return 'A diagram',['diagram']
        def embed(self,texts):raise RuntimeError('offline')
    engine.ollama=Fake();engine.models={'vision':True,'embedding':True}
    row=store.rows('SELECT * FROM images')[0]
    with pytest.raises(RuntimeError):engine.process_ai(row)
    row=store.rows('SELECT * FROM images')[0]
    assert row['vision']=='done' and row['embedding']=='pending'
    engine.ollama.describe=lambda image,context='':pytest.fail('Description must be reused')
    engine.ollama.embed=lambda texts:[[1,0] for t in texts]
    engine.process_ai(row)
    assert store.rows('SELECT embedding FROM images')[0]['embedding']=='done'


def test_corrupt_file_isolated(setup):
    folder,store,engine=setup
    (folder/'broken.png').write_bytes(b'not an image')
    settled(engine)
    with pytest.raises(Exception):engine.process_ocr(store.rows('SELECT * FROM images')[0])
    assert store.search()[1]==1
