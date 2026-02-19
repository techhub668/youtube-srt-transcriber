# YouTube SRT Transcriber

YouTube video to SRT subtitle converter + live speech-to-text web application.

Uses **SenseVoice Small** (Alibaba) for ASR — optimised for **Cantonese (yue)**, with support for Mandarin, English, Japanese, and Korean.

## Architecture

| Component | Tech | Deployment |
|-----------|------|------------|
| Frontend | React 18 + Vite + Tailwind CSS | Vercel |
| Backend | FastAPI + SenseVoice + yt-dlp | Railway (Hobby Tier) |

## Features

- **YouTube → SRT**: Paste a YouTube URL, select language, get downloadable `.srt` subtitles
- **Live Speech-to-Text**: Real-time microphone transcription via WebSocket
- Responsive layout (side-by-side on desktop, tabbed on mobile)

## Local Development

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
uvicorn main:app --reload
```

Requires `ffmpeg` installed on your system.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

The Vite dev server proxies `/api` requests to `http://localhost:8000`.

## Deployment

### Frontend → Vercel

1. Import `techhub668/youtube-srt-transcriber` on [vercel.com/new](https://vercel.com/new)
2. Set **Root Directory** to `frontend/`
3. Framework Preset: **Vite**
4. Add environment variable: `VITE_API_URL` = `https://<your-railway-app>.up.railway.app`
5. Deploy

### Backend → Railway

1. Create new project on [railway.app](https://railway.app/new)
2. Deploy from GitHub: `techhub668/youtube-srt-transcriber`
3. Set **Root Directory** to `backend/`
4. Railway detects the Dockerfile automatically
5. Add environment variable: `ALLOWED_ORIGINS` = `https://<your-app>.vercel.app`

### Environment Variables

| Variable | Where | Description |
|----------|-------|-------------|
| `VITE_API_URL` | Vercel | Full Railway backend URL |
| `ALLOWED_ORIGINS` | Railway | Comma-separated allowed CORS origins |
