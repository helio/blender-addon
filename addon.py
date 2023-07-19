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

import bpy
import bpy.utils.previews
import subprocess
import os
import json
import logging
from urllib.parse import urlencode
from pathlib import Path
from hashlib import sha256
from shutil import copy2
from . import addon_updater_ops

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO,
                    format='%(levelname)8s %(message)s')
if os.getenv("ADDON_DEBUG"):
    log.setLevel(logging.DEBUG)
    log.debug("debug log enabled")
    addon_updater_ops.updater.verbose = True


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

    def get_progress(self):
        return self.value

    def get_progress_status(self):
        return self.status_value

    progress: bpy.props.FloatProperty( name="Progress", subtype="PERCENTAGE", soft_min=0, soft_max=100, precision=1, get=get_progress)
    progress_status: bpy.props.StringProperty(name="Status", get=get_progress_status)


class RenderOnHelio(bpy.types.Operator):
    """Render on Helio"""      # Use this as a tooltip for menu items and buttons.
    bl_idname = "helio.render"        # Unique identifier for buttons and menu items to reference.
    bl_label = "Render On Helio"         # Display name in the interface.
    bl_options = {'REGISTER', 'UNDO'}  # Enable undo for the operator.

    _steps = []
    _current_step = None
    _total_steps = None
    _timer = None
    _timer_count = 0

    def update_progress(self, context, value, status):
        log.debug("update progress %d %s", value, status)
        helio_progress = context.scene.helio_progress
        helio_progress.value = value
        helio_progress.status_value = status

    def check(self, context):
        return True

    def target_dir(self, context):
        directory = Path(bpy.data.filepath).parent
        return Path(directory, "_helio")

    def process_step(self, context):
        helio_dir = self.target_dir(context)

        action, param = self._steps[self._current_step]
        log.debug("current step %d (%s, %s", self._current_step, action, param)
        progress_message = ""
        if action == 'copy':
            path = param
            name = Path(path).name
            directory = Path(path).parent
            new_dir = Path(helio_dir, sha256(str(directory).encode("utf-8")).hexdigest())
            new_dir.mkdir(parents=False, exist_ok=True)
            try:
                copy2(path, str(new_dir))
                progress_message = f"Copied {name}"
            except FileNotFoundError:
                log.error("file not found: %s", path)
                progress_message = f"File {name} not found"
        elif action == 'relink':
            bpy.ops.file.find_missing_files(find_all=True, directory=param)
            progress_message = "Relinked files"
        elif action == 'resave':
            bpy.ops.wm.save_as_mainfile(filepath=param, copy=True, relative_remap=True)
            progress_message = "Saved exported file"
        elif action == 'open_client':
            protocol = "helio-render"
            prefs = addon_updater_ops.get_user_preferences(context)
            release = prefs.client_target_release
            if release == "BETA":
                protocol += "-beta"
            elif release == "ALPHA":
                protocol += "-alpha"
            subprocess.run(["open", f"{protocol}://scene-manager.pulze.io/projects/upsert?"+param])
            log.info("opening client")
            progress_message = "Opened Helio Client"
        else:
            raise NotImplementedError(f"Not implemented step: ({action}, {param})")

        self._current_step += 1
        self.update_progress(context, self._current_step/self._total_steps*100, progress_message)
        context.area.tag_redraw()

    def done(self):
        return self._current_step == self._total_steps

    def modal(self, context, event):
        if event.type != 'TIMER':
            return {'PASS_THROUGH'}

        self._timer_count += 1
        if self._timer_count == 2:
            self._timer_count = 0

            self.process_step(context)

            if self.done():
                context.area.tag_redraw()
                self.cancel(context)

                if not bpy.data.is_saved:
                    log.info("file not saved, executing undo.")
                    bpy.ops.ed.undo()
                else:
                    log.info("file is saved, doing nothing")
                return {'FINISHED'}

        return {'PASS_THROUGH'}

    def invoke(self, context, event):
        self.update_progress(context, 0, "")
        self._steps = []
        bpy.ops.helio.render_modal('INVOKE_DEFAULT')

        if not bpy.data.is_saved:
            log.error("current blender file not saved")
            self.update_progress(context, 100.0, "current blender file is not saved")
            return {'FINISHED'}

        filename = Path(bpy.data.filepath).name
        directory = Path(bpy.data.filepath).parent
        helio_dir = Path(directory, "_helio")
        helio_dir.mkdir(parents=False, exist_ok=True)
        log.debug("created directory %s", helio_dir)

        project_path = str(helio_dir)
        project_name = filename
        project_filepath = str(helio_dir.joinpath(project_name))

        paths = bpy.utils.blend_paths(absolute=True, packed=True, local=False)
        log.debug("all paths: %s", paths)

        for path in paths:
            self._steps.append(('copy', path))

        self._steps.append(('relink', project_path))
        self._steps.append(('resave', project_filepath))

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

        prefs = None
        if hasattr(context, "user_preferences"):
            prefs = context.user_preferences
        elif hasattr(context, "preferences"):
            prefs = context.preferences

        engine_id = "cycles"
        if engine == 'BLENDER_EEVEE':
            if bpy.app.version < (3, 6, 0):
                raise NotImplementedError("EEVEE support is limited to blender versions >= 3.6.0")
            engine_id = 'eevee_gpu_optix' # eevee only this is possible
        else:
            device = cycles.device
            if device == 'GPU':
                engine_id += '_gpu'
            compute_device_type = prefs.addons['cycles'].preferences.compute_device_type
            if compute_device_type == 'OPTIX':
                engine_id += '_optix'

        major, minor, patch = bpy.app.version
        full_version = '.'.join(map(str, bpy.app.version))
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
                    "output": {
                        "common": {
                            "enabled": True,
                            "final": render.frame_path(),
                            "project": render.filepath,
                            "extension": render.image_settings.file_format
                        }
                    },
                    "render_settings": [],
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
    bl_label = "Helio Render Modal"
    bl_region_type = "UI"
    bl_options = {'REGISTER', 'INTERNAL'}

    def draw(self, context):
        helio_progress = context.scene.helio_progress
        layout = self.layout

        layout.prop(helio_progress, "progress")
        layout.prop(helio_progress, "progress_status")

    def check(self, context):
        # Important for changing options
        return True

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        return {'PASS_THROUGH'}


def menu_func(self, context):
    global custom_icons
    self.layout.operator(RenderOnHelio.bl_idname, icon_value=custom_icons["helio_icon"].icon_id)


classes = [Preferences, RenderOnHelio, HelioProgress, ModalOperator]

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
