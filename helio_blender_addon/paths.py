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
from bpy.app.handlers import persistent
from pathlib import Path
import sys
import logging
import subprocess
import os
from hashlib import sha256
from distutils.file_util import copy_file
from distutils.errors import DistutilsFileError


log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO,
                    format='%(levelname)8s %(message)s')
if os.getenv("ADDON_DEBUG"):
    log.setLevel(logging.DEBUG)
    log.debug("debug log enabled")


def relocate_files(all_paths, target_parent_dir, objects):
    for obj in objects:
        if obj.filepath == "":
            yield obj.filepath, "empty filepath", False
            return

        path = Path(bpy.path.abspath(obj.filepath, library=obj.library))

        directory = path.parent
        target_dir = target_parent_dir.joinpath(sha256(str(directory).encode("utf-8")).hexdigest())
        target_dir.mkdir(parents=False, exist_ok=True)

        log.debug("copying %s file (%s) %s to %s (lib: %s)", obj.name, obj.filepath, path, target_dir, obj.library)
        all_paths.remove(str(path))

        if '<UDIM>' in obj.filepath:
            directory = path.parent
            target_dir = target_parent_dir.joinpath(sha256(str(directory).encode("utf-8")).hexdigest())
            for p in directory.glob(path.name.replace('<UDIM>', '*')):
                log.debug("copying %s file (%s) %s to %s", obj.name, obj.filepath, p, target_dir)
                try:
                    dest, copied = copy_file(str(p), str(target_dir), update=True)
                    yield str(p), dest, copied
                except DistutilsFileError as e:
                    yield str(p), e, False
            obj.filepath = str(target_dir.joinpath(path.name))
        else:
            try:
                dest, copied = copy_file(str(path), str(target_dir), update=True)
                obj.filepath = str(target_dir.joinpath(path.name))
                yield str(path), dest, copied
            except DistutilsFileError as e:
                yield str(path), e, False


@persistent
def load_post(filepath):
    log.debug("load post %s", filepath)

    path = Path(filepath)
    directory = path.parent
    helio_dir = Path(directory, "_helio")
    if os.getenv("HELIO_DIR"):
        # log_file = Path(os.getenv("HELIO_DIR")).joinpath(bpy.data.filepath.replace('.blend', '.log'))
        # try:
        #     log_file.unlink()
        # except Exception:
        #     pass
        # fh = logging.FileHandler(str(log_file))
        # fh.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
        # log.addHandler(fh)
        # log.info("handle %s", bpy.data.filepath)
        # log.debug("HELIO_DIR=%s", os.getenv("HELIO_DIR"))
        helio_dir = Path(os.getenv("HELIO_DIR"))

    filename = path.name
    project_name = filename
    project_filepath = str(helio_dir.joinpath(project_name))
    helio_dir.mkdir(parents=False, exist_ok=True)

    all_paths = set(bpy.utils.blend_paths(absolute=True, packed=True, local=False))
    print('<<<< all paths', bpy.utils.blend_paths(absolute=True, packed=True, local=False))

    for idx, objects in enumerate([
        bpy.data.libraries,
        bpy.data.images,
        bpy.data.movieclips,
        bpy.data.fonts,
        bpy.data.sounds,
        bpy.data.texts,
        bpy.data.volumes,
        bpy.data.cache_files
    ]):
        for src, dest, copied in relocate_files(all_paths, helio_dir, objects):
            if copied:
                log.info("%s copied %s to %s", idx, src, dest)
            else:
                log.info("%s did not copy: %s (%s)", idx, src, dest)

    if os.getenv("SKIP_LIBRARIES") != "true":
        for lib in bpy.data.libraries:
            subprocess.run([bpy.app.binary_path, '-b', '-P', __file__, lib.filepath], env={'HELIO_DIR': helio_dir, 'SKIP_LIBRARIES': "true", 'ADDON_DEBUG': os.getenv('ADDON_DEBUG')})
            sys.exit(1)

    print('remaining >>>', all_paths)

    bpy.ops.wm.save_as_mainfile(filepath=project_filepath, copy=True, relative_remap=True, compress=True)


bpy.app.handlers.load_post.append(load_post)
