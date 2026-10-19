# Screenshot Recall

Local screenshot search for Windows. Find saved images by their text, subject, or visual description without uploading them to a cloud service.

Recall watches a folder, extracts text with OCR, generates descriptions with a local vision model, and combines keyword and semantic search. The browser interface includes thumbnails, full-size previews, date filters, and copyable extracted text.

## Features

- Automatic indexing of new screenshots, with a startup scan for files added while stopped.
- Keyword search over filenames, extracted text, and descriptions.
- Semantic search using locally generated embeddings.
- Image previews, OCR text copying, and Reveal in Explorer.
- Date filters and separate views for completed and pending analysis.
- Pause/resume, failed-file retries, and persistent indexing progress.
- Content-hash caching to reuse analysis for identical images.
- SQLite storage, with no database server or cloud API key required.

Supported formats: PNG, JPEG, WebP, and BMP. One folder is indexed at a time, without subfolders or symbolic links. Source images are never modified.

## Requirements

- Windows 10 or 11
- Python 3.11
- Node.js 22.12 or later
- [Ollama](https://ollama.com/download/windows), installed and running
- Sufficient disk space and memory for the selected local models

The default models are `gemma4:e2b` for descriptions and `embeddinggemma:300m` for semantic search. Inference speed depends on the hardware; a GPU is useful for the vision model. OCR and keyword search can run without Ollama.

## Setup

Open PowerShell:

```powershell
git clone https://github.com/StoutAphid/screenshot-recall.git
cd screenshot-recall
ollama pull gemma4:e2b
.\setup.ps1
.\start.ps1
```

Setup creates a Python virtual environment, installs dependencies, builds the frontend, prepares OCR weights, and downloads the embedding model. The vision model is downloaded separately using the command above. Internet access is needed for setup; normal processing stays local.

The app opens at **http://127.0.0.1:8765**. The default folder is `%USERPROFILE%\Pictures\Screenshots`; change it in Settings if needed.

To omit the embedding download, run `.\setup.ps1 -SkipEmbeddingModel`. Install it later with `ollama pull embeddinggemma:300m`; the running indexer detects it automatically.

## Usage

Take screenshots normally with Win+Shift+S. Recall indexes the saved images while running. Files added while stopped are discovered on the next launch.

Try queries such as `ModuleNotFoundError`, `database validation rules`, or `architecture diagram`. Click a result to see the original, its description, and extracted text. Use **Copy** to copy OCR text or **Reveal in Explorer** to locate the file. Ctrl+K focuses search; Escape closes a preview or Settings.

**File date** uses filesystem modification time, not necessarily capture time. The end date includes the full selected day. **AI ready** means embeddings have finished; keyword search becomes available as soon as OCR finishes. The initial import runs in the background, and search works while it is processing.

### Start and stop

```powershell
.\start.ps1              # Start and open the browser
.\start.ps1 -NoBrowser   # Start without opening a browser
.\stop.ps1               # Stop from another PowerShell window
```

Keep the launcher window open. Ctrl+C in that window also stops the server. Closing the browser does not stop indexing. Pause in the interface stops new indexing work after the current operation finishes, while keeping search available.

Ollama runs separately. To unload its models after stopping Recall:

```powershell
ollama stop gemma4:e2b
ollama stop embeddinggemma:300m
```

These commands release model allocations without deleting the downloads. Recall does not register a Windows service or start automatically at sign-in.

## Architecture

```text
Screenshots folder
       |
Watchdog + periodic scan
       |
Background worker
       +-- RapidOCR ---------> extracted text and bounding boxes
       +-- Gemma / Ollama ---> descriptions and tags
       +-- EmbeddingGemma --> chunk embeddings
       |
SQLite + thumbnail cache
       |
FastAPI <----> React / TypeScript browser interface
       |
FTS5 keyword ranking + cosine similarity -> reciprocal rank fusion
```

Files must have a stable size and timestamp before processing. The worker runs OCR in small batches and serializes model requests to limit resource contention. OCR, description, and embedding states are stored independently, so unfinished work resumes after a restart. Modified files invalidate previous analysis; missing files are excluded from active search.

Long OCR text is split into overlapping chunks. Embeddings are stored as normalized float32 vectors in SQLite and compared using NumPy. Search combines FTS5 keyword ranks with semantic similarity ranks using reciprocal rank fusion, returning one result per image.

If image inference is busy, search may initially return keyword results and retry for semantic results. If Ollama is unavailable, OCR and keyword search continue.

### Project structure

```text
recall/
  app.py         FastAPI routes and local-access checks
  engine.py      Folder watching, OCR, and Ollama processing
  store.py       SQLite persistence and search ranking
src/             React interface and styles
scripts/         Benchmark and retrieval evaluation tools
tests/           Storage, API, and indexing tests
setup.ps1        Dependency and model setup
start.ps1        Launcher
stop.ps1         Server shutdown
```

### Storage and privacy

| Location | Contents |
| --- | --- |
| `data/recall.sqlite3` | Metadata, OCR, descriptions, vectors, settings, and indexing states |
| `data/thumbs/` | Cached JPEG thumbnails |
| `data/server*.log` | Launcher output and errors |

SQLite tables are `images`, `search` (FTS5), `vectors`, and `settings`. WAL mode may create `-wal` and `-shm` sidecars. Stop the app before copying the complete data directory as a backup. Runtime data is excluded from version control.

The server binds to loopback and checks Host and Origin headers. It is intended for a trusted local user, not public hosting. Screenshot text is treated as untrusted content in model prompts. There are no analytics or cloud processing calls.

## Development

After setup, start FastAPI:

```powershell
.\.venv\Scripts\python.exe -m uvicorn recall.app:app --host 127.0.0.1 --port 8765
```

In a second terminal, run `npm run dev`. Vite proxies `/api` to the backend. Production serves the built frontend from FastAPI.

```powershell
npm test
npm run build
```

Tests use temporary directories and mocked model calls. They cover incomplete writes, changes and deletion, duplicate reuse, recovery, ranking, filtering, API access checks, and live filesystem events.

### Evaluation

Sample a folder without starting a full import:

```powershell
.\.venv\Scripts\python.exe scripts\benchmark.py --folder "$env:USERPROFILE\Pictures\Screenshots" --count 30 --spread --output data/benchmark
```

Create a local label file using IDs from that benchmark database:

```json
[{"query": "database validation rules", "expected_ids": [3], "kind": "text"}]
```

```powershell
.\.venv\Scripts\python.exe scripts\evaluate.py --data data/benchmark --labels data/labels.json
```

The evaluator reports hit@5 and retrieval latency after query-embedding warmup. Use `--keyword-only` to test keyword retrieval separately. Retrieval timing excludes model loading and query embedding; the search API reports its full request time. Keep source images, labels, databases, and benchmark outputs out of version control.

## Limitations

- Visual search depends on model-generated descriptions. Small details may be missed, and descriptions can be inaccurate.
- OCR can misread small text, unusual fonts, and dense code screenshots.
- Cold model loads and initial indexing can be slow on limited hardware.
- This version supports English OCR and one watched folder.
- Recall does not capture screens, organize files, or provide a chat interface.

## Removing data

Move or delete an original through Explorer to remove it from active search. Cached text and thumbnails remain for reuse; deleting a source file is not a cache purge.

To clear the index and settings, stop Recall and remove `data/`. Original screenshots remain in their separate folder. The next launch rebuilds the index. Rename `data/` to keep a reversible backup instead.

To uninstall, stop Recall and remove its project directory. Ollama models are separate; optionally remove the added embedding model with `ollama rm embeddinggemma:300m`.
