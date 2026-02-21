"""Video Draft MCP - Blender Addon for VSE rendering."""

import bpy
import mathutils
import json
import threading
import socket
import time
import traceback
import os
import io
from bpy.props import IntProperty
from contextlib import redirect_stdout

bl_info = {
    "name": "Video Draft MCP",
    "author": "VideoDraftMCP",
    "version": (0, 1),
    "blender": (3, 0, 0),
    "location": "View3D > Sidebar > VideoDraftMCP",
    "description": "Connect Blender to Claude for video drafting via MCP",
    "category": "Interface",
}


class BlenderMCPServer:
    def __init__(self, host='localhost', port=9876):
        self.host = host
        self.port = port
        self.running = False
        self.socket = None
        self.server_thread = None

    def start(self):
        if self.running:
            print("Server is already running")
            return

        self.running = True

        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.socket.bind((self.host, self.port))
            self.socket.listen(1)

            self.server_thread = threading.Thread(target=self._server_loop)
            self.server_thread.daemon = True
            self.server_thread.start()

            print(f"VideoDraftMCP server started on {self.host}:{self.port}")
        except Exception as e:
            print(f"Failed to start server: {str(e)}")
            self.stop()

    def stop(self):
        self.running = False

        if self.socket:
            try:
                self.socket.close()
            except:
                pass
            self.socket = None

        if self.server_thread:
            try:
                if self.server_thread.is_alive():
                    self.server_thread.join(timeout=1.0)
            except:
                pass
            self.server_thread = None

        print("VideoDraftMCP server stopped")

    def _server_loop(self):
        """Main server loop in a separate thread"""
        print("Server thread started")
        self.socket.settimeout(1.0)

        while self.running:
            try:
                try:
                    client, address = self.socket.accept()
                    print(f"Connected to client: {address}")

                    client_thread = threading.Thread(
                        target=self._handle_client,
                        args=(client,)
                    )
                    client_thread.daemon = True
                    client_thread.start()
                except socket.timeout:
                    continue
                except Exception as e:
                    print(f"Error accepting connection: {str(e)}")
                    time.sleep(0.5)
            except Exception as e:
                print(f"Error in server loop: {str(e)}")
                if not self.running:
                    break
                time.sleep(0.5)

        print("Server thread stopped")

    def _handle_client(self, client):
        """Handle connected client"""
        print("Client handler started")
        client.settimeout(None)
        buffer = b''

        try:
            while self.running:
                try:
                    data = client.recv(8192)
                    if not data:
                        print("Client disconnected")
                        break

                    buffer += data
                    try:
                        command = json.loads(buffer.decode('utf-8'))
                        buffer = b''

                        def execute_wrapper():
                            try:
                                response = self.execute_command(command)
                                response_json = json.dumps(response)
                                try:
                                    client.sendall(response_json.encode('utf-8'))
                                except:
                                    print("Failed to send response - client disconnected")
                            except Exception as e:
                                print(f"Error executing command: {str(e)}")
                                traceback.print_exc()
                                try:
                                    error_response = {
                                        "status": "error",
                                        "message": str(e)
                                    }
                                    client.sendall(json.dumps(error_response).encode('utf-8'))
                                except:
                                    pass
                            return None

                        bpy.app.timers.register(execute_wrapper, first_interval=0.0)
                    except json.JSONDecodeError:
                        pass
                except Exception as e:
                    print(f"Error receiving data: {str(e)}")
                    break
        except Exception as e:
            print(f"Error in client handler: {str(e)}")
        finally:
            try:
                client.close()
            except:
                pass
            print("Client handler stopped")

    def execute_command(self, command):
        """Execute a command in the main Blender thread"""
        try:
            return self._execute_command_internal(command)
        except Exception as e:
            print(f"Error executing command: {str(e)}")
            traceback.print_exc()
            return {"status": "error", "message": str(e)}

    def _execute_command_internal(self, command):
        """Internal command execution with proper context"""
        cmd_type = command.get("type")
        params = command.get("params", {})

        handlers = {
            "get_scene_info": self.get_scene_info,
            "get_object_info": self.get_object_info,
            "get_viewport_screenshot": self.get_viewport_screenshot,
            "execute_code": self.execute_code,
            # VSE rendering handlers
            "render_slides_to_vse": self.render_slides_to_vse,
            "render_preview_frame": self.render_preview_frame,
            "export_video": self.export_video,
            "set_vse_audio": self.set_vse_audio,
        }

        handler = handlers.get(cmd_type)
        if handler:
            try:
                print(f"Executing handler for {cmd_type}")
                result = handler(**params)
                print(f"Handler execution complete")
                return {"status": "success", "result": result}
            except Exception as e:
                print(f"Error in handler: {str(e)}")
                traceback.print_exc()
                return {"status": "error", "message": str(e)}
        else:
            return {"status": "error", "message": f"Unknown command type: {cmd_type}"}

    def get_scene_info(self):
        """Get information about the current Blender scene"""
        try:
            print("Getting scene info...")
            scene_info = {
                "name": bpy.context.scene.name,
                "object_count": len(bpy.context.scene.objects),
                "objects": [],
                "materials_count": len(bpy.data.materials),
            }

            for i, obj in enumerate(bpy.context.scene.objects):
                if i >= 10:
                    break
                obj_info = {
                    "name": obj.name,
                    "type": obj.type,
                    "location": [round(float(obj.location.x), 2),
                                round(float(obj.location.y), 2),
                                round(float(obj.location.z), 2)],
                }
                scene_info["objects"].append(obj_info)

            print(f"Scene info collected: {len(scene_info['objects'])} objects")
            return scene_info
        except Exception as e:
            print(f"Error in get_scene_info: {str(e)}")
            traceback.print_exc()
            return {"error": str(e)}

    @staticmethod
    def _get_aabb(obj):
        """Returns the world-space axis-aligned bounding box (AABB) of an object."""
        if obj.type != 'MESH':
            raise TypeError("Object must be a mesh")

        local_bbox_corners = [mathutils.Vector(corner) for corner in obj.bound_box]
        world_bbox_corners = [obj.matrix_world @ corner for corner in local_bbox_corners]
        min_corner = mathutils.Vector(map(min, zip(*world_bbox_corners)))
        max_corner = mathutils.Vector(map(max, zip(*world_bbox_corners)))
        return [[*min_corner], [*max_corner]]

    def get_object_info(self, name):
        """Get detailed information about a specific object"""
        obj = bpy.data.objects.get(name)
        if not obj:
            raise ValueError(f"Object not found: {name}")

        obj_info = {
            "name": obj.name,
            "type": obj.type,
            "location": [obj.location.x, obj.location.y, obj.location.z],
            "rotation": [obj.rotation_euler.x, obj.rotation_euler.y, obj.rotation_euler.z],
            "scale": [obj.scale.x, obj.scale.y, obj.scale.z],
            "visible": obj.visible_get(),
            "materials": [],
        }

        if obj.type == "MESH":
            bounding_box = self._get_aabb(obj)
            obj_info["world_bounding_box"] = bounding_box

        for slot in obj.material_slots:
            if slot.material:
                obj_info["materials"].append(slot.material.name)

        if obj.type == 'MESH' and obj.data:
            mesh = obj.data
            obj_info["mesh"] = {
                "vertices": len(mesh.vertices),
                "edges": len(mesh.edges),
                "polygons": len(mesh.polygons),
            }

        return obj_info

    def get_viewport_screenshot(self, max_size=800, filepath=None, format="png"):
        """Capture a screenshot of the current 3D viewport"""
        try:
            if not filepath:
                return {"error": "No filepath provided"}

            area = None
            for a in bpy.context.screen.areas:
                if a.type == 'VIEW_3D':
                    area = a
                    break

            if not area:
                return {"error": "No 3D viewport found"}

            with bpy.context.temp_override(area=area):
                bpy.ops.screen.screenshot_area(filepath=filepath)

            img = bpy.data.images.load(filepath)
            width, height = img.size

            if max(width, height) > max_size:
                scale = max_size / max(width, height)
                new_width = int(width * scale)
                new_height = int(height * scale)
                img.scale(new_width, new_height)
                img.file_format = format.upper()
                img.save()
                width, height = new_width, new_height

            bpy.data.images.remove(img)

            return {
                "success": True,
                "width": width,
                "height": height,
                "filepath": filepath,
            }
        except Exception as e:
            return {"error": str(e)}

    def execute_code(self, code):
        """Execute arbitrary Blender Python code"""
        try:
            namespace = {"bpy": bpy}
            capture_buffer = io.StringIO()
            with redirect_stdout(capture_buffer):
                exec(code, namespace)

            captured_output = capture_buffer.getvalue()
            return {"executed": True, "result": captured_output}
        except Exception as e:
            raise Exception(f"Code execution error: {str(e)}")

    # ── VSE Rendering Handlers ──────────────────────────────────────────

    def render_slides_to_vse(self, slides_json, audio_path=None, fps=30,
                             resolution_x=1920, resolution_y=1080):
        """Render slides into Blender's Video Sequence Editor."""
        try:
            slides = json.loads(slides_json) if isinstance(slides_json, str) else slides_json

            scene = bpy.context.scene
            scene.render.resolution_x = resolution_x
            scene.render.resolution_y = resolution_y
            scene.render.fps = fps

            # Ensure we have a sequencer
            if not scene.sequence_editor:
                scene.sequence_editor_create()
            seq_editor = scene.sequence_editor

            # Clear existing strips
            for strip in list(seq_editor.sequences_all):
                seq_editor.sequences.remove(strip)

            global_style = slides.get("global_style", {})
            slide_list = slides.get("slides", [])

            if not slide_list:
                return {"success": True, "message": "No slides to render", "strip_count": 0}

            # Calculate total frame range
            max_end_time = max(s.get("end_time", 0) for s in slide_list)
            scene.frame_start = 1
            scene.frame_end = int(max_end_time * fps) + 1

            channel_bg = 1
            channel_title = 2
            channel_body = 3
            strip_count = 0

            for slide in slide_list:
                start_frame = int(slide.get("start_time", 0) * fps) + 1
                end_frame = int(slide.get("end_time", 0) * fps) + 1
                duration = max(end_frame - start_frame, 1)

                style = dict(global_style)
                if slide.get("style_overrides"):
                    style.update(slide["style_overrides"])

                bg_color = style.get("background_color", "#1A1A2E")

                # Background image or color strip
                bg_ref = slide.get("background_image_ref")
                if bg_ref and os.path.exists(bg_ref):
                    strip = seq_editor.sequences.new_image(
                        name=f"bg_{slide.get('id', strip_count)}",
                        filepath=bg_ref,
                        channel=channel_bg,
                        frame_start=start_frame,
                    )
                    strip.frame_final_end = end_frame
                    strip.transform.scale_x = resolution_x / max(strip.elements[0].orig_width, 1)
                    strip.transform.scale_y = resolution_y / max(strip.elements[0].orig_height, 1)
                else:
                    strip = seq_editor.sequences.new_effect(
                        name=f"bg_{slide.get('id', strip_count)}",
                        type='COLOR',
                        channel=channel_bg,
                        frame_start=start_frame,
                        frame_end=end_frame,
                    )
                    r, g, b = self._hex_to_rgb(bg_color)
                    strip.color = (r, g, b)
                strip_count += 1

                # Title text strip
                title = slide.get("title", "")
                if title:
                    text_strip = seq_editor.sequences.new_effect(
                        name=f"title_{slide.get('id', strip_count)}",
                        type='TEXT',
                        channel=channel_title,
                        frame_start=start_frame,
                        frame_end=end_frame,
                    )
                    text_strip.text = title
                    text_strip.font_size = style.get("font_size_title", 72)
                    fc = self._hex_to_rgb(style.get("font_color", "#FFFFFF"))
                    text_strip.color = (fc[0], fc[1], fc[2], 1.0)
                    text_strip.location[1] = 0.7  # upper portion
                    alignment = style.get("text_alignment", "center").upper()
                    if hasattr(text_strip, 'align_x'):
                        text_strip.align_x = alignment
                    strip_count += 1

                # Body text strip
                body = slide.get("body_text", "")
                if body:
                    body_strip = seq_editor.sequences.new_effect(
                        name=f"body_{slide.get('id', strip_count)}",
                        type='TEXT',
                        channel=channel_body,
                        frame_start=start_frame,
                        frame_end=end_frame,
                    )
                    body_strip.text = body[:500]  # Blender text limit
                    body_strip.font_size = style.get("font_size_body", 36)
                    fc = self._hex_to_rgb(style.get("font_color", "#FFFFFF"))
                    body_strip.color = (fc[0], fc[1], fc[2], 1.0)
                    body_strip.location[1] = 0.4  # lower portion
                    strip_count += 1

            # Add audio if provided
            if audio_path and os.path.exists(audio_path):
                audio_strip = seq_editor.sequences.new_sound(
                    name="narration",
                    filepath=audio_path,
                    channel=channel_body + 1,
                    frame_start=1,
                )
                strip_count += 1

            return {
                "success": True,
                "message": f"Rendered {len(slide_list)} slides to VSE",
                "strip_count": strip_count,
                "frame_range": [scene.frame_start, scene.frame_end],
            }
        except Exception as e:
            print(f"Error in render_slides_to_vse: {str(e)}")
            traceback.print_exc()
            return {"error": str(e)}

    def render_preview_frame(self, frame_number, filepath):
        """Render a single frame from the VSE as a PNG preview."""
        try:
            scene = bpy.context.scene
            scene.frame_set(frame_number)

            # Store original settings
            orig_format = scene.render.image_settings.file_format
            orig_filepath = scene.render.filepath

            scene.render.image_settings.file_format = 'PNG'
            scene.render.filepath = filepath

            bpy.ops.render.render(write_still=True)

            # Restore
            scene.render.image_settings.file_format = orig_format
            scene.render.filepath = orig_filepath

            return {
                "success": True,
                "filepath": filepath,
                "frame": frame_number,
            }
        except Exception as e:
            return {"error": str(e)}

    def export_video(self, output_path, format="MPEG4", fps=30):
        """Export the VSE timeline as a video file."""
        try:
            scene = bpy.context.scene

            scene.render.filepath = output_path
            scene.render.image_settings.file_format = 'FFMPEG'
            scene.render.ffmpeg.format = format
            scene.render.ffmpeg.codec = 'H264'
            scene.render.ffmpeg.audio_codec = 'AAC'
            scene.render.fps = fps

            bpy.ops.render.render(animation=True)

            return {
                "success": True,
                "output_path": output_path,
                "frame_range": [scene.frame_start, scene.frame_end],
            }
        except Exception as e:
            return {"error": str(e)}

    def set_vse_audio(self, audio_path, start_frame=1):
        """Add an audio strip to the VSE."""
        try:
            scene = bpy.context.scene
            if not scene.sequence_editor:
                scene.sequence_editor_create()

            # Find next available channel
            used_channels = {s.channel for s in scene.sequence_editor.sequences_all}
            channel = max(used_channels, default=0) + 1

            audio_strip = scene.sequence_editor.sequences.new_sound(
                name="audio",
                filepath=audio_path,
                channel=channel,
                frame_start=start_frame,
            )

            return {
                "success": True,
                "strip_name": audio_strip.name,
                "channel": channel,
                "duration_frames": audio_strip.frame_final_duration,
            }
        except Exception as e:
            return {"error": str(e)}

    @staticmethod
    def _hex_to_rgb(hex_color):
        """Convert hex color string to RGB tuple (0-1 range)."""
        hex_color = hex_color.lstrip('#')
        r = int(hex_color[0:2], 16) / 255.0
        g = int(hex_color[2:4], 16) / 255.0
        b = int(hex_color[4:6], 16) / 255.0
        return (r, g, b)


# ── UI Panel ────────────────────────────────────────────────────────────

class VIDEODRAFT_PT_Panel(bpy.types.Panel):
    bl_label = "Video Draft MCP"
    bl_idname = "VIDEODRAFT_PT_Panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'VideoDraftMCP'

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        layout.prop(scene, "videodraft_port")

        if not scene.videodraft_server_running:
            layout.operator("videodraft.start_server", text="Connect to MCP server")
        else:
            layout.operator("videodraft.stop_server", text="Disconnect from MCP server")
            layout.label(text=f"Running on port {scene.videodraft_port}")


class VIDEODRAFT_OT_StartServer(bpy.types.Operator):
    bl_idname = "videodraft.start_server"
    bl_label = "Connect to Claude"
    bl_description = "Start the VideoDraftMCP server to connect with Claude"

    def execute(self, context):
        scene = context.scene

        if not hasattr(bpy.types, "videodraft_server") or not bpy.types.videodraft_server:
            bpy.types.videodraft_server = BlenderMCPServer(port=scene.videodraft_port)

        bpy.types.videodraft_server.start()
        scene.videodraft_server_running = True
        return {'FINISHED'}


class VIDEODRAFT_OT_StopServer(bpy.types.Operator):
    bl_idname = "videodraft.stop_server"
    bl_label = "Stop the connection to Claude"
    bl_description = "Stop the connection to Claude"

    def execute(self, context):
        scene = context.scene

        if hasattr(bpy.types, "videodraft_server") and bpy.types.videodraft_server:
            bpy.types.videodraft_server.stop()
            del bpy.types.videodraft_server

        scene.videodraft_server_running = False
        return {'FINISHED'}


# ── Registration ────────────────────────────────────────────────────────

def register():
    bpy.types.Scene.videodraft_port = IntProperty(
        name="Port",
        description="Port for the VideoDraftMCP server",
        default=9876,
        min=1024,
        max=65535,
    )

    bpy.types.Scene.videodraft_server_running = bpy.props.BoolProperty(
        name="Server Running",
        default=False,
    )

    bpy.utils.register_class(VIDEODRAFT_PT_Panel)
    bpy.utils.register_class(VIDEODRAFT_OT_StartServer)
    bpy.utils.register_class(VIDEODRAFT_OT_StopServer)

    print("VideoDraftMCP addon registered")


def unregister():
    if hasattr(bpy.types, "videodraft_server") and bpy.types.videodraft_server:
        bpy.types.videodraft_server.stop()
        del bpy.types.videodraft_server

    bpy.utils.unregister_class(VIDEODRAFT_PT_Panel)
    bpy.utils.unregister_class(VIDEODRAFT_OT_StartServer)
    bpy.utils.unregister_class(VIDEODRAFT_OT_StopServer)

    del bpy.types.Scene.videodraft_port
    del bpy.types.Scene.videodraft_server_running

    print("VideoDraftMCP addon unregistered")


if __name__ == "__main__":
    register()
