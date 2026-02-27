import os
import re
import uuid
import asyncio
import tempfile
import subprocess
from pathlib import Path

import yt_dlp
import opencc
import httpx
from groq import Groq
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, File, UploadFile, Form
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

SRT_DIR = Path(tempfile.gettempdir()) / "srt_output"
SRT_DIR.mkdir(exist_ok=True)

# Groq Whisper client
groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# Simplified -> Traditional converter (for Cantonese output)
_s2t = opencc.OpenCC("s2t")

# Ollama Cloud API
OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY")
OLLAMA_ENDPOINT = "https://ollama.com/api/chat"
OLLAMA_MODEL = "deepseek-v3.2"

# ElevenLabs Scribe API
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
ELEVENLABS_API_URL = "https://api.elevenlabs.io/v1/speech-to-text"
ELEVENLABS_MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB

_SUMMARY_PROMPT = """You are an AI assistant that summarizes video transcripts. You will receive SRT subtitle text from a YouTube video.

Instructions:
- Create a concise summary (2-4 paragraphs) of the main topics and key points
- Remove timing codes and numbering artifacts from SRT format
- Write in a clear, readable style
- CRITICAL: Output your summary in the SAME LANGUAGE as the input transcript. If the transcript is in Chinese, write in Chinese. If English, write in English.
- Do not add commentary, opinions, or information not present in the transcript
- Do not use markdown formatting

Now summarize the following transcript:"""

_POLISH_PROMPT = """角色設定：
你是一個專門處理語音轉文字結果的編輯助理，會把口語化文字整理成清晰、易讀的文字。
支援Mandarin、粵語（繁體中文）、英文、中英夾雜、Japanese、Korean，會保持原來的語言，不要硬改語言。

處理規則：
1. 去除口頭禪 / filler words：例如「呃、嗯、其實、你知唔知、like、you know、um、uh、so、actually、basically」等，除非對語氣或意思非常重要。
2. 修正標點與分段：加入合適標點、段落，令內容更好讀，但不要改變原本意思。
3. 保留關鍵專有名詞：產品名、人名、地點、數字、網址要盡量保留原樣。
4. 不要自己杜撰內容：如果原文不清楚，就保持模糊或用「（聽不清楚）」標註，不要亂補。
5. 保持原來用字風格：
   - 如果 transcript 是粵語口語，就用自然的粵語書寫（繁體），但不要過度地書面化。
   - 如果是英文，就用簡潔的英文。
   - 中英夾雜則可自然混合。
6. 不要使用 markdown 格式。

請整理以下語音轉文字內容："""

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


app = FastAPI(title="YouTube SRT Transcriber API")

app.add_middleware(DynamicCORSMiddleware)


class TranscribeRequest(BaseModel):
    youtube_url: str
    language: str = "yue"


class SummarizeRequest(BaseModel):
    text: str
    mode: str = "summary"  # "summary" or "polish"


# --------------- helpers ---------------


GROQ_MAX_FILE_SIZE = 24 * 1024 * 1024  # 24 MB (leave margin under 25 MB limit)
CHUNK_DURATION_SEC = 600  # 10-minute chunks


def _download_audio(youtube_url: str) -> str:
    """Download audio from a YouTube URL, return path to .mp3 file."""
    stem = str(SRT_DIR / str(uuid.uuid4()))
    ydl_opts = {
        "format": "bestaudio/best",
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "0",
            }
        ],
        "outtmpl": stem,
        "quiet": True,
        "no_warnings": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([youtube_url])
    mp3_path = stem + ".mp3"
    if not Path(mp3_path).exists():
        raise FileNotFoundError("yt-dlp failed to produce an audio file")
    return mp3_path


def _split_audio(audio_path: str) -> list[tuple[str, float]]:
    """Split audio into chunks if it exceeds Groq file size limit.

    Returns list of (chunk_path, offset_seconds) tuples.
    If file is small enough, returns [(original_path, 0.0)].
    """
    if Path(audio_path).stat().st_size <= GROQ_MAX_FILE_SIZE:
        return [(audio_path, 0.0)]

    chunks = []
    offset = 0.0
    idx = 0
    while True:
        chunk_path = str(SRT_DIR / f"chunk_{uuid.uuid4()}_{idx}.mp3")
        proc = subprocess.run(
            [
                "ffmpeg", "-y", "-i", audio_path,
                "-ss", str(offset),
                "-t", str(CHUNK_DURATION_SEC),
                "-acodec", "libmp3lame", "-ab", "128k",
                "-ac", "1", chunk_path,
            ],
            capture_output=True,
        )
        if proc.returncode != 0 or not Path(chunk_path).exists():
            break
        if Path(chunk_path).stat().st_size < 1000:
            # Empty/negligible chunk means we've passed the end
            Path(chunk_path).unlink(missing_ok=True)
            break
        chunks.append((chunk_path, offset))
        offset += CHUNK_DURATION_SEC
        idx += 1

    return chunks if chunks else [(audio_path, 0.0)]


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


def _normalize_audio(input_path: str) -> str:
    """Normalize audio to 16kHz mono for optimal transcription."""
    out_path = str(SRT_DIR / f"norm_{uuid.uuid4()}.mp3")
    proc = subprocess.run(
        [
            "ffmpeg", "-y", "-i", input_path,
            "-ar", "16000", "-ac", "1",
            "-af", "highpass=f=200,lowpass=f=3000",
            out_path
        ],
        capture_output=True,
    )
    if proc.returncode != 0 or not Path(out_path).exists():
        raise RuntimeError("Audio normalization failed")
    return out_path


def _format_ts(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _convert_chinese(text: str, language: str) -> str:
    """Cantonese -> Traditional Chinese, Mandarin -> Simplified (no-op)."""
    if language == "yue":
        return _s2t.convert(text)
    return text


def _build_srt(segments, language: str = "yue") -> str:
    """Build SRT string from Groq Whisper segments.

    Each segment has .start (float seconds), .end (float seconds), .text (str).
    """
    lines: list[str] = []
    idx = 1

    for seg in segments:
        text = (seg.get("text", "") if isinstance(seg, dict) else seg.text).strip()
        if not text:
            continue
        text = _convert_chinese(text, language)
        start = seg["start"] if isinstance(seg, dict) else seg.start
        end = seg["end"] if isinstance(seg, dict) else seg.end
        lines.append(f"{idx}")
        lines.append(f"{_format_ts(start)} --> {_format_ts(end)}")
        lines.append(text)
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
        chunks = await asyncio.to_thread(_split_audio, audio_path)

        all_segments = []
        for chunk_path, offset in chunks:
            def _transcribe(path=chunk_path, language=req.language):
                with open(path, "rb") as f:
                    return groq_client.audio.transcriptions.create(
                        file=("audio.mp3", f),
                        model="whisper-large-v3",
                        language=language,
                        response_format="verbose_json",
                        timestamp_granularities=["segment"],
                    )

            transcription = await asyncio.to_thread(_transcribe)

            segs = transcription.segments if hasattr(transcription, "segments") else transcription.get("segments", [])
            for seg in segs:
                if isinstance(seg, dict):
                    seg["start"] = seg.get("start", 0) + offset
                    seg["end"] = seg.get("end", 0) + offset
                else:
                    seg.start += offset
                    seg.end += offset
                all_segments.append(seg)

            # Clean up chunk if it's not the original file
            if chunk_path != audio_path:
                Path(chunk_path).unlink(missing_ok=True)

        srt_content = _build_srt(all_segments, language=req.language)

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
async def download_file(filename: str):
    # Prevent path traversal
    if "/" in filename or "\\" in filename or ".." in filename:
        return JSONResponse(status_code=400, content={"error": "Invalid filename"})
    filepath = SRT_DIR / filename
    if not filepath.exists():
        return JSONResponse(status_code=404, content={"error": "File not found"})

    # Determine media type based on extension
    if filename.endswith(".srt"):
        media_type = "application/x-subrip"
    elif filename.endswith(".txt"):
        media_type = "text/plain; charset=utf-8"
    else:
        media_type = "application/octet-stream"

    return FileResponse(
        filepath,
        filename=filename,
        media_type=media_type,
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

            def _transcribe_chunk(path=wav_path, language=lang):
                with open(path, "rb") as f:
                    return groq_client.audio.transcriptions.create(
                        file=("chunk.wav", f),
                        model="whisper-large-v3",
                        language=language,
                        response_format="json",
                    )

            transcription = await asyncio.to_thread(_transcribe_chunk)

            Path(wav_path).unlink(missing_ok=True)

            raw_text = transcription.text if hasattr(transcription, "text") else transcription.get("text", "")
            text = raw_text.strip() if raw_text else ""
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


async def _call_ollama(text: str, mode: str) -> str:
    """Call Ollama Cloud API for summarization / polishing."""
    if not OLLAMA_API_KEY:
        raise RuntimeError("OLLAMA_API_KEY not configured")

    system_prompt = _SUMMARY_PROMPT if mode == "summary" else _POLISH_PROMPT

    payload = {
        "model": OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": text},
        ],
        "stream": False,
    }

    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(
            OLLAMA_ENDPOINT,
            json=payload,
            headers={"Authorization": f"Bearer {OLLAMA_API_KEY}"},
        )
        resp.raise_for_status()
        data = resp.json()
        return data["message"]["content"]


async def _call_elevenlabs_scribe(audio_path: str, language: str) -> dict:
    """Call ElevenLabs Scribe API for transcription."""
    if not ELEVENLABS_API_KEY:
        raise RuntimeError("ELEVENLABS_API_KEY not configured")

    with open(audio_path, "rb") as f:
        files = {"file": (Path(audio_path).name, f.read())}

    data = {"model_id": "scribe_v1", "language_code": language}

    async with httpx.AsyncClient(timeout=300.0) as client:
        resp = await client.post(
            ELEVENLABS_API_URL,
            headers={"xi-api-key": ELEVENLABS_API_KEY},
            files=files,
            data=data,
        )
        resp.raise_for_status()
        return resp.json()


def _format_minutes_text(result: dict, language: str, include_timestamps: bool) -> str:
    """Format ElevenLabs response as plain text or timestamped text."""
    text = result.get("text", "")
    text = _convert_chinese(text, language)

    if not include_timestamps:
        return text

    # Format with timestamps from words if available
    words = result.get("words", [])
    if not words:
        return text

    # Group words into lines (roughly by sentence or time gaps)
    lines = []
    current_line_words = []
    current_start = None

    for word in words:
        word_start = word.get("start", 0)
        word_text = word.get("text", "")

        if current_start is None:
            current_start = word_start

        current_line_words.append(word_text)

        # Break line on sentence-ending punctuation
        if word_text.rstrip().endswith((".", "。", "!", "?", "！", "？")):
            ts = f"[{int(current_start//60):02d}:{int(current_start%60):02d}]"
            line_text = "".join(current_line_words)
            line_text = _convert_chinese(line_text, language)
            lines.append(f"{ts} {line_text}")
            current_line_words = []
            current_start = None

    # Handle remaining words
    if current_line_words:
        ts = f"[{int((current_start or 0)//60):02d}:{int((current_start or 0)%60):02d}]"
        line_text = "".join(current_line_words)
        line_text = _convert_chinese(line_text, language)
        lines.append(f"{ts} {line_text}")

    return "\n".join(lines)


@app.post("/api/summarize")
async def summarize_text(req: SummarizeRequest):
    if req.mode not in ("summary", "polish"):
        return JSONResponse(
            status_code=400,
            content={"error": "Mode must be 'summary' or 'polish'."},
        )
    if not req.text or not req.text.strip():
        return JSONResponse(
            status_code=400,
            content={"error": "Text content is required."},
        )
    if len(req.text) > 50000:
        return JSONResponse(
            status_code=400,
            content={"error": "Text too long (max 50 000 characters)."},
        )

    try:
        result = await _call_ollama(req.text.strip(), req.mode)
        return {"summary": result}
    except httpx.HTTPStatusError as exc:
        return JSONResponse(
            status_code=500,
            content={"error": f"Ollama API error: {exc.response.status_code}"},
        )
    except Exception as exc:
        return JSONResponse(status_code=500, content={"error": str(exc)})


@app.post("/api/minutes")
async def transcribe_minutes(
    file: UploadFile = File(...),
    language: str = Form("yue"),
    include_timestamps: bool = Form(False),
):
    """Transcribe uploaded audio file using ElevenLabs Scribe API."""
    # Validate file
    if not file.filename:
        return JSONResponse(status_code=400, content={"error": "No file provided"})

    ext = Path(file.filename).suffix.lower()
    if ext not in {".mp3", ".wav", ".m4a", ".ogg", ".flac", ".webm", ".mp4", ".mov"}:
        return JSONResponse(
            status_code=400,
            content={"error": f"Unsupported format: {ext}. Use mp3, wav, m4a, ogg, flac, webm, mp4, or mov."},
        )

    content = await file.read()
    if len(content) > ELEVENLABS_MAX_FILE_SIZE:
        return JSONResponse(
            status_code=400,
            content={"error": "File too large (max 100MB)"},
        )

    # Save uploaded file
    input_path = str(SRT_DIR / f"upload_{uuid.uuid4()}{ext}")
    Path(input_path).write_bytes(content)
    norm_path = None

    try:
        # Normalize audio
        norm_path = await asyncio.to_thread(_normalize_audio, input_path)

        # Transcribe with ElevenLabs
        result = await _call_elevenlabs_scribe(norm_path, language)

        # Format output
        text = _format_minutes_text(result, language, include_timestamps)

        # Save for download
        txt_filename = f"{uuid.uuid4()}.txt"
        (SRT_DIR / txt_filename).write_text(text, encoding="utf-8")

        return {
            "text": text,
            "preview": text[:1000],
            "filename": txt_filename,
        }

    except httpx.HTTPStatusError as exc:
        return JSONResponse(
            status_code=500,
            content={"error": f"ElevenLabs API error: {exc.response.status_code} - {exc.response.text[:200]}"},
        )
    except Exception as exc:
        return JSONResponse(status_code=500, content={"error": str(exc)})
    finally:
        Path(input_path).unlink(missing_ok=True)
        if norm_path:
            Path(norm_path).unlink(missing_ok=True)


@app.get("/health")
async def health():
    return {"status": "ok", "model": "whisper-large-v3"}
