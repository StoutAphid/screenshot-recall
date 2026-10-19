import time

from PIL import Image

from recall.engine import Engine
from recall.store import Store


class Offline:
    def readiness(self):
        return {'online':False,'vision':False,'embedding':False}


def until(predicate, timeout=15):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        if predicate():return
        time.sleep(.1)
    raise AssertionError('Worker did not reach expected state in time')


def test_live_watch_pause_retry_and_restart(tmp_path):
    folder=tmp_path/'shots';folder.mkdir()
    store=Store(tmp_path/'db');store.save_settings(folder=str(folder),paused=True)
    engine=Engine(store,Offline())
    engine.extract=lambda image:('watched screenshot',[])
    engine.start()
    try:
        Image.new('RGB',(20,20),'red').save(folder/'new.png')
        until(lambda:len(store.rows('SELECT * FROM images'))==1)
        assert store.rows('SELECT ocr FROM images')[0]['ocr']=='pending'
        store.save_settings(paused=False);engine.wake.set()
        until(lambda:store.search('watched')[1]==1)
        (folder/'bad.png').write_bytes(b'broken')
        until(lambda:len(store.rows("SELECT * FROM images WHERE ocr='failed'"))==1)
        Image.new('RGB',(20,20),'blue').save(folder/'bad.png')
        until(lambda:len(store.rows("SELECT * FROM images WHERE ocr='done'"))==2)
    finally:
        engine.stop()
    restarted=Engine(Store(store.root),Offline())
    restarted.extract=lambda image:(_ for _ in ()).throw(AssertionError('Unchanged OCR must not rerun'))
    restarted.start()
    try:
        time.sleep(2)
        assert len(store.rows("SELECT * FROM images WHERE ocr='done'"))==2
        assert not store.rows("SELECT * FROM images WHERE ocr='failed'")
    finally:restarted.stop()
