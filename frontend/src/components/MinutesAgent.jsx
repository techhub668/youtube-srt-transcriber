import { useState, useRef } from "react";

const LANGUAGES = [
  { code: "yue", label: "Cantonese" },
  { code: "zh", label: "Mandarin" },
  { code: "en", label: "English" },
  { code: "ja", label: "Japanese" },
  { code: "ko", label: "Korean" },
];

const ACCEPTED_FORMATS = ".mp3,.wav,.m4a,.ogg,.flac,.webm,.mp4,.mov";

export default function MinutesAgent({ apiUrl }) {
  const [file, setFile] = useState(null);
  const [language, setLanguage] = useState("yue");
  const [includeTimestamps, setIncludeTimestamps] = useState(false);
  const [loading, setLoading] = useState(false);
  const [progress, setProgress] = useState("");
  const [transcriptText, setTranscriptText] = useState("");
  const [filename, setFilename] = useState("");
  const [error, setError] = useState("");

  const [polished, setPolished] = useState("");
  const [polishing, setPolishing] = useState(false);
  const [polishError, setPolishError] = useState("");

  const fileInputRef = useRef(null);

  function handleFileChange(e) {
    const selected = e.target.files?.[0];
    if (selected) {
      setFile(selected);
      setError("");
      setTranscriptText("");
      setFilename("");
      setPolished("");
      setPolishError("");
    }
  }

  async function handleTranscribe(e) {
    e.preventDefault();
    if (!file) return;

    setLoading(true);
    setError("");
    setTranscriptText("");
    setFilename("");
    setPolished("");
    setPolishError("");
    setProgress("Uploading and transcribing...");

    try {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("language", language);
      formData.append("include_timestamps", includeTimestamps.toString());

      const res = await fetch(`${apiUrl}/api/minutes`, {
        method: "POST",
        body: formData,
      });

      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.error || `Server error ${res.status}`);
      }

      const data = await res.json();
      setTranscriptText(data.text);
      setFilename(data.filename);
      setProgress("Done!");
    } catch (err) {
      setError(err.message);
      setProgress("");
    } finally {
      setLoading(false);
    }
  }

  async function handlePolish() {
    if (!transcriptText) return;

    setPolishing(true);
    setPolishError("");
    setPolished("");

    try {
      const res = await fetch(`${apiUrl}/api/summarize`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: transcriptText, mode: "polish" }),
      });

      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.error || `Server error ${res.status}`);
      }

      const data = await res.json();
      setPolished(data.summary);
    } catch (err) {
      setPolishError(err.message);
    } finally {
      setPolishing(false);
    }
  }

  function handleDownload() {
    if (filename) {
      window.open(`${apiUrl}/api/download/${filename}`, "_blank");
    }
  }

  function handleCopy() {
    navigator.clipboard.writeText(transcriptText);
  }

  function handleCopyPolished() {
    navigator.clipboard.writeText(polished);
  }

  function handleClearFile() {
    setFile(null);
    setTranscriptText("");
    setFilename("");
    setError("");
    setProgress("");
    setPolished("");
    setPolishError("");
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  }

  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-5 flex flex-col gap-4">
      <div className="flex items-center gap-2">
        <div className="w-8 h-8 rounded-lg bg-green-100 flex items-center justify-center text-green-600 font-bold text-sm">
          MA
        </div>
        <h2 className="font-semibold text-lg">Minutes Agent</h2>
      </div>

      <form onSubmit={handleTranscribe} className="flex flex-col gap-3">
        {/* File input */}
        <div className="flex flex-col gap-1">
          <label className="text-xs font-medium text-gray-500 uppercase tracking-wide">
            Audio File
          </label>
          <div className="flex gap-2 items-center">
            <input
              ref={fileInputRef}
              type="file"
              accept={ACCEPTED_FORMATS}
              onChange={handleFileChange}
              className="flex-1 text-sm text-gray-500 file:mr-3 file:py-2 file:px-3 file:rounded-lg file:border-0 file:text-sm file:font-medium file:bg-green-50 file:text-green-700 hover:file:bg-green-100 file:cursor-pointer"
            />
            {file && (
              <button
                type="button"
                onClick={handleClearFile}
                className="text-xs px-2 py-1 text-gray-500 hover:text-gray-700 border border-gray-200 rounded transition-colors"
              >
                Clear
              </button>
            )}
          </div>
          {file && (
            <span className="text-xs text-gray-400">
              Selected: {file.name} ({(file.size / 1024 / 1024).toFixed(2)} MB)
            </span>
          )}
        </div>

        {/* Language and Timestamps */}
        <div className="flex gap-3 items-center flex-wrap">
          <select
            value={language}
            onChange={(e) => setLanguage(e.target.value)}
            disabled={loading}
            className="px-3 py-2 border border-gray-300 rounded-lg text-sm bg-white focus:outline-none focus:ring-2 focus:ring-green-400 disabled:opacity-50"
          >
            {LANGUAGES.map((l) => (
              <option key={l.code} value={l.code}>
                {l.label}
              </option>
            ))}
          </select>

          <label className="flex items-center gap-2 text-sm text-gray-600 cursor-pointer">
            <input
              type="checkbox"
              checked={includeTimestamps}
              onChange={(e) => setIncludeTimestamps(e.target.checked)}
              disabled={loading}
              className="w-4 h-4 rounded border-gray-300 text-green-600 focus:ring-green-500 disabled:opacity-50"
            />
            Include timestamps
          </label>
        </div>

        {/* Submit button */}
        <button
          type="submit"
          disabled={!file || loading}
          className="w-full px-4 py-2 bg-green-600 text-white rounded-lg text-sm font-medium hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {loading ? "Transcribing..." : "Transcribe Audio"}
        </button>
      </form>

      {/* Progress */}
      {progress && (
        <div className="flex items-center gap-2 text-sm text-gray-600">
          {loading && (
            <div className="w-4 h-4 border-2 border-green-400 border-t-transparent rounded-full animate-spin" />
          )}
          <span>{progress}</span>
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="bg-red-50 text-red-700 text-sm rounded-lg px-3 py-2 border border-red-200">
          {error}
        </div>
      )}

      {/* Transcript Preview */}
      {transcriptText && (
        <div className="flex flex-col gap-2">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-gray-500 uppercase tracking-wide">
              Transcript
            </span>
            <div className="flex gap-2">
              <button
                onClick={handleCopy}
                className="text-xs px-2 py-1 text-gray-500 hover:text-gray-700 border border-gray-200 rounded transition-colors"
              >
                Copy
              </button>
              <button
                onClick={handleDownload}
                className="text-xs px-2 py-1 bg-green-600 text-white rounded hover:bg-green-700 transition-colors"
              >
                Download .txt
              </button>
              <button
                onClick={handlePolish}
                disabled={polishing}
                className="text-xs px-2 py-1 bg-purple-600 text-white rounded hover:bg-purple-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {polishing ? "Polishing..." : "Polish"}
              </button>
            </div>
          </div>
          <pre className="bg-gray-50 border border-gray-200 rounded-lg p-3 text-sm leading-relaxed max-h-80 overflow-y-auto whitespace-pre-wrap">
            {transcriptText}
          </pre>
        </div>
      )}

      {/* Polish Error */}
      {polishError && (
        <div className="bg-red-50 text-red-700 text-sm rounded-lg px-3 py-2 border border-red-200">
          {polishError}
        </div>
      )}

      {/* Polishing indicator */}
      {polishing && (
        <div className="flex items-center gap-2 text-sm text-gray-600">
          <div className="w-4 h-4 border-2 border-purple-400 border-t-transparent rounded-full animate-spin" />
          <span>Polishing transcript...</span>
        </div>
      )}

      {/* Polished Text */}
      {polished && (
        <div className="flex flex-col gap-2">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-purple-600 uppercase tracking-wide">
              Polished Transcript
            </span>
            <button
              onClick={handleCopyPolished}
              className="text-xs px-2 py-1 text-gray-500 hover:text-gray-700 border border-gray-200 rounded transition-colors"
            >
              Copy
            </button>
          </div>
          <div className="bg-purple-50 border border-purple-200 rounded-lg p-3 text-sm leading-relaxed max-h-60 overflow-y-auto whitespace-pre-wrap">
            {polished}
          </div>
        </div>
      )}
    </div>
  );
}
