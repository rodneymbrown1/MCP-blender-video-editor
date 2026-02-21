# Video Draft MCP - Style Guide

## Built-in Presets

### YouTube
Bold, high-contrast style optimized for YouTube video thumbnails and content.
- Font: Bfont, Title: 80px, Body: 40px
- Text color: #FFFFFF (white)
- Background: #0F0F0F (near-black)
- Alignment: center
- Padding: 50px

### Presentation
Clean, professional look suitable for business presentations and educational content.
- Font: Bfont, Title: 64px, Body: 32px
- Text color: #333333 (dark gray)
- Background: #F5F5F5 (light gray)
- Alignment: left
- Padding: 60px

### Cinematic
Minimal, dramatic style for cinematic intros, trailers, and atmospheric content.
- Font: Bfont, Title: 56px, Body: 28px
- Text color: #E0E0E0 (light gray)
- Background: #000000 (black)
- Alignment: center
- Padding: 80px

## Style Hierarchy

Styles are resolved in this order (later overrides earlier):
1. **Global defaults** — SlideStyleProps defaults
2. **Preset** — Applied via `set_global_style(preset="youtube")`
3. **Global custom** — Individual properties via `set_global_style(font_color="#FF0000")`
4. **Per-slide overrides** — Via `set_slide_style(slide_id, ...)`

## Supported Properties

| Property | Type | Default | Description |
|----------|------|---------|-------------|
| font_family | string | "Bfont" | Font family (Blender built-in or system font) |
| font_size_title | int | 72 | Title text size in pixels |
| font_size_body | int | 36 | Body text size in pixels |
| font_color | string | "#FFFFFF" | Hex color for all text |
| background_color | string | "#1A1A2E" | Hex color for slide background |
| text_alignment | string | "center" | Text alignment: left, center, right |
| padding | int | 40 | Padding from edges in pixels |

## Known-Working Fonts in Blender VSE

- **Bfont** (Blender's built-in font, always available)
- System fonts can be loaded but availability varies by OS
- For consistent results, stick with Bfont or bundle fonts in the project

## Color Format

All colors use hex format with `#` prefix:
- `#FFFFFF` — white
- `#000000` — black
- `#1A1A2E` — dark navy (default background)
- `#E0E0E0` — light gray
- `#FF6B6B` — coral red
- `#4ECDC4` — teal
