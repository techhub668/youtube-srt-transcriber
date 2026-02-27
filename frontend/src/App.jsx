import { useState } from "react";
import VideoTranscriber from "./components/VideoTranscriber";
import LiveSTT from "./components/LiveSTT";
import MinutesAgent from "./components/MinutesAgent";

const API_URL = import.meta.env.VITE_API_URL || "";

export default function App() {
  const [tab, setTab] = useState("youtube");

  return (
    <div className="min-h-screen flex flex-col bg-gray-50">
      {/* Header */}
      <header className="bg-white border-b border-gray-200 px-4 py-3 shadow-sm">
        <div className="max-w-6xl mx-auto flex items-center justify-between">
          <h1 className="text-xl font-bold tracking-tight">
            <span className="text-red-600">YouTube</span> SRT Transcriber
          </h1>
          <span className="text-xs text-gray-400 hidden sm:inline">
            Powered by Whisper &middot; Cantonese-optimised
          </span>
        </div>
      </header>

      {/* Tab bar */}
      <div className="bg-white border-b border-gray-200">
        <div className="max-w-6xl mx-auto flex">
          <button
            onClick={() => setTab("youtube")}
            className={`flex-1 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
              tab === "youtube"
                ? "border-red-500 text-red-600"
                : "border-transparent text-gray-500 hover:text-gray-700"
            }`}
          >
            YouTube &rarr; SRT
          </button>
          <button
            onClick={() => setTab("live")}
            className={`flex-1 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
              tab === "live"
                ? "border-blue-500 text-blue-600"
                : "border-transparent text-gray-500 hover:text-gray-700"
            }`}
          >
            Live STT
          </button>
          <button
            onClick={() => setTab("minutes")}
            className={`flex-1 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
              tab === "minutes"
                ? "border-green-500 text-green-600"
                : "border-transparent text-gray-500 hover:text-gray-700"
            }`}
          >
            Minutes Agent
          </button>
        </div>
      </div>

      {/* Content */}
      <main className="flex-1 max-w-2xl w-full mx-auto p-4 sm:p-6">
        {tab === "youtube" && <VideoTranscriber apiUrl={API_URL} />}
        {tab === "live" && <LiveSTT apiUrl={API_URL} />}
        {tab === "minutes" && <MinutesAgent apiUrl={API_URL} />}
      </main>

      <footer className="text-center text-xs text-gray-400 py-3 border-t border-gray-100">
        youtube-srt-transcriber &copy; {new Date().getFullYear()}
      </footer>
    </div>
  );
}
