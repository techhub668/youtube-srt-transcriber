import os
import re
import uuid
import asyncio
import tempfile
import subprocess
from contextlib import asynccontextmanager
from pathlib import Path

import yt_dlp
import opencc
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

SRT_DIR = Path(tempfile.gettempdir()) / "srt_output"
SRT_DIR.mkdir(exist_ok=True)

asr_model = None

# Simplified → Traditional converter (for Cantonese output)
_s2t = opencc.OpenCC("s2t")

YOUTUBE_URL_PATTERN = re.compile(
    r"^https?://(www\.)?(youtube\.com/watch\?|youtu\.be/|youtube\.com/shorts/)"
)

# Trusted origin patterns (any *.vercel.app + explicitly configured origins)
_EXTRA_ORIGINS = [
    o.strip()
    for o in os.getenv("ALLOWED_ORIGINS", "").split(",")
    if o.strip() and o.strip() != "*"
]
_VERCEL_PATTERN = re.compile(r"^https://[a-z0-9\-]+\.vercel\.app$")


def _origin_allowed(origin: str) -> bool:
    if not origin:
        return False
    if _VERCEL_PATTERN.match(origin):
        return True
    return origin in _EXTRA_ORIGINS


class DynamicCORSMiddleware(BaseHTTPMiddleware):
    """Allow any *.vercel.app origin + explicit ALLOWED_ORIGINS."""

    async def dispatch(self, request: Request, call_next):
        origin = request.headers.get("origin", "")

        if request.method == "OPTIONS":
            # Preflight
            if _origin_allowed(origin):
                from starlette.responses import Response

                return Response(
                    status_code=200,
                    headers={
                        "Access-Control-Allow-Origin": origin,
                        "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
                        "Access-Control-Allow-Headers": "Content-Type, Authorization",
                        "Access-Control-Allow-Credentials": "true",
                        "Access-Control-Max-Age": "600",
                    },
                )

        response = await call_next(request)

        if _origin_allowed(origin):
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Credentials"] = "true"

        return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    global asr_model
    from funasr import AutoModel

    asr_model = AutoModel(
        model="iic/SenseVoiceSmall",
        vad_model="fsmn-vad",
        vad_kwargs={"max_single_segment_time": 30000},
        trust_remote_code=True,
        device="cpu",
    )
    yield


app = FastAPI(title="YouTube SRT Transcriber API", lifespan=lifespan)

app.add_middleware(DynamicCORSMiddleware)


class TranscribeRequest(BaseModel):
    youtube_url: str
    language: str = "yue"


# --------------- helpers ---------------


def _download_audio(youtube_url: str) -> str:
    """Download audio from a YouTube URL, return path to .wav file."""
    stem = str(SRT_DIR / str(uuid.uuid4()))
    ydl_opts = {
        "format": "bestaudio/best",
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "wav",
                "preferredquality": "0",
            }
        ],
        "outtmpl": stem,
        "quiet": True,
        "no_warnings": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([youtube_url])
    wav_path = stem + ".wav"
    if not Path(wav_path).exists():
        raise FileNotFoundError("yt-dlp failed to produce an audio file")
    return wav_path


def _get_audio_duration(wav_path: str) -> float:
    """Return audio duration in seconds via ffprobe."""
    try:
        proc = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                wav_path,
            ],
            capture_output=True,
            text=True,
        )
        return float(proc.stdout.strip())
    except Exception:
        return 0.0


def _convert_to_wav(input_bytes: bytes) -> str:
    """Convert arbitrary audio bytes (webm/ogg) to 16 kHz mono wav via ffmpeg."""
    in_path = SRT_DIR / f"live_in_{uuid.uuid4()}.webm"
    out_path = SRT_DIR / f"live_out_{uuid.uuid4()}.wav"
    in_path.write_bytes(input_bytes)
    proc = subprocess.run(
        [
            "ffmpeg", "-y", "-i", str(in_path),
            "-ar", "16000", "-ac", "1", "-f", "wav", str(out_path),
        ],
        capture_output=True,
    )
    in_path.unlink(missing_ok=True)
    if proc.returncode != 0 or not out_path.exists():
        raise RuntimeError("ffmpeg conversion failed")
    return str(out_path)


def _format_ts(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _convert_chinese(text: str, language: str) -> str:
    """Cantonese → Traditional Chinese, Mandarin → Simplified (no-op)."""
    if language == "yue":
        return _s2t.convert(text)
    return text


def _build_srt(result: list, audio_duration: float = 0.0, language: str = "yue") -> str:
    """Build SRT string from funasr result list."""
    lines: list[str] = []
    idx = 1

    # Collect segments with cleaned text
    segments = []
    for item in result:
        raw_text: str = item.get("text", "")
        text = re.sub(r"<\|[^|]*\|>", "", raw_text).strip()
        if not text:
            continue
        text = _convert_chinese(text, language)
        segments.append({"text": text, "timestamp": item.get("timestamp")})

    if not segments:
        return ""

    # Estimate per-segment duration when timestamps are missing
    seg_duration = (audio_duration / len(segments)) if audio_duration > 0 else 5.0

    for i, seg in enumerate(segments):
        ts = seg["timestamp"]
        if ts and len(ts) >= 2:
            start_s = ts[0][0] / 1000
            end_s = ts[-1][1] / 1000
        else:
            start_s = i * seg_duration
            end_s = (i + 1) * seg_duration

        lines.append(f"{idx}")
        lines.append(f"{_format_ts(start_s)} --> {_format_ts(end_s)}")
        lines.append(seg["text"])
        lines.append("")
        idx += 1

    return "\n".join(lines)


# --------------- routes ---------------


@app.post("/api/transcribe")
async def transcribe_youtube(req: TranscribeRequest):
    if not YOUTUBE_URL_PATTERN.match(req.youtube_url):
        return JSONResponse(
            status_code=400,
            content={"error": "Invalid YouTube URL. Provide a youtube.com or youtu.be link."},
        )

    try:
        audio_path = await asyncio.to_thread(_download_audio, req.youtube_url)

        duration = await asyncio.to_thread(_get_audio_duration, audio_path)

        result = await asyncio.to_thread(
            asr_model.generate,
            input=audio_path,
            cache={},
            language=req.language,
            use_itn=True,
            batch_size_s=60,
            merge_vad=True,
            merge_length_s=15,
        )

        srt_content = _build_srt(result, audio_duration=duration, language=req.language)

        filename = f"{uuid.uuid4()}.srt"
        (SRT_DIR / filename).write_text(srt_content, encoding="utf-8")

        # clean up source audio
        Path(audio_path).unlink(missing_ok=True)

        return {
            "srt_content": srt_content,
            "preview": srt_content[:1000],
            "filename": filename,
        }

    except Exception as exc:
        return JSONResponse(status_code=500, content={"error": str(exc)})


@app.get("/api/download/{filename}")
async def download_srt(filename: str):
    # Prevent path traversal
    if "/" in filename or "\\" in filename or ".." in filename:
        return JSONResponse(status_code=400, content={"error": "Invalid filename"})
    filepath = SRT_DIR / filename
    if not filepath.exists():
        return JSONResponse(status_code=404, content={"error": "File not found"})
    return FileResponse(
        filepath,
        filename=filename,
        media_type="application/x-subrip",
    )


@app.websocket("/api/live-stt")
async def live_stt(websocket: WebSocket):
    await websocket.accept()
    try:
        # Client sends first message with optional config
        init = await websocket.receive_json()
        lang = init.get("language", "yue")

        while True:
            audio_bytes = await websocket.receive_bytes()
            if len(audio_bytes) < 100:
                continue

            wav_path = await asyncio.to_thread(_convert_to_wav, audio_bytes)

            result = await asyncio.to_thread(
                asr_model.generate,
                input=wav_path,
                cache={},
                language=lang,
                use_itn=True,
            )

            Path(wav_path).unlink(missing_ok=True)

            text = ""
            if result:
                raw = result[0].get("text", "")
                text = re.sub(r"<\|[^|]*\|>", "", raw).strip()
                if text:
                    text = _convert_chinese(text, lang)

            await websocket.send_json({"text": text})

    except WebSocketDisconnect:
        pass
    except Exception as exc:
        try:
            await websocket.send_json({"error": str(exc)})
        except Exception:
            pass


@app.get("/health")
async def health():
    return {"status": "ok", "model": "SenseVoiceSmall"}
