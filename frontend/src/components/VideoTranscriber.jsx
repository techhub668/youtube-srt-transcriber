import { useState } from "react";

const LANGUAGES = [
  { code: "yue", label: "Cantonese" },
  { code: "zh", label: "Mandarin" },
  { code: "en", label: "English" },
  { code: "ja", label: "Japanese" },
  { code: "ko", label: "Korean" },
];

export default function VideoTranscriber({ apiUrl }) {
  const [url, setUrl] = useState("");
  const [language, setLanguage] = useState("yue");
  const [loading, setLoading] = useState(false);
  const [progress, setProgress] = useState("");
  const [srtContent, setSrtContent] = useState("");
  const [filename, setFilename] = useState("");
  const [error, setError] = useState("");

  const [summary, setSummary] = useState("");
  const [summarizing, setSummarizing] = useState(false);
  const [summaryError, setSummaryError] = useState("");

  async function handleTranscribe(e) {
    e.preventDefault();
    if (!url.trim()) return;

    setLoading(true);
    setError("");
    setSrtContent("");
    setFilename("");
    setSummary("");
    setSummaryError("");
    setProgress("Downloading audio and transcribing...");

    try {
      const res = await fetch(`${apiUrl}/api/transcribe`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ youtube_url: url.trim(), language }),
      });

      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.error || `Server error ${res.status}`);
      }

      const data = await res.json();
      setSrtContent(data.srt_content);
      setFilename(data.filename);
      setProgress("Done!");
    } catch (err) {
      setError(err.message);
      setProgress("");
    } finally {
      setLoading(false);
    }
  }

  async function handleSummarize() {
    if (!srtContent) return;

    setSummarizing(true);
    setSummaryError("");
    setSummary("");

    try {
      const res = await fetch(`${apiUrl}/api/summarize`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: srtContent, mode: "summary" }),
      });

      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.error || `Server error ${res.status}`);
      }

      const data = await res.json();
      setSummary(data.summary);
    } catch (err) {
      setSummaryError(err.message);
    } finally {
      setSummarizing(false);
    }
  }

  function handleDownload() {
    if (filename) {
      window.open(`${apiUrl}/api/download/${filename}`, "_blank");
    }
  }

  function handleCopyToClipboard() {
    navigator.clipboard.writeText(srtContent);
  }

  function handleCopySummary() {
    navigator.clipboard.writeText(summary);
  }

  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-5 flex flex-col gap-4">
      <div className="flex items-center gap-2">
        <div className="w-8 h-8 rounded-lg bg-red-100 flex items-center justify-center text-red-600 font-bold text-sm">
          YT
        </div>
        <h2 className="font-semibold text-lg">YouTube &rarr; SRT</h2>
      </div>

      <form onSubmit={handleTranscribe} className="flex flex-col gap-3">
        <input
          type="url"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="https://www.youtube.com/watch?v=..."
          required
          className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-red-400 focus:border-transparent"
        />

        <div className="flex gap-2">
          <select
            value={language}
            onChange={(e) => setLanguage(e.target.value)}
            className="px-3 py-2 border border-gray-300 rounded-lg text-sm bg-white focus:outline-none focus:ring-2 focus:ring-red-400"
          >
            {LANGUAGES.map((l) => (
              <option key={l.code} value={l.code}>
                {l.label}
              </option>
            ))}
          </select>

          <button
            type="submit"
            disabled={loading}
            className="flex-1 px-4 py-2 bg-red-600 text-white rounded-lg text-sm font-medium hover:bg-red-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {loading ? "Transcribing..." : "Transcribe"}
          </button>
        </div>
      </form>

      {/* Progress */}
      {progress && (
        <div className="flex items-center gap-2 text-sm text-gray-600">
          {loading && (
            <div className="w-4 h-4 border-2 border-red-400 border-t-transparent rounded-full animate-spin" />
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

      {/* SRT Preview */}
      {srtContent && (
        <div className="flex flex-col gap-2">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-gray-500 uppercase tracking-wide">
              SRT Preview
            </span>
            <div className="flex gap-2">
              <button
                onClick={handleCopyToClipboard}
                className="text-xs px-2 py-1 text-gray-500 hover:text-gray-700 border border-gray-200 rounded transition-colors"
              >
                Copy
              </button>
              <button
                onClick={handleDownload}
                className="text-xs px-2 py-1 bg-green-600 text-white rounded hover:bg-green-700 transition-colors"
              >
                Download .srt
              </button>
              <button
                onClick={handleSummarize}
                disabled={summarizing}
                className="text-xs px-2 py-1 bg-purple-600 text-white rounded hover:bg-purple-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {summarizing ? "Summarizing..." : "Summarize"}
              </button>
            </div>
          </div>
          <pre className="bg-gray-50 border border-gray-200 rounded-lg p-3 text-xs leading-relaxed max-h-80 overflow-y-auto whitespace-pre-wrap">
            {srtContent}
          </pre>
        </div>
      )}

      {/* Summary Error */}
      {summaryError && (
        <div className="bg-red-50 text-red-700 text-sm rounded-lg px-3 py-2 border border-red-200">
          {summaryError}
        </div>
      )}

      {/* Summarizing indicator */}
      {summarizing && (
        <div className="flex items-center gap-2 text-sm text-gray-600">
          <div className="w-4 h-4 border-2 border-purple-400 border-t-transparent rounded-full animate-spin" />
          <span>Generating summary...</span>
        </div>
      )}

      {/* Summary */}
      {summary && (
        <div className="flex flex-col gap-2">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-purple-600 uppercase tracking-wide">
              Summary
            </span>
            <button
              onClick={handleCopySummary}
              className="text-xs px-2 py-1 text-gray-500 hover:text-gray-700 border border-gray-200 rounded transition-colors"
            >
              Copy
            </button>
          </div>
          <div className="bg-purple-50 border border-purple-200 rounded-lg p-3 text-sm leading-relaxed max-h-60 overflow-y-auto whitespace-pre-wrap">
            {summary}
          </div>
        </div>
      )}
    </div>
  );
}
