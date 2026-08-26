# Hand Cricket

Real-time multiplayer hand cricket game built with FastAPI, React, and WebSockets.

Two teams take turns batting and bowling. Players draw numbers (0–10) simultaneously — matching numbers means OUT. All game logic is enforced server-side.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.12+, FastAPI, uvicorn, Pydantic v2 |
| Frontend | React 18, TypeScript 5, Vite 5, Zustand 4 |
| Styling | Tailwind CSS 3.4 |
| Realtime | Native WebSocket (no Socket.IO) |
| Database | SQLite via aiosqlite + SQLAlchemy |
| Persistence | Match history (completed games) |

## Local Setup

### Prerequisites

- Python 3.12+
- Node.js 18+
- npm

### 1. Clone and install

```bash
# Backend
cd backend
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt

# Frontend (new terminal)
cd frontend
npm install
```

### 2. Configure environment

```bash
# Backend
cd backend
cp .env.example .env
# Edit .env — defaults work for local development

# Frontend (optional — defaults work with Vite dev proxy)
cd frontend
cp .env.example .env.local
```

### 3. Start the servers

```bash
# Backend (terminal 1)
cd backend
python run.py

# Frontend (terminal 2)
cd frontend
npm run dev
```

Open http://localhost:5173 in your browser.

### 4. Run tests

```bash
cd backend
python -m pytest -q
```

## Production Setup

### 1. Build the frontend

```bash
cd frontend
npm run build
```

This creates a `dist/` directory with optimized static assets.

### 2. Deploy the frontend

Serve `frontend/dist/` from any static host (Nginx, Caddy, Vercel, Netlify, Cloudflare Pages).

Example Nginx config:

```nginx
server {
    listen 80;
    server_name yourdomain.com;

    # Serve frontend static files
    location / {
        root /var/www/hand-cricket/dist;
        try_files $uri $uri/ /index.html;
    }

    # Proxy API to backend
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    # Proxy WebSocket to backend
    location /ws/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 86400;
    }
}
```

### 3. Deploy the backend

```bash
cd backend
pip install -r requirements.txt
python run.py --production
```

For production, use a process manager (systemd, supervisor, or Docker):

```bash
# Example systemd service
ExecStart=/path/to/venv/bin/python run.py --production
```

**Important:** The backend uses in-memory room state. A single worker is required — multiple workers create isolated state silos.

### 4. Configure environment variables

**Backend:**

| Variable | Default | Description |
|----------|---------|-------------|
| `ENVIRONMENT` | `development` | `development` or `production` |
| `HOST` | `0.0.0.0` | Bind address |
| `PORT` | `8000` | Listen port |
| `CORS_ORIGINS` | `http://localhost:5173` | Comma-separated allowed origins |
| `FRONTEND_ORIGIN` | _(empty)_ | Exact frontend URL for production CORS |
| `DATABASE_URL` | `sqlite+aiosqlite:///./hand_cricket.db` | SQLite file path |
| `LOG_LEVEL` | `info` | Logging level |
| `APP_VERSION` | `1.0.0` | Version string |

**Frontend:**

| Variable | Default | Description |
|----------|---------|-------------|
| `VITE_API_BASE_URL` | `/api` | REST API base URL |
| `VITE_WS_BASE_URL` | _(auto-detected)_ | WebSocket URL (auto-detects ws/wss) |

### 5. Configure HTTPS

The frontend WebSocket client automatically uses `wss://` when the page is served over HTTPS. No code changes needed — just configure TLS on your reverse proxy.

### 6. Verify deployment

```bash
# Health check
curl https://yourdomain.com/health
# Expected: {"status":"ok","version":"1.0.0","environment":"production",...}
```

Open the app in two browser tabs, create a room, and verify WebSocket connectivity (green "Live" indicator in the nav bar).

## Architecture

```
frontend/                  backend/
├── src/                   ├── app/
│   ├── pages/             │   ├── api/          # REST endpoints
│   │   ├── LandingPage    │   ├── game/
│   │   ├── CreateRoom     │   │   ├── engine.py  # State machine
│   │   ├── JoinRoom       │   │   ├── rules.py   # Pure rule functions
│   │   ├── RoomPage       │   │   └── state.py   # In-memory registry
│   │   └── GamePage       │   ├── models/
│   ├── components/        │   │   └── domain.py  # Pydantic models
│   ├── state/             │   ├── services/      # Business logic
│   │   └── gameStore.ts   │   │   └── room_service.py
│   ├── services/          │   ├── websocket/     # WS transport
│   │   ├── websocket.ts   │   │   ├── handler.py
│   │   └── api.ts         │   │   ├── connection_manager.py
│   ├── hooks/             │   │   └── router.py
│   │   └── useWebSocket   │   ├── db.py          # SQLite persistence
│   ├── types/             │   ├── config.py      # Environment config
│   └── utils/             │   └── main.py        # FastAPI app
├── package.json           ├── run.py             # Server entry point
└── vite.config.ts         └── requirements.txt
```

**Data flow:** Frontend → WebSocket → handler.py → room_service.py → engine.py → rules.py → back to all clients.

All game decisions are server-authoritative. The frontend is a pure display layer.

## Game Rules

- **Numbers:** 0–10 (both batsman and bowler choose simultaneously)
- **OUT:** Matching numbers → batsman is dismissed (0 runs)
- **Special:** Batsman plays 0, bowler plays non-zero → batsman scores the bowler's number
- **Normal:** Batsman's number = runs scored
- **Toss:** One player picks ODD/EVEN, both reveal a number (0–10). Sum determines winner.
- **Extra wicket:** When teams are unequal, the smaller team gets a batting reprieve vote
- **Switching:** Batsmen can request to swap; bowlers can request to swap (requires acceptance)

## Known Limitations

- In-memory room state: server restart clears all active rooms (match history is persisted)
- Single worker: multiple uvicorn workers create isolated state silos
- No persistent player accounts: identity is session-based (survives page refresh within the same browser session)
- No over limit by default: innings end only when all wickets are down (configurable per room)
