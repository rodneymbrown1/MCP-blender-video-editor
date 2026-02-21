# Video Draft MCP

Video Draft MCP is a video editing assistant SDK built on top of [BlenderMCP](https://github.com/ahujasid/blender-mcp). It connects to Claude through the [Model Context Protocol](https://modelcontextprotocol.io/) and uses Blender's Video Sequence Editor (VSE) for rendering.

The flagship feature: give it audio from a recorded script and it scaffolds your entire video. Titles, slides, topic segmentation, background images — all generated automatically from your voice using OpenAI Whisper (fully offline). You review and refine through conversation instead of clicking through timelines.

This doesn't replace video editing. It bootstraps it. And because it sits on top of the full BlenderMCP connection, you can still get creative with 3D effects, scene composition, and anything else Blender can do.

## Forked From

This project is forked from [BlenderMCP](https://github.com/ahujasid/blender-mcp) by [@ahujasid](https://github.com/ahujasid):

> BlenderMCP connects Blender to Claude AI through the Model Context Protocol (MCP), allowing Claude to directly interact with and control Blender. This integration enables prompt assisted 3D modeling, scene creation, and manipulation.
>
> We have no official website. Any website you see online is unofficial and has no affiliation with this project. Use them at your own risk.

This fork retains the core Blender socket connection and adds the Video Draft SDK on top of it.

## How It Works

```
You record audio (podcast, script, lecture, etc.)
        |
        v
Whisper transcribes it offline (word-level timestamps)
        |
        v
SDK groups transcript into slides (pause detection, sentence boundaries)
        |
        v
Claude helps you title slides, pick images, set styles
        |
        v
Blender VSE renders the final video
```

1. **Transcribe** — Whisper runs locally via [faster-whisper](https://github.com/SYSTRAN/faster-whisper) (CTranslate2, CPU int8). No API calls, no uploads. It detects pauses and sentence boundaries to automatically segment your audio into slides.

2. **Edit** — Claude sees all your slides and helps you refine them. Add titles, rewrite body text, split or merge slides, reorder sections. Every change is tracked with an undo stack.

3. **Style** — Apply built-in presets (youtube, presentation, cinematic) or set custom fonts, colors, and alignment. Global styles with per-slide overrides.

4. **Image Search** — Search Unsplash, Pexels, and Pixabay for background images. Download and attach to slides directly through conversation. Rate-limited and cached.

5. **Render** — Push slides to Blender's VSE. Preview individual frames or export the full video as MP4.

## What Works Today

| Feature | Status |
|---------|--------|
| Audio transcription (Whisper) | Working |
| Slide generation from transcript | Working |
| Slide editing (CRUD, split, merge, reorder) | Working |
| Style presets and customization | Working |
| Image search and download | Working (requires API keys) |
| Blender VSE rendering | Working (requires Blender addon) |
| Project management and persistence | Working |
| Undo/redo | Working |

## Roadmap

- **Web scraping testing** — Image search APIs need real-world testing across sources
- **Animations and effects** — Slide transitions, text animations, and 3D overlays via Blender
- **Video scraping** — yt-dlp integration for Creative Commons footage (stubbed)
- **Audio/SFX sourcing** — freesound.org integration for background music (stubbed)

## Installation

### Prerequisites

- Python 3.10+
- [uv](https://docs.astral.sh/uv/) (recommended) or pip
- [Blender](https://www.blender.org/) 3.0+ (for VSE rendering — SDK tools work without it)

### Install

```bash
git clone https://github.com/yourusername/video-draft-mcp.git
cd video-draft-mcp
uv sync
```

### Claude Desktop

Add to your Claude Desktop config (`~/Library/Application Support/Claude/claude_desktop_config.json` on macOS):

```json
{
  "mcpServers": {
    "video-draft-mcp": {
      "command": "uv",
      "args": [
        "--directory",
        "/ABSOLUTE/PATH/TO/video-draft-mcp",
        "run",
        "video-draft-mcp"
      ]
    }
  }
}
```

### Claude Code

```bash
claude mcp add video-draft-mcp -- uv --directory /ABSOLUTE/PATH/TO/video-draft-mcp run video-draft-mcp
```

### Blender Addon

1. Open Blender
2. Edit > Preferences > Add-ons > Install
3. Select `addon.py` from this repo
4. Enable "VideoDraftMCP"
5. In the 3D Viewport sidebar, open the VideoDraftMCP panel and click Connect

The addon runs a socket server on `localhost:9876`. The MCP server connects to it automatically when Blender is running.

## Image Search Setup

Image search uses free API tiers. Set any combination of these environment variables:

| Variable | Source | Free Tier |
|----------|--------|-----------|
| `UNSPLASH_API_KEY` | [Unsplash Developers](https://unsplash.com/developers) | 50 requests/hour |
| `PEXELS_API_KEY` | [Pexels API](https://www.pexels.com/api/) | 200 requests/hour |
| `PIXABAY_API_KEY` | [Pixabay API](https://pixabay.com/api/docs/) | 100 requests/minute |

All three are optional. The SDK rotates through whichever sources are configured.

## Example Workflow

```
You: Create a project called "ml-talk"

You: Transcribe this audio /path/to/recording.wav

Claude: Found 8 slides from your 4-minute recording. Here's a summary...

You: Can you add titles to each slide based on the content?

You: Search for background images for each slide

You: Apply the youtube style preset

You: Render it to Blender and export as mp4
```

## Architecture

```
src/
  sdk/
    core/
      frame.py        # Slide data models (Pydantic)
      workspace.py    # Project directory and asset management
      state.py        # Session state, undo stack, style presets
    intake/
      audio.py        # faster-whisper transcription
    webscraping/
      images.py       # Unsplash/Pexels/Pixabay search
  blender_mcp/
    server.py         # MCP server (29 tools)
addon.py              # Blender addon (VSE rendering, socket server)
```

The SDK is pure Python — no Blender dependency. Blender is only used for final rendering through the addon's socket connection.

## Running Tests

```bash
uv run pytest
```

Tests cover slide models, workspace management, session state, audio transcription (with real Whisper model), and image search (mocked APIs). The e2e audio tests use a WAV fixture and run actual transcription.

## License

MIT
