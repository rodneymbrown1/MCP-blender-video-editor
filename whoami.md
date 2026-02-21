# Video Draft MCP

## What It Is
Video Draft MCP is a video drafting and scaffolding tool that connects an Agent to Blender's Video Sequence Editor (VSE) through the Model Context Protocol (MCP). Users provide audio, and the system auto-generates timestamped slides from speech transcription, which can then be edited interactively through conversation.

## Core Capabilities
- **Audio Transcription**: Uses faster-whisper (CTranslate2, CPU int8) to transcribe audio files with word-level timestamps
- **Auto Slide Generation**: Groups transcript segments into slides using pause detection, sentence boundaries, and duration constraints
- **Slide Editing**: Full CRUD operations on slides (create, read, update, delete, split, merge, reorder)
- **Image Search**: Multi-source free image search across Unsplash, Pexels, and Pixabay with rate limiting
- **Style System**: Built-in presets (youtube, presentation, cinematic) with per-slide overrides
- **VSE Rendering**: Pushes slides to Blender's Video Sequence Editor for preview and video export
- **Project Management**: Organized workspace with asset tracking, undo history, and auto-save
- **Undo Support**: Full undo stack for all slide mutations

## Architecture
- **SDK modules** (pure Python, no bpy): core data models, transcription, image search
- **Blender addon** (bpy): VSE rendering only, communicated via TCP socket
- **MCP server**: Exposes ~25 tools to Claude Desktop

## Limitations
- Whisper transcribes speech only - it does not generate slide titles (Claude fills those via edit_slide)
- Image search requires API keys (UNSPLASH_API_KEY, PEXELS_API_KEY, PIXABAY_API_KEY)
- Blender VSE has limited font support; uses Blender's built-in "Bfont" by default
- First-run whisper model download is ~150MB
- Video scraping (yt-dlp) is experimental and behind an optional dependency

## Project Structure
Projects are stored in `./projects/{name}/` with subdirectories for assets (images, audio, video, blender) and exports.
