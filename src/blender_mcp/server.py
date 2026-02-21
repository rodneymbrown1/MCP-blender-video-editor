"""Video Draft MCP Server - MCP tools for video drafting through Claude Desktop."""

from mcp.server.fastmcp import FastMCP, Context, Image
import socket
import json
import asyncio
import logging
import tempfile
import uuid
from dataclasses import dataclass
from contextlib import asynccontextmanager
from typing import AsyncIterator, Dict, Any, Optional
import os
from pathlib import Path
import base64

# SDK imports
from sdk.core.frame import Slide, SlideCollection, SlideStyleProps
from sdk.core.workspace import Workspace, AssetMetadata
from sdk.core.state import SessionState, StylePreset, BUILTIN_PRESETS
from sdk.intake.audio import AudioTranscriber
from sdk.webscraping.images import ImageSearcher, ImageResult

# Configure logging
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("VideoDraftMCP")

# Default configuration
DEFAULT_HOST = "localhost"
DEFAULT_PORT = 9876
DEFAULT_PROJECTS_DIR = "./projects"


@dataclass
class BlenderConnection:
    host: str
    port: int
    sock: socket.socket = None

    def connect(self) -> bool:
        if self.sock:
            return True
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((self.host, self.port))
            logger.info(f"Connected to Blender at {self.host}:{self.port}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to Blender: {str(e)}")
            self.sock = None
            return False

    def disconnect(self):
        if self.sock:
            try:
                self.sock.close()
            except Exception as e:
                logger.error(f"Error disconnecting from Blender: {str(e)}")
            finally:
                self.sock = None

    def receive_full_response(self, sock, buffer_size=8192):
        chunks = []
        sock.settimeout(180.0)
        try:
            while True:
                try:
                    chunk = sock.recv(buffer_size)
                    if not chunk:
                        if not chunks:
                            raise Exception("Connection closed before receiving any data")
                        break
                    chunks.append(chunk)
                    try:
                        data = b''.join(chunks)
                        json.loads(data.decode('utf-8'))
                        return data
                    except json.JSONDecodeError:
                        continue
                except socket.timeout:
                    break
                except (ConnectionError, BrokenPipeError, ConnectionResetError) as e:
                    raise
        except socket.timeout:
            pass

        if chunks:
            data = b''.join(chunks)
            try:
                json.loads(data.decode('utf-8'))
                return data
            except json.JSONDecodeError:
                raise Exception("Incomplete JSON response received")
        raise Exception("No data received")

    def send_command(self, command_type: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        if not self.sock and not self.connect():
            raise ConnectionError("Not connected to Blender")

        command = {"type": command_type, "params": params or {}}
        try:
            self.sock.sendall(json.dumps(command).encode('utf-8'))
            self.sock.settimeout(180.0)
            response_data = self.receive_full_response(self.sock)
            response = json.loads(response_data.decode('utf-8'))

            if response.get("status") == "error":
                raise Exception(response.get("message", "Unknown error from Blender"))
            return response.get("result", {})
        except socket.timeout:
            self.sock = None
            raise Exception("Timeout waiting for Blender response")
        except (ConnectionError, BrokenPipeError, ConnectionResetError) as e:
            self.sock = None
            raise Exception(f"Connection to Blender lost: {str(e)}")
        except json.JSONDecodeError as e:
            raise Exception(f"Invalid response from Blender: {str(e)}")
        except Exception as e:
            self.sock = None
            raise Exception(f"Communication error with Blender: {str(e)}")


# ── Global State ────────────────────────────────────────────────────────

_blender_connection: Optional[BlenderConnection] = None
_session_state = SessionState()
_image_searcher = ImageSearcher()
_audio_transcriber: Optional[AudioTranscriber] = None


def get_blender_connection() -> BlenderConnection:
    global _blender_connection
    if _blender_connection is not None:
        try:
            _blender_connection.send_command("get_scene_info")
            return _blender_connection
        except Exception:
            try:
                _blender_connection.disconnect()
            except:
                pass
            _blender_connection = None

    host = os.getenv("BLENDER_HOST", DEFAULT_HOST)
    port = int(os.getenv("BLENDER_PORT", DEFAULT_PORT))
    _blender_connection = BlenderConnection(host=host, port=port)
    if not _blender_connection.connect():
        _blender_connection = None
        raise Exception("Could not connect to Blender. Make sure the Blender addon is running.")
    return _blender_connection


def _get_transcriber() -> AudioTranscriber:
    global _audio_transcriber
    if _audio_transcriber is None:
        _audio_transcriber = AudioTranscriber(model_size=_session_state.whisper_model_size)
    return _audio_transcriber


# ── Server Setup ────────────────────────────────────────────────────────

@asynccontextmanager
async def server_lifespan(server: FastMCP) -> AsyncIterator[Dict[str, Any]]:
    try:
        logger.info("VideoDraftMCP server starting up")
        try:
            blender = get_blender_connection()
            logger.info("Successfully connected to Blender on startup")
        except Exception as e:
            logger.warning(f"Could not connect to Blender on startup: {str(e)}")
            logger.warning("Blender connection is optional - SDK tools will work without it")
        yield {}
    finally:
        global _blender_connection
        if _blender_connection:
            _blender_connection.disconnect()
            _blender_connection = None
        logger.info("VideoDraftMCP server shut down")


mcp = FastMCP("VideoDraftMCP", lifespan=server_lifespan)


# ═══════════════════════════════════════════════════════════════════════
# PROJECT MANAGEMENT TOOLS
# ═══════════════════════════════════════════════════════════════════════

@mcp.tool()
def create_project(ctx: Context, project_name: str, base_path: str = "") -> str:
    """Create a new video draft project with standard directory structure.

    Parameters:
    - project_name: Name for the project (used as directory name)
    - base_path: Optional base directory (defaults to ./projects/)
    """
    global _session_state
    base = Path(base_path) if base_path else Path(DEFAULT_PROJECTS_DIR)
    project_path = base / project_name

    if project_path.exists():
        return f"Error: Project directory already exists at {project_path}"

    workspace = Workspace(project_name=project_name, root_path=project_path)
    workspace.initialize()

    _session_state = SessionState(workspace=workspace)
    _session_state.auto_save()

    return json.dumps({
        "status": "created",
        "project_name": project_name,
        "path": str(project_path),
        "directories": [
            "assets/images/", "assets/audio/", "assets/video/",
            "assets/blender/", "exports/"
        ],
    }, indent=2)


@mcp.tool()
def load_project(ctx: Context, project_path: str) -> str:
    """Load an existing video draft project.

    Parameters:
    - project_path: Path to the project directory
    """
    global _session_state
    try:
        workspace = Workspace.load(Path(project_path))
        _session_state = SessionState(workspace=workspace)
        _session_state.load_slides_from_workspace()

        return json.dumps({
            "status": "loaded",
            "project_name": workspace.project_name,
            "path": str(workspace.root_path),
            "asset_count": len(workspace.assets),
            "slide_count": len(_session_state.slides.slides),
        }, indent=2)
    except Exception as e:
        return f"Error loading project: {str(e)}"


@mcp.tool()
def save_project(ctx: Context) -> str:
    """Save the current project state (slides and manifest)."""
    if not _session_state.workspace:
        return "Error: No project is currently open. Use create_project or load_project first."

    _session_state.auto_save()
    _session_state.workspace.save_manifest()
    return f"Project '{_session_state.workspace.project_name}' saved successfully."


@mcp.tool()
def get_project_status(ctx: Context) -> str:
    """Get the current project status including slide count, assets, etc."""
    if not _session_state.workspace:
        return json.dumps({
            "project_loaded": False,
            "slide_count": len(_session_state.slides.slides),
            "message": "No project loaded. Use create_project or load_project.",
        }, indent=2)

    ws = _session_state.workspace
    return json.dumps({
        "project_loaded": True,
        "project_name": ws.project_name,
        "path": str(ws.root_path),
        "slide_count": len(_session_state.slides.slides),
        "asset_count": len(ws.assets),
        "assets_by_type": _count_assets_by_type(ws),
        "undo_depth": len(_session_state.undo_stack),
    }, indent=2)


def _count_assets_by_type(ws: Workspace) -> dict:
    counts: dict[str, int] = {}
    for asset in ws.assets.values():
        counts[asset.type] = counts.get(asset.type, 0) + 1
    return counts


# ═══════════════════════════════════════════════════════════════════════
# AUDIO TRANSCRIPTION TOOLS
# ═══════════════════════════════════════════════════════════════════════

@mcp.tool()
def transcribe_audio(ctx: Context, file_path: str, model_size: str = "base") -> str:
    """Transcribe an audio file and generate slides from the transcript.

    Parameters:
    - file_path: Path to the audio file (wav, mp3, m4a, etc.)
    - model_size: Whisper model size (tiny, base, small, medium, large-v3)
    """
    if not os.path.exists(file_path):
        return f"Error: File not found: {file_path}"

    try:
        transcriber = _get_transcriber()
        transcript = transcriber.transcribe(file_path, model_size=model_size)

        # Cache the raw transcript
        _session_state.transcript_cache = json.dumps(transcript, indent=2)

        # Generate slides
        _session_state.checkpoint("Before transcription")
        slides = transcriber.segments_to_slides(transcript)
        _session_state.slides = slides
        _session_state.auto_save()

        # Copy audio to project if workspace exists
        if _session_state.workspace:
            import shutil
            audio_dest = _session_state.workspace.audio_dir / Path(file_path).name
            if not audio_dest.exists():
                shutil.copy2(file_path, audio_dest)
            _session_state.workspace.register_asset(AssetMetadata(
                asset_id=f"audio_{uuid.uuid4().hex[:8]}",
                filename=Path(file_path).name,
                type="audio",
                source="local",
            ))

        return json.dumps({
            "status": "success",
            "language": transcript.get("language", "unknown"),
            "duration": f"{transcript.get('duration', 0):.1f}s",
            "segment_count": len(transcript.get("segments", [])),
            "slide_count": len(slides.slides),
            "slides_summary": slides.to_summary(),
        }, indent=2)
    except Exception as e:
        logger.error(f"Transcription error: {str(e)}")
        return f"Error during transcription: {str(e)}"


@mcp.tool()
def get_transcript(ctx: Context) -> str:
    """Get the raw timestamped transcript from the last transcription."""
    if not _session_state.transcript_cache:
        return "No transcript available. Use transcribe_audio first."
    return _session_state.transcript_cache


# ═══════════════════════════════════════════════════════════════════════
# SLIDE CRUD TOOLS
# ═══════════════════════════════════════════════════════════════════════

@mcp.tool()
def get_slides(ctx: Context) -> str:
    """List all slides with their IDs, time ranges, and title snippets."""
    slides = _session_state.slides
    if not slides.slides:
        return "No slides yet. Use transcribe_audio to generate slides from audio."
    return json.dumps(slides.to_summary(), indent=2)


@mcp.tool()
def get_slide(ctx: Context, slide_id: str) -> str:
    """Get full details of a specific slide.

    Parameters:
    - slide_id: The ID of the slide to retrieve
    """
    slide = _session_state.slides.get(slide_id)
    if not slide:
        return f"Error: Slide '{slide_id}' not found."
    return json.dumps(slide.model_dump(), indent=2)


@mcp.tool()
def edit_slide(ctx: Context, slide_id: str, title: str = None,
               body: str = None, speaker_notes: str = None) -> str:
    """Edit a slide's title, body text, or speaker notes.

    Parameters:
    - slide_id: The ID of the slide to edit
    - title: New title (optional)
    - body: New body text (optional)
    - speaker_notes: New speaker notes (optional)
    """
    slide = _session_state.slides.get(slide_id)
    if not slide:
        return f"Error: Slide '{slide_id}' not found."

    _session_state.checkpoint(f"Edit slide {slide_id}")

    if title is not None:
        slide.title = title
    if body is not None:
        slide.body_text = body
    if speaker_notes is not None:
        slide.speaker_notes = speaker_notes

    _session_state.auto_save()
    return json.dumps({
        "status": "updated",
        "slide": slide.model_dump(),
    }, indent=2)


@mcp.tool()
def split_slide(ctx: Context, slide_id: str, at_time: float) -> str:
    """Split a slide into two at a specific timestamp.

    Parameters:
    - slide_id: The ID of the slide to split
    - at_time: The timestamp (in seconds) at which to split
    """
    _session_state.checkpoint(f"Split slide {slide_id} at {at_time}s")

    result = _session_state.slides.split(slide_id, at_time)
    if not result:
        return f"Error: Could not split slide '{slide_id}' at {at_time}s. Check that the time is within the slide's range."

    s1, s2 = result
    _session_state.auto_save()
    return json.dumps({
        "status": "split",
        "slide_1": s1.model_dump(),
        "slide_2": s2.model_dump(),
    }, indent=2)


@mcp.tool()
def merge_slides(ctx: Context, slide_id_1: str, slide_id_2: str) -> str:
    """Merge two slides into one (combines text, extends time range).

    Parameters:
    - slide_id_1: First slide ID
    - slide_id_2: Second slide ID
    """
    _session_state.checkpoint(f"Merge slides {slide_id_1} + {slide_id_2}")

    result = _session_state.slides.merge(slide_id_1, slide_id_2)
    if not result:
        return f"Error: Could not merge slides '{slide_id_1}' and '{slide_id_2}'."

    _session_state.auto_save()
    return json.dumps({
        "status": "merged",
        "slide": result.model_dump(),
    }, indent=2)


@mcp.tool()
def remove_slide(ctx: Context, slide_id: str) -> str:
    """Remove a slide from the collection.

    Parameters:
    - slide_id: The ID of the slide to remove
    """
    _session_state.checkpoint(f"Remove slide {slide_id}")

    if _session_state.slides.remove(slide_id):
        _session_state.auto_save()
        return f"Slide '{slide_id}' removed. {len(_session_state.slides.slides)} slides remaining."
    return f"Error: Slide '{slide_id}' not found."


@mcp.tool()
def reorder_slides(ctx: Context, slide_id_list: list[str]) -> str:
    """Reorder slides by providing the complete list of slide IDs in desired order.

    Parameters:
    - slide_id_list: List of all slide IDs in the new order
    """
    _session_state.checkpoint("Reorder slides")

    if _session_state.slides.reorder(slide_id_list):
        _session_state.auto_save()
        return json.dumps({
            "status": "reordered",
            "slides": _session_state.slides.to_summary(),
        }, indent=2)
    return "Error: The provided slide ID list doesn't match the current slides."


# ═══════════════════════════════════════════════════════════════════════
# STYLE TOOLS
# ═══════════════════════════════════════════════════════════════════════

@mcp.tool()
def set_global_style(ctx: Context, preset: str = None,
                     font_family: str = None, font_size_title: int = None,
                     font_size_body: int = None, font_color: str = None,
                     background_color: str = None, text_alignment: str = None,
                     padding: int = None) -> str:
    """Set the global style for all slides. Can use a preset or individual properties.

    Parameters:
    - preset: Named preset (youtube, presentation, cinematic)
    - font_family: Font family name
    - font_size_title: Title font size in pixels
    - font_size_body: Body font size in pixels
    - font_color: Hex color for text (e.g. "#FFFFFF")
    - background_color: Hex color for background (e.g. "#1A1A2E")
    - text_alignment: Text alignment (left, center, right)
    - padding: Padding in pixels
    """
    _session_state.checkpoint("Change global style")

    style = _session_state.slides.global_style

    if preset:
        p = _session_state.get_preset(preset)
        if not p:
            available = ", ".join(BUILTIN_PRESETS.keys())
            return f"Error: Unknown preset '{preset}'. Available: {available}"
        _session_state.slides.global_style = p.style.model_copy()
        style = _session_state.slides.global_style

    # Apply individual overrides on top of preset
    if font_family is not None:
        style.font_family = font_family
    if font_size_title is not None:
        style.font_size_title = font_size_title
    if font_size_body is not None:
        style.font_size_body = font_size_body
    if font_color is not None:
        style.font_color = font_color
    if background_color is not None:
        style.background_color = background_color
    if text_alignment is not None:
        style.text_alignment = text_alignment
    if padding is not None:
        style.padding = padding

    _session_state.auto_save()
    return json.dumps({
        "status": "updated",
        "global_style": style.model_dump(),
        "available_presets": _session_state.list_presets(),
    }, indent=2)


@mcp.tool()
def set_slide_style(ctx: Context, slide_id: str,
                    font_family: str = None, font_size_title: int = None,
                    font_size_body: int = None, font_color: str = None,
                    background_color: str = None, text_alignment: str = None,
                    padding: int = None) -> str:
    """Set style overrides for a specific slide.

    Parameters:
    - slide_id: The slide to style
    - (same style properties as set_global_style)
    """
    slide = _session_state.slides.get(slide_id)
    if not slide:
        return f"Error: Slide '{slide_id}' not found."

    _session_state.checkpoint(f"Style slide {slide_id}")

    if not slide.style_overrides:
        slide.style_overrides = _session_state.slides.global_style.model_copy()

    s = slide.style_overrides
    if font_family is not None:
        s.font_family = font_family
    if font_size_title is not None:
        s.font_size_title = font_size_title
    if font_size_body is not None:
        s.font_size_body = font_size_body
    if font_color is not None:
        s.font_color = font_color
    if background_color is not None:
        s.background_color = background_color
    if text_alignment is not None:
        s.text_alignment = text_alignment
    if padding is not None:
        s.padding = padding

    _session_state.auto_save()
    return json.dumps({
        "status": "updated",
        "slide_id": slide_id,
        "style_overrides": s.model_dump(),
    }, indent=2)


@mcp.tool()
def undo(ctx: Context) -> str:
    """Undo the last slide mutation."""
    description = _session_state.undo()
    if description:
        _session_state.auto_save()
        return f"Undone: {description}. Slide count: {len(_session_state.slides.slides)}"
    return "Nothing to undo."


# ═══════════════════════════════════════════════════════════════════════
# IMAGE SEARCH & DOWNLOAD TOOLS
# ═══════════════════════════════════════════════════════════════════════

@mcp.tool()
def search_images(ctx: Context, query: str, count: int = 5,
                  orientation: str = "landscape") -> str:
    """Search for free images across Unsplash, Pexels, and Pixabay.

    Parameters:
    - query: Search query
    - count: Number of results (default 5)
    - orientation: Image orientation (landscape, portrait, squarish)
    """
    try:
        results = _image_searcher.search(query, count=count, orientation=orientation)
        if not results:
            status = _image_searcher.get_source_status()
            configured = [k for k, v in status.items() if v["configured"]]
            if not configured:
                return ("No image sources configured. Set API keys via environment variables: "
                        "UNSPLASH_API_KEY, PEXELS_API_KEY, PIXABAY_API_KEY")
            return f"No results found for '{query}'"

        return json.dumps([{
            "id": r.id,
            "source": r.source,
            "preview_url": r.preview_url,
            "download_url": r.download_url,
            "width": r.width,
            "height": r.height,
            "photographer": r.photographer,
            "license": r.license,
        } for r in results], indent=2)
    except Exception as e:
        return f"Error searching images: {str(e)}"


@mcp.tool()
def download_image(ctx: Context, url: str, slide_id: str = None) -> str:
    """Download an image and optionally attach it to a slide as background.

    Parameters:
    - url: URL of the image to download
    - slide_id: Optional slide ID to attach as background
    """
    if not _session_state.workspace:
        return "Error: No project open. Use create_project first."

    try:
        dest_path = _image_searcher.download(
            url, _session_state.workspace.images_dir
        )

        # Register asset
        asset_id = f"img_{uuid.uuid4().hex[:8]}"
        asset = AssetMetadata(
            asset_id=asset_id,
            filename=dest_path.name,
            type="image",
            source="download",
        )
        _session_state.workspace.register_asset(asset)

        # Attach to slide if specified
        if slide_id:
            slide = _session_state.slides.get(slide_id)
            if slide:
                _session_state.checkpoint(f"Set background for slide {slide_id}")
                slide.background_image_ref = str(dest_path)
                _session_state.auto_save()

        return json.dumps({
            "status": "downloaded",
            "asset_id": asset_id,
            "path": str(dest_path),
            "attached_to_slide": slide_id,
        }, indent=2)
    except Exception as e:
        return f"Error downloading image: {str(e)}"


@mcp.tool()
def set_slide_background(ctx: Context, slide_id: str, asset_id: str) -> str:
    """Set a downloaded image as a slide's background.

    Parameters:
    - slide_id: The slide to update
    - asset_id: The asset ID of the downloaded image
    """
    slide = _session_state.slides.get(slide_id)
    if not slide:
        return f"Error: Slide '{slide_id}' not found."

    if not _session_state.workspace:
        return "Error: No project open."

    asset_path = _session_state.workspace.get_asset_path(asset_id)
    if not asset_path:
        return f"Error: Asset '{asset_id}' not found."

    _session_state.checkpoint(f"Set background for slide {slide_id}")
    slide.background_image_ref = str(asset_path)
    _session_state.auto_save()

    return json.dumps({
        "status": "updated",
        "slide_id": slide_id,
        "background": str(asset_path),
    }, indent=2)


@mcp.tool()
def scan_titles_for_images(ctx: Context, count_per_slide: int = 3) -> str:
    """Batch-search images for all slide titles. Returns suggestions per slide.

    Parameters:
    - count_per_slide: Number of image results per slide (default 3)
    """
    slides = _session_state.slides.slides
    if not slides:
        return "No slides to scan. Use transcribe_audio first."

    results = {}
    for slide in slides:
        query = slide.title if slide.title else slide.body_text[:50]
        if not query.strip():
            continue
        try:
            images = _image_searcher.search(query, count=count_per_slide)
            results[slide.id] = {
                "query": query,
                "results": [{
                    "id": r.id,
                    "source": r.source,
                    "preview_url": r.preview_url,
                    "download_url": r.download_url,
                    "photographer": r.photographer,
                } for r in images],
            }
        except Exception as e:
            results[slide.id] = {"query": query, "error": str(e)}

    return json.dumps(results, indent=2)


@mcp.tool()
def list_assets(ctx: Context) -> str:
    """List all assets in the current project workspace."""
    if not _session_state.workspace:
        return "Error: No project open. Use create_project first."

    assets = _session_state.workspace.assets
    if not assets:
        return "No assets registered yet."

    return json.dumps([{
        "asset_id": a.asset_id,
        "filename": a.filename,
        "type": a.type,
        "source": a.source,
    } for a in assets.values()], indent=2)


@mcp.tool()
def get_image_source_status(ctx: Context) -> str:
    """Check which image API sources are configured and their rate limit status."""
    return json.dumps(_image_searcher.get_source_status(), indent=2)


# ═══════════════════════════════════════════════════════════════════════
# BLENDER TOOLS (kept from original)
# ═══════════════════════════════════════════════════════════════════════

@mcp.tool()
def get_scene_info(ctx: Context) -> str:
    """Get detailed information about the current Blender scene."""
    try:
        blender = get_blender_connection()
        result = blender.send_command("get_scene_info")
        return json.dumps(result, indent=2)
    except Exception as e:
        return f"Error getting scene info: {str(e)}"


@mcp.tool()
def get_object_info(ctx: Context, object_name: str) -> str:
    """Get detailed information about a specific object in the Blender scene.

    Parameters:
    - object_name: The name of the object to get information about
    """
    try:
        blender = get_blender_connection()
        result = blender.send_command("get_object_info", {"name": object_name})
        return json.dumps(result, indent=2)
    except Exception as e:
        return f"Error getting object info: {str(e)}"


@mcp.tool()
def get_viewport_screenshot(ctx: Context, max_size: int = 800) -> Image:
    """Capture a screenshot of the current Blender 3D viewport.

    Parameters:
    - max_size: Maximum size in pixels for the largest dimension (default: 800)
    """
    try:
        blender = get_blender_connection()
        temp_dir = tempfile.gettempdir()
        temp_path = os.path.join(temp_dir, f"blender_screenshot_{os.getpid()}.png")

        result = blender.send_command("get_viewport_screenshot", {
            "max_size": max_size,
            "filepath": temp_path,
            "format": "png",
        })

        if "error" in result:
            raise Exception(result["error"])
        if not os.path.exists(temp_path):
            raise Exception("Screenshot file was not created")

        with open(temp_path, 'rb') as f:
            image_bytes = f.read()
        os.remove(temp_path)

        return Image(data=image_bytes, format="png")
    except Exception as e:
        raise Exception(f"Screenshot failed: {str(e)}")


@mcp.tool()
def execute_blender_code(ctx: Context, code: str) -> str:
    """Execute arbitrary Python code in Blender.

    Parameters:
    - code: The Python code to execute
    """
    try:
        blender = get_blender_connection()
        result = blender.send_command("execute_code", {"code": code})
        return f"Code executed successfully: {result.get('result', '')}"
    except Exception as e:
        return f"Error executing code: {str(e)}"


# ═══════════════════════════════════════════════════════════════════════
# VSE RENDERING TOOLS
# ═══════════════════════════════════════════════════════════════════════

@mcp.tool()
def render_slides_to_blender(ctx: Context) -> str:
    """Push current slides to Blender's Video Sequence Editor for rendering."""
    slides = _session_state.slides
    if not slides.slides:
        return "No slides to render. Use transcribe_audio first."

    try:
        blender = get_blender_connection()
        slides_data = slides.model_dump()

        audio_path = None
        if _session_state.workspace:
            # Find audio file in workspace
            for asset in _session_state.workspace.assets.values():
                if asset.type == "audio":
                    ap = _session_state.workspace.get_asset_path(asset.asset_id)
                    if ap and ap.exists():
                        audio_path = str(ap)
                        break

        result = blender.send_command("render_slides_to_vse", {
            "slides_json": json.dumps(slides_data),
            "audio_path": audio_path,
        })

        return json.dumps(result, indent=2)
    except Exception as e:
        return f"Error rendering to Blender: {str(e)}"


@mcp.tool()
def render_preview_frame(ctx: Context, slide_id: str) -> Image:
    """Render a preview frame of a specific slide from the VSE.

    Parameters:
    - slide_id: The slide to preview
    """
    slide = _session_state.slides.get(slide_id)
    if not slide:
        raise Exception(f"Slide '{slide_id}' not found.")

    try:
        blender = get_blender_connection()

        # Calculate frame number from slide's start time (assume 30fps)
        frame_number = int(slide.start_time * 30) + 1
        temp_path = os.path.join(tempfile.gettempdir(), f"preview_{slide_id}.png")

        result = blender.send_command("render_preview_frame", {
            "frame_number": frame_number,
            "filepath": temp_path,
        })

        if "error" in result:
            raise Exception(result["error"])

        with open(temp_path, 'rb') as f:
            image_bytes = f.read()
        os.remove(temp_path)

        return Image(data=image_bytes, format="png")
    except Exception as e:
        raise Exception(f"Preview render failed: {str(e)}")


@mcp.tool()
def export_video(ctx: Context, output_path: str = None, format: str = "MPEG4") -> str:
    """Export the VSE timeline as a video file.

    Parameters:
    - output_path: Output file path (defaults to project exports dir)
    - format: Video format (MPEG4, AVI, etc.)
    """
    if not output_path:
        if _session_state.workspace:
            output_path = str(
                _session_state.workspace.exports_dir /
                f"{_session_state.workspace.project_name}.mp4"
            )
        else:
            output_path = os.path.join(tempfile.gettempdir(), "video_draft_export.mp4")

    try:
        blender = get_blender_connection()
        result = blender.send_command("export_video", {
            "output_path": output_path,
            "format": format,
        })
        return json.dumps(result, indent=2)
    except Exception as e:
        return f"Error exporting video: {str(e)}"


# ═══════════════════════════════════════════════════════════════════════
# MCP PROMPT
# ═══════════════════════════════════════════════════════════════════════

@mcp.prompt()
def video_draft_workflow() -> str:
    """Recommended workflow for creating a video draft"""
    return """You are helping the user create a video draft. Follow this workflow:

1. **Create Project**: Use create_project() to set up a new project workspace.

2. **Transcribe Audio**: Use transcribe_audio() with the user's audio file.
   This will auto-generate slides from the speech with timestamps.

3. **Review & Edit Slides**: Use get_slides() to see all slides, then:
   - Use edit_slide() to add titles and refine body text
   - Use split_slide() or merge_slides() to adjust slide boundaries
   - Use remove_slide() for unwanted content

4. **Search & Add Images**: Use search_images() to find background images.
   - Use scan_titles_for_images() for batch suggestions
   - Use download_image() to save images and attach to slides
   - Use set_slide_background() to assign images

5. **Style**: Use set_global_style() with a preset (youtube, presentation, cinematic)
   or custom properties. Use set_slide_style() for per-slide overrides.

6. **Render**: Use render_slides_to_blender() to push to Blender's VSE.
   - Use render_preview_frame() to preview individual slides
   - Use export_video() to render the final video

Tips:
- Whisper generates body text only - use edit_slide() to add descriptive titles
- Use undo() if you make a mistake
- Use save_project() periodically to persist state
- Use get_project_status() to check overall progress
- Check get_image_source_status() to see which image APIs are configured
"""


# ── Main ────────────────────────────────────────────────────────────────

def main():
    """Run the MCP server"""
    mcp.run()


if __name__ == "__main__":
    main()
