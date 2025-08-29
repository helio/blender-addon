# ##### BEGIN GPL LICENSE BLOCK #####
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 2
#  of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software Foundation,
#  Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
#
# ##### END GPL LICENSE BLOCK #####
import json
import logging
import os
import subprocess
import sys
import tempfile
import typing
from pathlib import Path, PurePath
from threading import Thread
from urllib.parse import urlencode

import bpy
import bpy.utils.previews
from blender_asset_tracer.pack.transfer import FileTransferError

from blender_asset_tracer import pack
from helio_blender_addon import addon_updater_ops

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO,
                    format='%(levelname)8s %(message)s')
if os.getenv("ADDON_DEBUG"):
    log.setLevel(logging.DEBUG)
    log.debug("debug log enabled")
    addon_updater_ops.updater.verbose = True


def startfile(path):
    """
    Cross-platform start file for opening helio client.
    """
    if sys.platform == 'win32':
        os.startfile(path)
    elif sys.platform == 'darwin':
        subprocess.run(["open", path])
    else:
        subprocess.run(["xdg-open", path])


@addon_updater_ops.make_annotations
class Preferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    client_target_release = bpy.props.EnumProperty(
        name="Client release to use",
        description="Determines which client release to use. Must have the respective client installed",
        items=[('STABLE', 'Stable', ''), ('BETA', 'Beta', ''), ('ALPHA', 'Alpha', '')],
        default="STABLE"
    )

    # Addon updater preferences.
    auto_check_update = bpy.props.BoolProperty(
        name="Auto-check for Update",
        description="If enabled, auto-check for updates using an interval",
        default=True)

    updater_interval_months = bpy.props.IntProperty(
        name='Months',
        description="Number of months between checking for updates",
        default=0,
        min=0)

    updater_interval_days = bpy.props.IntProperty(
        name='Days',
        description="Number of days between checking for updates",
        default=7,
        min=0,
        max=31)

    updater_interval_hours = bpy.props.IntProperty(
        name='Hours',
        description="Number of hours between checking for updates",
        default=0,
        min=0,
        max=23)

    updater_interval_minutes = bpy.props.IntProperty(
        name='Minutes',
        description="Number of minutes between checking for updates",
        default=0,
        min=0,
        max=59)

    def draw(self, context):
        layout = self.layout

        box = layout.box()
        box.label(text="Helio Settings")
        row = box.row()
        row.prop(self, "client_target_release")

        # Works best if a column, or even just self.layout.
        mainrow = layout.row()
        col = mainrow.column()

        # Updater draw function, could also pass in col as third arg.
        addon_updater_ops.update_settings_ui(self, context)


class HelioProgress(bpy.types.PropertyGroup):
    value: bpy.props.FloatProperty(name="Progress Value", options={'HIDDEN'})
    status_value: bpy.props.StringProperty(name="Status Value", options={'HIDDEN'})
    copy_value: bpy.props.FloatProperty(name="Copy progress", options={'HIDDEN'})
    show_copy_progress: bpy.props.BoolProperty(name="Show copy progress", default=False, options={'HIDDEN'})
    copy_progress_filename: bpy.props.StringProperty(options={'HIDDEN'})

    def get_progress(self):
        return self.value

    def get_progress_status(self):
        return self.status_value

    def get_copy_progress(self):
        return self.copy_value

    progress: bpy.props.FloatProperty(name="Progress", subtype="PERCENTAGE", soft_min=0, soft_max=100, precision=1,
                                      get=get_progress)
    progress_status: bpy.props.StringProperty(name="Status", get=get_progress_status)
    copy_progress: bpy.props.FloatProperty(name="Copy Progress", subtype="PERCENTAGE", soft_min=0, soft_max=100,
                                           precision=1,
                                           get=get_copy_progress, options={'HIDDEN'})


class RenderOnHelio(bpy.types.Operator):
    """Render on Helio"""  # Use this as a tooltip for menu items and buttons.
    bl_idname = "helio.render"  # Unique identifier for buttons and menu items to reference.
    bl_label = "Render On Helio"  # Display name in the interface.
    bl_options = {'REGISTER', 'UNDO'}  # Enable undo for the operator.


    _extension_from_format = {
        "BMP": ".bmp",
        "IRIS": ".rgb",
        "IRIZ": ".rgb",
        "PNG": ".png",
        "JPEG": ".jpg",
        "JPEG2000": ".jpg2",
        "TARGA": ".tga",
        "TARGA_RAW": ".tga",
        "CINEON": ".cin",
        "DPX": ".dpx",
        "OPEN_EXR_MULTILAYER": ".exr",
        "OPEN_EXR": ".exr",
        "HDR": ".hdr",
        "TIFF": ".tiff",
        "WEBP": ".webp",
        "AVI_JPEG": ".jpg",
        "AVI_RAW": ".jpg",
        "FFMPEG": ".png",
    }

    target_directory = None

    _steps = []
    _current_step = None
    _total_steps = None
    _timer = None
    _timer_count = 0
    _log = None
    _thread = None
    _packer = None

    def update_progress(self, context, value, status):
        log.debug("update progress %d %s", value, status)
        helio_progress = context.scene.helio_progress
        helio_progress.value = value
        helio_progress.status_value = status

    def check(self, context):
        return True

    def execute_packer(self):
        self._packer.strategise()
        try:
            self._packer.execute()
        except FileTransferError as ex:
            self._log.info(f"{len(ex.files_remaining)} files couldn't be copied, starting with {ex.files_remaining[0]}")
            raise ex

    class ProgressCallback(pack.progress.Callback):
        def __init__(self, log: logging.Logger, helio_progress: HelioProgress, area: bpy.types.Area):
            self._log = log
            self._helio_progress = helio_progress
            self._current_file = ""
            self._total_files = 2 # pack-info and the main blender file
            self._current_file_num = 0
            self._area = area

        def trace_asset(self, filename: Path) -> None:
            self._helio_progress.show_copy_progress = True
            self._total_files += 1
            self._log.info("adding file %s", filename)

        def transfer_file(self, src: Path, dst: Path) -> None:
            self._log.info("transferring file %s to %s", src, dst)
            self._current_file = src.name
            self._current_file_num += 1
            self._helio_progress.copy_progress_filename = self._current_file
            self._helio_progress.copy_value = self._current_file_num / self._total_files * 100
            self._area.tag_redraw()

        def pack_done(
            self,
            output_blendfile: PurePath,
            missing_files: typing.Set[Path],
        ) -> None:
            self._helio_progress.show_copy_progress = False
            self._log.info("packing done")

        def transfer_file_skipped(self, src: Path, dst: PurePath) -> None:
            self._log.info("skipping file %s (already exists)", src)

        def missing_file(self, filename: Path) -> None:
            self._log.info("missing file %s", filename)

    def process_step(self, context):
        helio_dir = self.target_directory

        action, param = self._steps[self._current_step]
        log.debug("current step %d (%s, %s)", self._current_step, action, param)
        progress_message = ""
        advance_step = True
        if action == 'packer_init':
            progress_message = "Starting packing (no progress report during this time)"
        elif action == 'packer':
            bpath = Path(param)
            directory = bpath.parent

            self._packer = pack.Packer(bpath, directory, str(helio_dir), compress=True)
            self._packer.progress_cb = self.ProgressCallback(self._log, context.scene.helio_progress, context.area)
            self._thread = Thread(target=self.execute_packer)
            self._thread.start()
            progress_message = "Packing..."
        elif action == 'packer_wait':
            advance_step = not self._thread.is_alive()
            if advance_step:
                progress_message = "Packing done"
            else:
                progress_message = "Packing..."
        elif action == 'open_client':
            protocol = "helio-render"
            prefs = addon_updater_ops.get_user_preferences(context)
            try:
                release = prefs.client_target_release
            except AttributeError:
                release = "ALPHA"

            if release == "BETA":
                protocol += "-beta"
            elif release == "ALPHA":
                protocol += "-alpha"
            url = f"{protocol}://scene-manager.pulze.io/projects/upsert?{param}"
            startfile(url)
            log.info("opening client")
            self._log.info("opened client: %s", url)
            progress_message = "Opening Helio Client, please wait"
        else:
            raise NotImplementedError(f"Not implemented step: ({action}, {param})")

        if advance_step:
            self._current_step += 1
        self.update_progress(context, self._current_step / self._total_steps * 100, progress_message)
        context.area.tag_redraw()

    def done(self):
        return self._current_step == self._total_steps

    def modal(self, context, event):
        if event.type != 'TIMER':
            return {'PASS_THROUGH'}

        self._timer_count += 1
        if self._timer_count == 10:
            self._timer_count = 0

            self.process_step(context)

            if self.done():
                context.area.tag_redraw()
                self.cancel(context)

                bpy.ops.wm.revert_mainfile()
                return {'FINISHED'}

        return {'PASS_THROUGH'}

    def invoke(self, context, event):
        log.debug("target directory: %s", self.target_directory)

        self.update_progress(context, 0, "")
        self._steps = []
        bpy.ops.helio.render_modal('INVOKE_DEFAULT')

        if not bpy.data.is_saved:
            log.error("current blender file not saved")
            self.update_progress(context, 100.0, "current blender file is not saved")
            return {'FINISHED'}

        filename = Path(bpy.data.filepath).name
        helio_dir = Path(self.target_directory)
        project_path = str(helio_dir)
        project_name = filename
        project_filepath = str(helio_dir.joinpath(project_name))

        helio_dir.mkdir(parents=False, exist_ok=True)

        self._log = logging.getLogger(filename)
        self._log.setLevel(log.getEffectiveLevel())
        log_file = project_filepath.replace('.blend', '.log')
        try:
            Path(log_file).unlink()
        except Exception:
            pass
        fh = logging.FileHandler(log_file)
        fh.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
        self._log.addHandler(fh)
        self._log.info("start new sync")

        log.debug("created directory %s", helio_dir)

        self._steps.append(('packer_init', bpy.data.filepath))
        self._steps.append(('packer', bpy.data.filepath))
        self._steps.append(('packer_wait', bpy.data.filepath))

        # https://docs.blender.org/api/current/bpy.types.Scene.html#bpy.types.Scene
        scene = context.scene

        camera = scene.camera.name

        # https://docs.blender.org/api/current/bpy.types.RenderSettings.html#bpy.types.RenderSettings
        render = scene.render
        engine = render.engine

        frame_start = scene.frame_start
        frame_end = scene.frame_end

        resolution_x = render.resolution_x
        resolution_y = render.resolution_y

        # https://docs.blender.org/api/current/bpy.types.CyclesRenderSettings.html#bpy.types.CyclesRenderSettings
        cycles = scene.cycles
        cycles_samples = cycles.samples

        render_settings = []

        prefs = None
        if hasattr(context, "user_preferences"):
            prefs = context.user_preferences
        elif hasattr(context, "preferences"):
            prefs = context.preferences

        engine_id = "cycles"
        if engine == 'BLENDER_EEVEE':
            if bpy.app.version < (3, 6, 0):
                raise NotImplementedError("EEVEE support is limited to blender versions >= 3.6.0")
            engine_id = 'eevee_gpu_optix'  # eevee only this is possible
        else:
            device = cycles.device
            if device == 'GPU':
                engine_id += '_gpu'
            compute_device_type = prefs.addons['cycles'].preferences.compute_device_type
            if compute_device_type == 'OPTIX':
                engine_id += '_optix'

            render_settings.append({
                "name": "progressive_passLimit",
                "value": cycles_samples
            })

        major, minor, patch = bpy.app.version
        full_version = '.'.join(map(str, bpy.app.version))

        scene = bpy.context.scene
        render = bpy.context.scene.render

        def final_name(path: Path, file_format: str) -> str:
            if '#' not in path.name:
                path = path.joinpath('####')
            if path.suffix == '':
                path = path.with_suffix(self._extension_from_format[file_format])
            return str(path)

        render_filepath = str(Path(bpy.path.abspath(render.filepath)).resolve())
        output = {
            "common": {
                "enabled": True,
                "final": final_name(Path(render_filepath), render.image_settings.file_format),
                "project": os.path.dirname(render_filepath),
                "extension": render.image_settings.file_format.lower()
            }
        }
        tree = scene.node_tree
        if tree is not None:
            for node in tree.nodes:
                if node.bl_idname == 'CompositorNodeOutputFile':
                    base_path = str(Path(bpy.path.abspath(node.base_path)).resolve())
                    output[bpy.path.clean_name(node.name)] = {
                        "enabled": True,
                        "final": final_name(Path(base_path), node.format.file_format),
                        "project": os.path.dirname(base_path),
                        "extension": node.format.file_format.lower()
                    }

        data = {
            "version": "1.0.0",
            "addon_version": '.'.join(map(str, addon_updater_ops.updater.current_version)),
            "catalog": {
                "tool": {
                    "id": f"blender_{major}_{minor}",
                    "version": full_version
                },
                "engine": {
                    "id": engine_id,
                    "version": full_version
                },
                "plugins": []
            },
            "project_path": project_path,
            "project_name": project_name,
            "scenes": [
                {
                    "id": 1,
                    "scene_id": scene.name,
                    "scene_name": scene.name,
                    "color": "#250E37",
                    "enabled": True,
                    "camera": camera,
                    "resolution": {
                        "width": resolution_x,
                        "height": resolution_y,
                        "ration": 1
                    },
                    "frames": f"{frame_start}-{frame_end}",
                    "output": output,
                    "render_settings": render_settings,
                }
            ]
        }
        data_filename = project_filepath.replace('.blend', '.json')
        with open(str(helio_dir.joinpath(data_filename)), 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        qs = urlencode({
            "path": project_filepath,
        })

        self._steps.append(('open_client', qs))

        self._total_steps = len(self._steps)
        self._current_step = 0

        wm = context.window_manager
        self._timer = wm.event_timer_add(0.1, window=context.window)
        wm.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def cancel(self, context):
        wm = context.window_manager
        wm.event_timer_remove(self._timer)


class ModalOperator(bpy.types.Operator):
    bl_idname = "helio.render_modal"
    bl_label = "Render On Helio"
    bl_region_type = "UI"
    bl_options = {'REGISTER', 'INTERNAL'}

    def draw(self, context):
        helio_progress = context.scene.helio_progress
        layout = self.layout

        layout.prop(helio_progress, "progress")
        if helio_progress.show_copy_progress:
            layout.prop(helio_progress, "copy_progress", text=helio_progress.copy_progress_filename)
        layout.prop(helio_progress, "progress_status")

    def check(self, context):
        # Important for changing options
        return True

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        return {'PASS_THROUGH'}


class TargetDirectoryOperator(bpy.types.Operator):
    bl_idname = "helio.target_directory"
    bl_label = "Select"
    bl_description = "Select target directory where archive should be placed"
    bl_options = {'REGISTER', 'INTERNAL'}

    directory: bpy.props.StringProperty(subtype="DIR_PATH", options={'HIDDEN'})
    filter_folder: bpy.props.BoolProperty(default=True, options={'HIDDEN', 'SKIP_SAVE'})
    title = bpy.props.StringProperty()

    def execute(self, context):
        RenderOnHelio.target_directory = self.directory
        bpy.ops.helio.render('INVOKE_DEFAULT')
        return {'FINISHED'}

    def invoke(self, context, event):
        if event.type == 'ESC':
            return {'CANCELLED'}
        self.title = 'Select target directory for archive'
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}


class TargetDirectoryPromptOperator(bpy.types.Operator):
    bl_idname = "helio.target_directory_prompt"
    bl_label = "Render On Helio..."
    bl_description = "Select target directory where archive should be placed"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        return True

    def execute(self, context):
        return {'FINISHED'}

    def invoke(self, context, event):
        if not bpy.data.is_saved:
            raise Exception("current blender file must be saved before calling Render on Helio")
        return context.window_manager.invoke_popup(self)

    def draw(self, context):
        layout = self.layout
        layout.label(text=self.bl_description)
        layout.operator_context = 'INVOKE_DEFAULT'
        layout.operator(TargetDirectoryOperator.bl_idname, icon="FILEBROWSER", text="Choose target directory...")


def menu_func(self, context):
    global custom_icons
    self.layout.separator()
    self.layout.operator(TargetDirectoryPromptOperator.bl_idname, icon_value=custom_icons["helio_icon"].icon_id)


classes = [Preferences, RenderOnHelio, HelioProgress, ModalOperator, TargetDirectoryOperator,
           TargetDirectoryPromptOperator]

custom_icons = None


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.TOPBAR_MT_render.append(menu_func)  # Adds the new operator to an existing menu.

    bpy.types.Scene.helio_progress = bpy.props.PointerProperty(type=HelioProgress)

    icons_dir = os.path.join(os.path.dirname(__file__), "icons")
    try:
        script_path = bpy.context.space_data.text.filepath
        icons_dir = os.path.join(os.path.dirname(script_path), "icons")
    except (ValueError, AttributeError):
        log.debug("not running in script mode")

    global custom_icons
    custom_icons = bpy.utils.previews.new()
    custom_icons.load("helio_icon", os.path.join(icons_dir, "logo.png"), 'IMAGE')


def unregister():
    for cls in classes:
        try:
            bpy.utils.unregister_class(cls)
        except Exception as e:
            print(e)
    bpy.types.TOPBAR_MT_render.remove(menu_func)

    del bpy.types.Scene.helio_progress

    global custom_icons
    bpy.utils.previews.remove(custom_icons)


# This allows you to run the script directly from Blender's Text editor
# to test the add-on without having to install it.
if __name__ == "__main__":
    register()
