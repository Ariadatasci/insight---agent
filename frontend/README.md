# Insight frontend

A lightweight React and Vite interface for the existing FastAPI agent. The backend
remains responsible for all retrieval, SQL, and model calls.

From `insight-agent`, start the backend in one terminal:

```powershell
uvicorn backend.main:app --reload
```

With Node.js 22 or newer installed, open another terminal:

```powershell
cd frontend
Copy-Item .env.example .env
npm.cmd ci
npm.cmd run dev
```

Open http://127.0.0.1:5173. The development server uses port 5173 to match the
existing backend CORS configuration. `VITE_API_URL` sets the backend base URL;
it defaults to `http://localhost:8000` for local development. Restart Vite after
changing `.env`. Vite environment variables are public: do not put secrets in them.

If Node is not installed globally, the portable runtime used during development
is available in the ignored project cache. From `frontend`, enable it for the
current PowerShell terminal before running the npm commands above:

```powershell
$nodeDirectory = Get-ChildItem ../.cache -Directory -Filter 'node-*-win-x64' | Select-Object -First 1
$env:Path = $nodeDirectory.FullName + ';' + $env:Path
```

Build the frontend with `npm run build`. Output goes to `dist/`.

Enter submits a question; Shift + Enter adds a line. Example questions submit
immediately. While a request is pending, input and question buttons are disabled.
The answer shows SQL only when returned, and sources only when present. Sidebar
record counts describe the supplied demo dataset; online status comes from
`GET /health`. The page uses plain CSS and system font fallbacks if the optional
Google font is unavailable.
