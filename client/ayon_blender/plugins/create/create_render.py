"""Create render."""
import re

import bpy
from typing import Optional

from ayon_core.lib import BoolDef, EnumDef, AbstractAttrDef
from ayon_core.pipeline.create import CreatedInstance
from ayon_blender.api import plugin, lib, render_lib

BLENDER_VERSION = lib.get_blender_version()

# Unique tooltip snippets used to find the Create-dialog widgets. ayon-core
# does not expose those fields, so the addon locates them after they exist.
_AOV_PRESET_TOOLTIP = (
    "Studio AOV layout from AYON settings. Selecting a "
    "preset ticks the matching AOVs below. You can then "
    "check or uncheck passes for this instance."
)
_AOV_LIST_TOOLTIP = (
    "Passes enabled when Create Render Setup is on. "
    "Filled from the selected AOV Preset; check or uncheck "
    "to add or remove passes from the compositor setup."
)


def clean_name(name: str) -> str:
    """Ensure variant name is valid, e.g. strip spaces from name"""
    # Entity name regex taken from server code which also applies to
    # product names (which also follows the same rules).
    name_regex = r"^[a-zA-Z0-9_]([a-zA-Z0-9_\.\-]*[a-zA-Z0-9_])?$"

    # Remove spaces
    clean = name.replace(" ", "")
    # Strip out any remaining invalid characters
    clean = re.sub(r"[^a-zA-Z0-9_.-]", "", clean)
    # Ensure start and end characters are not a dot or dash
    clean = clean.strip(".-")
    # Ensure name is at least 1 character long
    if not clean:
        # Fallback to a default name
        clean = "Main"

    if not re.match(name_regex, clean):
        raise ValueError(f"Failed to create valid name for {name}")
    return clean


class CreateRender(plugin.BlenderCreator):
    """Create render from Compositor File Output node"""

    identifier = "io.ayon.creators.blender.render"
    label = "Render"
    description = __doc__
    product_base_type = "render"
    product_type = product_base_type
    icon = "eye"

    render_target = "farm"

    def _find_compositor_node_from_create_render_setup(self) -> Optional["bpy.types.CompositorNodeOutputFile"]:
        tree = lib.get_scene_node_tree()
        for node in tree.nodes:
            if (
                    node.bl_idname == "CompositorNodeOutputFile"
                    and node.name == "AYON File Output"
            ):
                return node
        return None

    def create(
        self, product_name: str, instance_data: dict, pre_create_data: dict
    ):
        tree = lib.get_scene_node_tree(ensure_exists=True)

        variant: str = instance_data.get("variant", self.default_variant)
        view_layers: Optional[list[str]] = pre_create_data.get("view_layers")

        if pre_create_data.get("create_render_setup", False):
            # TODO: Prepare rendering setup should always generate a new
            #  setup, and return the relevant compositor node instead of
            #  guessing afterwards
            # add options to select renderlayers
            project_settings = (
                self.create_context.get_current_project_settings()
            )
            aov_preset = self._resolve_aov_preset(
                pre_create_data, project_settings
            )
            aov_list = pre_create_data.get("aov_list")
            if aov_list is None or (
                aov_list == [] and not getattr(self, "_aov_list_widget_ready", False)
            ):
                aov_list = aov_preset.get("aov_list") or ["combined"]
            node = render_lib.prepare_rendering(
                variant_name=variant,
                project_settings=project_settings,
                selected_view_layers=view_layers,
                aov_list=aov_list,
                custom_passes=aov_preset.get("custom_passes") or [],
            )

        else:
            project_settings = (
                self.create_context.get_current_project_settings()
            )
            view_layer_nodes = render_lib.get_selected_render_layer_nodes(
                tree,
                selected_all=True,
                selected_view_layers=view_layers
            )
            node = render_lib.create_render_node_tree(
                variant,
                view_layer_nodes,
                project_settings
            )

        project_name = self.create_context.get_current_project_name()
        project_entity = self.create_context.get_current_project_entity()
        folder_entity = self.create_context.get_current_folder_entity()
        task_entity = self.create_context.get_current_task_entity()

        product_type = instance_data.get("productType")
        if not product_type:
            product_type = self.product_base_type

        variant = clean_name(node.name)
        product_name = self.get_product_name(
            project_name=project_name,
            project_entity=project_entity,
            folder_entity=folder_entity,
            task_entity=task_entity,
            variant=variant,
            host_name=self.create_context.host_name,
            product_type=product_type,
        )

        instance_data["productName"] = product_name
        self.set_instance_data(product_name, instance_data)
        instance = CreatedInstance(
            product_base_type=self.product_base_type,
            product_type=product_type,
            product_name=product_name,
            data=instance_data,
            creator=self,
        )
        instance.transient_data["instance_node"] = node
        self._add_instance_to_context(instance)

        self.imprint(node, instance_data)

        return instance

    def collect_instances(self):
        node_tree = lib.get_scene_node_tree()
        if not node_tree:
            # Blender 5.0 may not have created and set a compositor group
            return

        super().collect_instances()

        # TODO: Collect all Compositor nodes - even those that are not
        #   imprinted with any data.
        collected_nodes = {
            created_instance.transient_data.get("instance_node")
            for created_instance in self.create_context.instances
        }
        collected_nodes.discard(None)

        # Convert legacy instances that did not yet imprint on the
        # compositor node itself
        for instance in self.create_context.instances:
            # Ignore instances from other creators
            if instance.creator_identifier != self.identifier:
                continue

            # Check if node type is the old object type
            node = instance.transient_data["instance_node"]

            if not isinstance(node, bpy.types.Collection):
                # Already new-style node
                continue

            self.log.info(f"Converting legacy render instance: {node}")
            # Find the related compositor node
            # TODO: Find the actual relevant compositor node instead of just
            #  any
            comp_node = self._find_compositor_node_from_create_render_setup()
            if not comp_node:
                raise RuntimeError("No compositor node found")

            instance.transient_data["instance_node"] = comp_node
            self.imprint(comp_node, instance.data_to_store())

            # Delete the original object
            bpy.data.collections.remove(node)

        # Collect all remaining compositor output nodes
        unregistered_output_nodes = [
            node for node in node_tree.nodes
            if node.bl_idname == "CompositorNodeOutputFile"
            and node not in collected_nodes
        ]
        if not unregistered_output_nodes:
            return

        project_name = self.create_context.get_current_project_name()
        project_entity = self.create_context.get_current_project_entity()
        folder_entity = self.create_context.get_current_folder_entity()
        task_entity = self.create_context.get_current_task_entity()
        for node in unregistered_output_nodes:
            self.log.info("Found unregistered render output node: %s",
                          node.name)
            variant = clean_name(node.name)

            instance_data = self.read(node)
            product_type = instance_data.get("productType")
            if not product_type:
                product_type = self.product_base_type

            product_name = self.get_product_name(
                project_name=project_name,
                project_entity=project_entity,
                folder_entity=folder_entity,
                task_entity=task_entity,
                variant=variant,
                host_name=self.create_context.host_name,
                product_type=product_type,
            )
            instance_data.update({
                "folderPath": folder_entity["path"],
                "task": task_entity["name"],
                "productName": product_name,
                "variant": variant,
            })

            instance = CreatedInstance(
                product_base_type=self.product_base_type,
                product_type=product_type,
                product_name=product_name,
                data=instance_data,
                creator=self,
                transient_data={
                    "instance_node": node
                }
            )
            self._add_instance_to_context(instance)

    def _resolve_aov_preset(
        self, pre_create_data: dict, project_settings: dict
    ) -> dict:
        """Return the AOV preset selected in the Create dialog."""
        default_preset = render_lib.get_default_aov_preset(project_settings)
        selected_name = pre_create_data.get("aov_preset") or getattr(
            self, "_active_aov_preset", None
        )
        selected = render_lib.get_aov_preset(project_settings, selected_name)
        return selected or default_preset

    @staticmethod
    def _qt_widget_alive(widget) -> bool:
        if widget is None:
            return False
        try:
            widget.objectName()
        except RuntimeError:
            return False
        return True

    def _start_aov_widget_sync(self) -> None:
        """Keep the AOV checklist in sync with the preset dropdown.

        ayon-core does not apply multi-select enum defaults, and it cannot
        retick sibling fields when a dropdown changes. After the Create
        widgets exist we find them and drive the checklist ourselves.
        """
        try:
            from qtpy import QtCore, QtWidgets
        except Exception:
            return

        app = QtWidgets.QApplication.instance()
        timer = getattr(self, "_aov_sync_timer", None)
        if timer is None:
            timer = QtCore.QTimer(app)
            timer.setInterval(100)
            timer.timeout.connect(self._sync_aov_create_widgets)
            self._aov_sync_timer = timer
        if not timer.isActive():
            timer.start()
        self._sync_aov_create_widgets()

    def _find_aov_create_widgets(self):
        """Return the AOV Preset and AOVs EnumAttrWidget wrappers.

        ayon-core does not expose these fields, so they are located by the
        ``attr_def.key`` set on each Create-dialog widget.
        """
        try:
            from qtpy import QtWidgets
        except Exception:
            return None, None

        app = QtWidgets.QApplication.instance()
        if app is None:
            return None, None

        preset_widget = None
        aov_widget = None
        for widget in app.allWidgets():
            attr_def = getattr(widget, "attr_def", None)
            if attr_def is None:
                continue
            key = getattr(attr_def, "key", None)
            if key == "aov_preset":
                if widget.isVisible() or preset_widget is None:
                    preset_widget = widget
            elif key == "aov_list":
                if widget.isVisible() or aov_widget is None:
                    aov_widget = widget
        return preset_widget, aov_widget

    def _read_preset_name(self, preset_widget) -> Optional[str]:
        if not self._qt_widget_alive(preset_widget):
            return None
        if hasattr(preset_widget, "current_value"):
            try:
                value = preset_widget.current_value()
                if value:
                    return value
            except Exception:
                pass
        combo = getattr(preset_widget, "_input_widget", preset_widget)
        if hasattr(combo, "currentData"):
            return combo.currentData() or combo.currentText() or None
        return None

    def _apply_preset_to_aov_widget(
        self, aov_widget, preset_name: str
    ) -> None:
        if not self._qt_widget_alive(aov_widget):
            return

        project_settings = self.create_context.get_current_project_settings()
        aov_items = render_lib.get_aov_enum_items(
            render_lib.get_renderer(project_settings)
        )
        preset = (
            render_lib.get_aov_preset(project_settings, preset_name)
            or render_lib.get_default_aov_preset(project_settings)
        )
        wanted = [
            value for value in (preset.get("aov_list") or [])
            if value in aov_items
        ]

        # EnumAttrWidget.set_value is the official API and also updates
        # the tag layout on MultiSelectionComboBox.
        if hasattr(aov_widget, "set_value"):
            aov_widget.set_value(wanted)
        combo = getattr(aov_widget, "_input_widget", aov_widget)
        if combo is not aov_widget and hasattr(combo, "set_value"):
            combo.set_value(wanted)
        if hasattr(combo, "_update_size_hint"):
            combo._update_size_hint()
        combo.updateGeometry()
        combo.update()
        combo.repaint()
        self._aov_list_widget_ready = True

    def _on_aov_preset_changed(self, preset_widget, aov_widget, *_args) -> None:
        preset_name = self._read_preset_name(preset_widget)
        if not preset_name:
            return
        self._active_aov_preset = preset_name
        self._apply_preset_to_aov_widget(aov_widget, preset_name)
        self._last_applied_aov_preset = preset_name

    def _sync_aov_create_widgets(self) -> None:
        preset_widget = getattr(self, "_aov_preset_widget", None)
        aov_widget = getattr(self, "_aov_list_widget", None)
        if (
            not self._qt_widget_alive(preset_widget)
            or not self._qt_widget_alive(aov_widget)
        ):
            preset_widget, aov_widget = self._find_aov_create_widgets()
            self._aov_preset_widget = preset_widget
            self._aov_list_widget = aov_widget
            self._last_applied_aov_preset = None
            self._aov_preset_connected = False

        if aov_widget is None:
            return

        current_preset = self._read_preset_name(preset_widget)
        if not current_preset:
            project_settings = (
                self.create_context.get_current_project_settings()
            )
            current_preset = getattr(self, "_active_aov_preset", None) or (
                render_lib.get_default_aov_preset(project_settings).get("name")
            )
        if current_preset:
            self._active_aov_preset = current_preset

        last = getattr(self, "_last_applied_aov_preset", None)
        if current_preset and current_preset != last:
            self._apply_preset_to_aov_widget(aov_widget, current_preset)
            self._last_applied_aov_preset = current_preset

        # Direct widget refs are passed into the slot. CreateRender is not a
        # QObject, so QObject.sender() is always None and cannot be used.
        preset_combo = getattr(preset_widget, "_input_widget", preset_widget)
        if (
            self._qt_widget_alive(preset_combo)
            and not getattr(self, "_aov_preset_connected", False)
        ):
            self._aov_preset_connected = True
            callback = (
                lambda *_args, p=preset_widget, a=aov_widget:
                self._on_aov_preset_changed(p, a)
            )
            preset_combo.currentIndexChanged.connect(callback)
            try:
                preset_combo.activated.connect(callback)
            except (TypeError, AttributeError):
                try:
                    preset_combo.activated[int].connect(callback)
                except (TypeError, AttributeError):
                    pass

    def get_instance_attr_defs(self):
        render_target_items: dict[str, str] = {
            "local": "Local machine rendering",
            "local_no_render": "Use existing frames (local)",
            "farm": "Farm Rendering",
        }

        defs: list[AbstractAttrDef] = lib.collect_animation_defs(
            self.create_context
        )
        defs.extend([
            EnumDef("render_target",
                    items=render_target_items,
                    label="Render target",
                    default=self.render_target),
            BoolDef("review",
                    label="Review",
                    tooltip="Mark as reviewable",
                    default=True),
        ])
        return defs

    def get_pre_create_attr_defs(self):
        view_layer_items: list[str] = [
            layer.name for layer in bpy.context.scene.view_layers
        ]
        project_settings = self.create_context.get_current_project_settings()
        renderer = render_lib.get_renderer(project_settings)
        aov_preset = render_lib.get_default_aov_preset(project_settings)
        aov_items = render_lib.get_aov_enum_items(renderer)
        preset_items = render_lib.get_aov_preset_enum_items(project_settings)
        default_preset_name = aov_preset.get("name") or "Default"
        if default_preset_name not in preset_items:
            default_preset_name = next(iter(preset_items))
        default_aovs = [
            value for value in (aov_preset.get("aov_list") or [])
            if value in aov_items
        ]
        self._start_aov_widget_sync()
        return [
            BoolDef(
                "create_render_setup",
                label="Create Render Setup",
                default=True,
                tooltip="Create Render Setup",
            ),
            EnumDef("view_layers",
                    items=view_layer_items,
                    label="View Layers",
                    multiselection=True,
                    default=[],
                    tooltip="Select view layers to include in the render setup"
            ),
            EnumDef(
                "aov_preset",
                items=preset_items,
                label="AOV Preset",
                default=default_preset_name,
                tooltip=_AOV_PRESET_TOOLTIP,
            ),
            EnumDef(
                "aov_list",
                items=aov_items,
                label="AOVs",
                multiselection=True,
                default=default_aovs,
                tooltip=_AOV_LIST_TOOLTIP,
            ),
        ]

    def imprint(self, node: bpy.types.CompositorNodeOutputFile, data: dict):
        # Use the node `mute` state to define the active state of the instance.
        active = data.pop("active", True)
        node.mute = not active
        super().imprint(node, data)

    def read(self, node: bpy.types.CompositorNodeOutputFile) -> dict:
        # Read the active state from the node `mute` state.
        data = super().read(node)

        # On super().collect_instances() it may collect legacy render instances
        # that are not Compositor nodes but Collection objects.
        if isinstance(node, bpy.types.CompositorNodeOutputFile):
            data["active"] = not node.mute

        return data
