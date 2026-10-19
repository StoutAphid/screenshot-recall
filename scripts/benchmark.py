"""Explicit opt-in benchmark. Source files are read only; output stays in data/benchmark."""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from recall.engine import Engine, EXTENSIONS
from recall.store import Store

parser=argparse.ArgumentParser()
parser.add_argument('--folder',required=True)
parser.add_argument('--count',type=int,default=30)
parser.add_argument('--output',default='data/benchmark')
parser.add_argument('--ocr-only',action='store_true')
parser.add_argument('--spread',action='store_true',help='Sample across the folder history rather than only recent files')
args=parser.parse_args()
folder=Path(args.folder).resolve()
store=Store(Path(args.output));store.save_settings(folder=str(folder),paused=True)
engine=Engine(store);engine.models=engine.ollama.readiness()
all_files=sorted((p for p in folder.iterdir() if p.suffix.lower() in EXTENSIONS and p.is_file()),key=lambda p:p.stat().st_mtime,reverse=True)
if args.spread and args.count>1 and len(all_files)>args.count:
    files=[all_files[round(i*(len(all_files)-1)/(args.count-1))] for i in range(args.count)]
else:
    files=all_files[:args.count]
measurements=[]
for path in files:
    stat=path.stat()
    with store.connect() as db:
        db.execute('INSERT OR IGNORE INTO images(path,name,mtime,size) VALUES(?,?,?,?)',(str(path),path.name,stat.st_mtime,stat.st_size))
    row=store.rows('SELECT * FROM images WHERE path=?',(str(path),))[0]
    result={'id':row['id'],'name':path.name}
    try:
        started=time.perf_counter();engine.process_ocr(row);result['ocr_seconds']=round(time.perf_counter()-started,3)
        if not args.ocr_only:
            row=store.rows('SELECT * FROM images WHERE id=?',(row['id'],))[0]
            started=time.perf_counter();engine.process_ai(row);result['ai_seconds']=round(time.perf_counter()-started,3)
        updated=store.rows('SELECT * FROM images WHERE id=?',(row['id'],))[0]
        result.update(description=updated['description'],text=updated['text'],vision=updated['vision'],embedding=updated['embedding'])
    except Exception as exc:result['error']=str(exc)
    measurements.append(result)
    (store.root/'results.json').write_text(json.dumps(measurements,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in {'text','description'}}),flush=True)
print(f'Results saved locally to {store.root / "results.json"}')
