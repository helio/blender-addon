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

from helio_blender_addon import addon_updater_ops
from helio_blender_addon import addon

bl_info = {
    "name": "Helio Cloud Rendering",
    "blender": (3, 20, 0),
    "version": (0, 1, 9),
    "category": "Render",
    "tracker_url": "https://github.com/helio/blender-addon/issues"
}


def register():
    addon_updater_ops.register(bl_info)
    addon.register()


def unregister():
    addon_updater_ops.unregister()
    addon.unregister()

# This allows you to run the script directly from Blender's Text editor
# to test the add-on without having to install it.
if __name__ == "__main__":
    register()
