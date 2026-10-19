"""Reuse validated OCR/description caches in the main library without re-running models."""
import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from recall.store import Store

parser=argparse.ArgumentParser()
parser.add_argument('--source',default='data/benchmark-final')
parser.add_argument('--target',default='data')
args=parser.parse_args()
source,target=Store(Path(args.source)),Store(Path(args.target))
fields=['hash','width','height','text','boxes','description','tags','ocr','vision','embedding','error']
copied=0
for row in source.rows("SELECT * FROM images WHERE ocr='done'"):
    matches=target.rows('SELECT * FROM images WHERE path=? AND mtime=? AND size=?',(row['path'],row['mtime'],row['size']))
    if not matches:continue
    image_id=matches[0]['id']
    values={k:row[k] for k in fields}
    values['embedding']='pending'
    target.update(image_id,**values)
    thumb=source.root/'thumbs'/f"{row['id']}.jpg"
    if thumb.is_file():shutil.copyfile(thumb,target.root/'thumbs'/f'{image_id}.jpg')
    vectors=source.rows('SELECT vector FROM vectors WHERE image_id=? ORDER BY chunk',(row['id'],))
    if vectors:
        import numpy as np
        target.save_vectors(image_id,[np.frombuffer(v['vector'],dtype=np.float32) for v in vectors])
    copied+=1
print(f'Reused {copied} cached images.')
