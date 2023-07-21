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
import logging
from pathlib import Path
from hashlib import sha256
import os
import sys

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO,
                    format='%(levelname)8s %(message)s')
if os.getenv("ADDON_DEBUG"):
    log.setLevel(logging.DEBUG)
    log.debug("debug log enabled")

paths = bpy.utils.blend_paths(absolute=True, packed=True, local=False)
log.debug("all paths: %s", paths)

helio_dir = os.getenv('HELIO_DIR')

log.debug("starting missing files: %s", helio_dir)

bpy.ops.file.find_missing_files(find_all=True, directory=helio_dir)

log.debug("stopped missing files")

bpy.ops.wm.save_as_mainfile(filepath=bpy.data.filepath, relative_remap=True, compress=True)
bpy.ops.wm.quit_blender()
