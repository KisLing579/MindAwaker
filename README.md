# Mindawaker Studio

[中文说明](README_zh.md)

Mindawaker is a browser-based workspace for turning ideas and stories into editable visual narratives. It combines text generation, structured story planning, image generation, speech synthesis, and video composition, with a review workflow that lets you refine intermediate results before continuing.

The application consists of a FastAPI backend and a Next.js frontend. The separate SceneStudio service extends the workflow with LTX image-to-video generation from project assets.

## Features

- **Story planning:** extract characters and recurring items, divide a story into scenes, and generate shots with structured visual prompts.
- **Review before generation:** edit the story document, preview compiled segments, and run individual stages for items, scenes, shots, images, audio, clips, or final composition.
- **Chapter workflows:** append chapters in generation or review mode and load an existing chapter for continued editing.
- **Media creation:** generate text, images, and audio independently, or combine them in a video project. Image redraw and selection support iterative refinement.
- **Video composition:** build clips and assemble media with FFmpeg. Clip settings include static and Jimeng modes; availability depends on the configured services.
- **Project management:** create, save, load, rebuild, and revisit project assets. Background tasks expose status, cancellation, and WebSocket progress.
- **English and Chinese interfaces:** use the frontend language selection, including when opening SceneStudio.
- **SceneStudio handoff:** open the current project or chapter directly in the LTX key-scene workbench.

## Workflow and architecture

```text
Idea or story
  -> characters / items -> scenes -> shots
  -> review and edit -> image and audio assets
  -> clips -> FFmpeg composition -> video
                         |
Project or chapter ------+-> SceneStudio -> LTX scene clips -> selected montage
```

Story review uses project-scoped stage locks and revision checks to prevent conflicting edits. The automatic pipeline and individual stage actions share the project data, so intermediate results can be inspected and refined without recreating the entire project.

```text
Mindawaker/
  app/
    main.py                 FastAPI application and route registration
    configs/                Credentials, logging, and application configuration
    router/                 Media, project, task, settings, and story APIs
    service/                Pipelines, review, chapters, tasks, and composition
    model/                  Request and story schemas
    langchain_pipeline/     Text-generation chains
    image_engine/           Flux and Volcengine integrations
    tts_engine/             Speech integrations
    assets/                 Application assets and served files
  mindawaker-web/            Next.js 14 / React 18 / TypeScript frontend
  requirements.txt          Backend dependencies
  .env.example              Backend environment template
  start.py                  Backend launcher
```

## Getting started

Install Python compatible with `requirements.txt`, Node.js with npm, and FFmpeg/ffprobe. Use an isolated Python environment. External generation services require their own credentials; SceneStudio's local LTX generation additionally requires a separately configured model runtime and GPU.

Run backend commands from the Mindawaker directory:

```bash
python -m venv .venv
# Linux/macOS:
source .venv/bin/activate
# Windows PowerShell instead:
# .\.venv\Scripts\Activate.ps1

python -m pip install -r requirements.txt
```

Copy `.env.example` to `.env` and fill in only the services you use:

```bash
# Linux/macOS
cp .env.example .env
# Windows PowerShell
# Copy-Item .env.example .env

python start.py --host 127.0.0.1 --port 8000 --reload
```

The backend is available at `http://localhost:8000`; interactive API documentation is at `http://localhost:8000/docs`, and the health endpoint is `/health`. Omit `--reload` for a long-running session where file changes should not restart active work.

In another terminal:

```bash
cd mindawaker-web
npm install
npm run dev
```

Open `http://localhost:3000`. The frontend proxies `/api/*` to `http://127.0.0.1:8000/*` through `mindawaker-web/next.config.js`. Update that rewrite if the backend runs elsewhere.

## Credentials and settings

Credentials are read on the backend. Existing process environment variables take precedence over `.env`. Restart the backend after changing its environment. Do not prefix secret variables with `NEXT_PUBLIC_`.

| Service | Backend environment variables |
| --- | --- |
| DeepSeek text | `DEEPSEEK_API_KEY` |
| OpenAI GPT text | `OPENAI_API_KEY` |
| Anthropic Claude text | `ANTHROPIC_API_KEY` |
| Google Gemini text | `GOOGLE_API_KEY` |
| Azure speech | `AZURE_SPEECH_KEY`, `AZURE_SPEECH_REGION` |
| Flux images | `FLUX_API_KEY` |
| Volcengine / Jimeng images | `VOLC_ACCESS_KEY`, `VOLC_SECRET_KEY`; `VOLC_REQ_KEY` defaults to `jimeng_t2i_v40` |
| Legacy image credential fallback | `IMAGE_MODEL_PASSWORD` |

For Volcengine, separate access and secret keys are preferred. The legacy fallback accepts `AccessKey**SecretKey`. Flux prefers `FLUX_API_KEY` and falls back to `IMAGE_MODEL_PASSWORD`. Model keys supplied by old browser requests or saved projects are ignored, and legacy credential fields are cleared when projects are saved again.

`CORS_ORIGINS` controls allowed backend origins; the current default is `http://localhost:3000,http://localhost:5173`. Logging configuration is in `app/configs/logging_config.py`. Configure the backend environment and frontend proxy together when changing hosts or ports.

## Working with SceneStudio

Start SceneStudio separately, then use **LTX-Scene-Studio** in a loaded project or chapter. Mindawaker obtains the active project directory from `/story/{project_id}/scene-studio` and opens:

```text
http://<frontend-host>:7200/?project_path=<URL-encoded-absolute-directory>&locale=en
```

The selected UI language is passed as `locale=en` or `locale=zh`. To use a different address, set `NEXT_PUBLIC_SCENE_STUDIO_URL` in the frontend environment and restart the development server or rebuild the frontend.

Both backends must be able to access the same project directory. The link passes a filesystem path; it does not upload or copy media. SceneStudio uses the project's `meta.json`, images, and story artifacts to create key-scene clips and a final montage. See the SceneStudio README for model setup and output locations.

## API overview

Paths below are backend paths; browser requests normally reach them through the frontend's `/api` proxy.

| Endpoint | Purpose |
| --- | --- |
| `/text`, `/image`, `/audio` | Media-generation route groups; see `/docs` for request schemas |
| `POST /video/compose` | Start a composition task |
| `GET /video/task/{task_id}` | Read task status |
| `POST /video/cancel/{task_id}` | Request task cancellation |
| `WS /video/ws/{task_id}` | Receive live progress |
| `POST /project/create`, `/project/save`, `/project/load` | Create, save, or load a project |
| `GET /project/list` | List projects |
| `POST /story/start` | Create a story-review project |
| `GET /story/{project_id}`, `PUT /story/{project_id}` | Read or revise a story document |
| `POST /story/{project_id}/stage` | Execute a selected stage |
| `POST /story/{project_id}/preview` | Preview compiled segments |
| `/story/{project_id}/chapters` | List or append chapters with GET or POST |
| `GET /story/{project_id}/scene-studio` | Resolve the current SceneStudio project path |

## Development and operational notes

```bash
cd mindawaker-web
npm run lint
npm run build
```

Provider errors should be checked in the task status and backend logs. A missing credential message names the required backend variable. If browser requests fail before a task starts, check the API proxy, backend port, and CORS configuration.

Structured prompts help carry character and scene information across shots, but visual consistency still depends on model output and review. Media generation requires the selected external services to be reachable. The retired video-retrieval and standalone 3D GUIDED modules are not part of the current application.
#   M i n d A w a k e r  
 #   M i n d A w a k e r  
 