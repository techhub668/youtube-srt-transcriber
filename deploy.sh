#!/usr/bin/env bash
set -euo pipefail

echo "=== YouTube SRT Transcriber - Deploy ==="

# 1. Push to GitHub
echo ""
echo "[1/3] Pushing to GitHub..."
git add .
git commit -m "Deploy: YouTube SRT Transcriber" || echo "Nothing to commit"
git push -u origin main

# 2. Vercel (frontend)
echo ""
echo "[2/3] Frontend (Vercel)"
echo "  1. Go to https://vercel.com/new"
echo "  2. Import: techhub668/youtube-srt-transcriber"
echo "  3. Set Root Directory: frontend/"
echo "  4. Framework Preset: Vite"
echo "  5. Add env var: VITE_API_URL = https://<your-railway-app>.up.railway.app"
echo "  6. Deploy"

# 3. Railway (backend)
echo ""
echo "[3/3] Backend (Railway)"
if command -v railway &> /dev/null; then
  echo "  Railway CLI found. Deploying backend..."
  cd backend
  railway up
  echo ""
  echo "  Set ALLOWED_ORIGINS in Railway to your Vercel URL for security."
else
  echo "  Railway CLI not found. Manual steps:"
  echo "  1. Go to https://railway.app/new"
  echo "  2. Deploy from GitHub: techhub668/youtube-srt-transcriber"
  echo "  3. Set Root Directory: backend/"
  echo "  4. Railway will detect the Dockerfile automatically"
  echo "  5. Set env var: ALLOWED_ORIGINS = https://<your-app>.vercel.app"
fi

echo ""
echo "=== Done ==="
