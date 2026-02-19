import { useState, useRef, useCallback, useEffect } from "react";

const LANGUAGES = [
  { code: "yue", label: "Cantonese" },
  { code: "zh", label: "Mandarin" },
  { code: "en", label: "English" },
  { code: "ja", label: "Japanese" },
  { code: "ko", label: "Korean" },
];

export default function LiveSTT({ apiUrl }) {
  const [language, setLanguage] = useState("yue");
  const [recording, setRecording] = useState(false);
  const [transcript, setTranscript] = useState([]);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");

  const wsRef = useRef(null);
  const streamRef = useRef(null);
  const recorderRef = useRef(null);
  const recordingRef = useRef(false);
  const scrollRef = useRef(null);

  // Auto-scroll transcript area
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [transcript]);

  const getWsUrl = useCallback(() => {
    if (apiUrl) {
      const base = apiUrl.replace(/^http/, "ws");
      return `${base}/api/live-stt`;
    }
    const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    return `${proto}//${window.location.host}/api/live-stt`;
  }, [apiUrl]);

  const startSegment = useCallback(() => {
    if (!recordingRef.current || !streamRef.current) return;

    const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
      ? "audio/webm;codecs=opus"
      : "audio/webm";

    const recorder = new MediaRecorder(streamRef.current, { mimeType });
    const chunks = [];

    recorder.ondataavailable = (e) => {
      if (e.data.size > 0) chunks.push(e.data);
    };

    recorder.onstop = () => {
      if (chunks.length > 0 && wsRef.current?.readyState === WebSocket.OPEN) {
        const blob = new Blob(chunks, { type: mimeType });
        wsRef.current.send(blob);
      }
      // Start next segment if still recording
      if (recordingRef.current) {
        startSegment();
      }
    };

    recorderRef.current = recorder;
    recorder.start();

    // Stop after 3 seconds to create a complete, decodable chunk
    setTimeout(() => {
      if (recorder.state === "recording") {
        recorder.stop();
      }
    }, 3000);
  }, []);

  async function handleStart() {
    setError("");
    setStatus("Requesting microphone access...");

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, sampleRate: 16000 },
      });
      streamRef.current = stream;

      // Connect WebSocket
      setStatus("Connecting...");
      const ws = new WebSocket(getWsUrl());
      wsRef.current = ws;

      ws.onopen = () => {
        ws.send(JSON.stringify({ language }));
        setStatus("Listening...");
        setRecording(true);
        recordingRef.current = true;
        startSegment();
      };

      ws.onmessage = (e) => {
        const data = JSON.parse(e.data);
        if (data.error) {
          setError(data.error);
          return;
        }
        if (data.text) {
          setTranscript((prev) => [...prev, data.text]);
        }
      };

      ws.onerror = () => {
        setError("WebSocket connection error");
        handleStop();
      };

      ws.onclose = () => {
        if (recordingRef.current) {
          setStatus("Connection closed");
          handleStop();
        }
      };
    } catch (err) {
      setError(err.message);
      setStatus("");
    }
  }

  function handleStop() {
    recordingRef.current = false;
    setRecording(false);
    setStatus("");

    if (recorderRef.current?.state === "recording") {
      recorderRef.current.stop();
    }
    recorderRef.current = null;

    wsRef.current?.close();
    wsRef.current = null;

    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
  }

  function handleClear() {
    setTranscript([]);
    setError("");
  }

  function handleCopy() {
    navigator.clipboard.writeText(transcript.join("\n"));
  }

  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-5 flex flex-col gap-4">
      <div className="flex items-center gap-2">
        <div className="w-8 h-8 rounded-lg bg-blue-100 flex items-center justify-center text-blue-600 font-bold text-sm">
          Mic
        </div>
        <h2 className="font-semibold text-lg">Live Speech-to-Text</h2>
      </div>

      {/* Controls */}
      <div className="flex gap-2 items-center">
        <select
          value={language}
          onChange={(e) => setLanguage(e.target.value)}
          disabled={recording}
          className="px-3 py-2 border border-gray-300 rounded-lg text-sm bg-white focus:outline-none focus:ring-2 focus:ring-blue-400 disabled:opacity-50"
        >
          {LANGUAGES.map((l) => (
            <option key={l.code} value={l.code}>
              {l.label}
            </option>
          ))}
        </select>

        {!recording ? (
          <button
            onClick={handleStart}
            className="flex-1 px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 transition-colors"
          >
            Start Recording
          </button>
        ) : (
          <button
            onClick={handleStop}
            className="flex-1 px-4 py-2 bg-red-600 text-white rounded-lg text-sm font-medium hover:bg-red-700 transition-colors animate-pulse"
          >
            Stop Recording
          </button>
        )}
      </div>

      {/* Status */}
      {status && (
        <div className="flex items-center gap-2 text-sm text-gray-600">
          {recording && (
            <span className="w-2.5 h-2.5 rounded-full bg-red-500 animate-pulse" />
          )}
          <span>{status}</span>
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="bg-red-50 text-red-700 text-sm rounded-lg px-3 py-2 border border-red-200">
          {error}
        </div>
      )}

      {/* Transcript area */}
      <div className="flex flex-col gap-2 flex-1">
        <div className="flex items-center justify-between">
          <span className="text-xs font-medium text-gray-500 uppercase tracking-wide">
            Transcript
          </span>
          <div className="flex gap-2">
            <button
              onClick={handleCopy}
              disabled={transcript.length === 0}
              className="text-xs px-2 py-1 text-gray-500 hover:text-gray-700 border border-gray-200 rounded transition-colors disabled:opacity-30"
            >
              Copy
            </button>
            <button
              onClick={handleClear}
              disabled={transcript.length === 0}
              className="text-xs px-2 py-1 text-gray-500 hover:text-gray-700 border border-gray-200 rounded transition-colors disabled:opacity-30"
            >
              Clear
            </button>
          </div>
        </div>
        <div
          ref={scrollRef}
          className="bg-gray-50 border border-gray-200 rounded-lg p-3 text-sm leading-relaxed min-h-[200px] max-h-80 overflow-y-auto"
        >
          {transcript.length === 0 ? (
            <span className="text-gray-400">
              Transcribed text will appear here...
            </span>
          ) : (
            transcript.map((line, i) => (
              <p key={i} className="mb-1">
                {line}
              </p>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
