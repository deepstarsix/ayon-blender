import os
from pathlib import Path
from typing import Optional
import bpy

from ayon_core.settings import get_project_settings
from ayon_core.pipeline import get_current_project_name
from . import lib


def get_default_render_folder(project_settings) -> str:
    """Get default render folder from blender settings."""
    return project_settings["blender"]["RenderSettings"][
        "default_render_image_folder"
    ]


def get_aov_separator(project_settings) -> str:
    """Get aov separator from blender settings."""
    aov_sep = project_settings["blender"]["RenderSettings"]["aov_separator"]

    if aov_sep == "dash":
        return "-"
    elif aov_sep == "underscore":
        return "_"
    elif aov_sep == "dot":
        return "."
    else:
        raise ValueError(f"Invalid aov separator: {aov_sep}")


def get_image_format(project_settings) -> str:
    """Get image format from blender settings."""
    return project_settings["blender"]["RenderSettings"]["image_format"]


def get_multilayer(project_settings) -> bool:
    """Get multilayer from blender settings."""
    return project_settings["blender"]["RenderSettings"]["multilayer_exr"]


def get_renderer(project_settings) -> str:
    """Get renderer from blender settings."""
    return project_settings["blender"]["RenderSettings"]["renderer"]


def get_compositing(project_settings) -> bool:
    """Get whether 'Composite' render is enabled from blender settings."""
    # Blender 5+ does not have the "Composite" node, so it's always False
    if lib.get_blender_version() >= (5, 0, 0):
        return False

    return project_settings["blender"]["RenderSettings"]["compositing"]


def set_render_format(ext: str, multilayer: bool):
    """Set Blender scene to save render file with the right extension"""
    bpy.context.scene.render.use_file_extension = True
    image_settings = bpy.context.scene.render.image_settings

    # Force AYON renders to multilayer EXR with half-float and DWAB.
    ext = "exr"
    multilayer = True

    if multilayer and lib.get_blender_version() >= (5, 0, 0):
        image_settings.media_type = "MULTI_LAYER_IMAGE"

    if ext == "exr":
        file_format = "OPEN_EXR_MULTILAYER" if multilayer else "OPEN_EXR"
        image_settings.file_format = file_format
        image_settings.color_depth = "16"
        image_settings.exr_codec = "DWAB"
    elif ext == "bmp":
        image_settings.file_format = "BMP"
    elif ext == "rgb":
        image_settings.file_format = "IRIS"
    elif ext == "png":
        image_settings.file_format = "PNG"
    elif ext == "jpeg":
        image_settings.file_format = "JPEG"
    elif ext == "jp2":
        image_settings.file_format = "JPEG2000"
    elif ext == "tga":
        image_settings.file_format = "TARGA"
    elif ext == "tif":
        image_settings.file_format = "TIFF"


def get_file_format_extension(file_format: str) -> str:
    """Convert Blender file format to file extension."""
    # TODO: Figure out if Blender has a native way to convert to extensions
    if file_format == "OPEN_EXR_MULTILAYER":
        return "exr"
    elif file_format == "OPEN_EXR":
        return "exr"
    elif file_format == "BMP":
        return "bmp"
    elif file_format == "IRIS":
        return "rgb"
    elif file_format == "PNG":
        return "png"
    elif file_format == "JPEG":
        return "jpeg"
    elif file_format == "JPEG2000":
        return "jp2"
    elif file_format == "TARGA" or file_format == "TARGA_RAW":
        return "tga"
    elif file_format == "TIFF":
        return "tif"
    # Blender 5+
    elif file_format == "CINEON":
        return "cin"
    elif file_format == "DPX":
        return "dpx"
    elif file_format == "WEBP":
        return "webp"
    elif file_format == "HDR":
        return "hdr"
    else:
        raise ValueError(f"Unsupported file format: {file_format}")


def set_render_passes(settings, renderer, view_layers):
    """Set render passes for the current view layer

    Args:
        settings (dict): The project settings.
        renderer (str): The renderer to use, either CYCLES or BLENDER_EEVEE.
        view_layers (list[bpy.types.ViewLayer]): The list of view layers to
        set the passes for.
    """
    aov_list = set(settings["blender"]["RenderSettings"]["aov_list"])
    existing_aov_list = set(existing_aov_options(renderer, view_layers))
    aov_list = aov_list.union(existing_aov_list)
    custom_passes = settings["blender"]["RenderSettings"]["custom_passes"]
    # Common passes for both renderers
    for vl in view_layers:
        if renderer == "BLENDER_EEVEE":
            # Eevee exclusive passes
            aov_options = get_aov_options(renderer)
            eevee_attrs: set[str] = {
                "use_pass_bloom",
                "use_pass_transparent",
                "use_pass_volume_direct"
            }
            for pass_name, attr in aov_options.items():
                target = vl.eevee if attr in eevee_attrs else vl
                ver_major, ver_minor, _ = lib.get_blender_version()
                if ver_major >= 3 and ver_minor > 6:
                    if attr == "use_pass_bloom":
                        continue
                setattr(target, attr, pass_name in aov_list)
        elif renderer == "CYCLES":
            # Cycles exclusive passes
            aov_options = get_aov_options(renderer)
            cycle_attrs: set[str] = {
                "denoising_store_passes", "pass_debug_sample_count",
                "use_pass_volume_direct", "use_pass_volume_indirect",
                "use_pass_shadow_catcher"
            }
            for pass_name, attr in aov_options.items():
                target = vl.cycles if attr in cycle_attrs else vl
                setattr(target, attr, pass_name in aov_list)

        aovs_names: set[str] = {aov.name for aov in vl.aovs}
        for custom_pass in custom_passes:
            custom_pass_name = custom_pass["attribute"]
            if custom_pass_name not in aovs_names:
                aov = vl.aovs.add()
                aov.name = custom_pass_name
            else:
                aov = vl.aovs[custom_pass_name]
            aov.type = custom_pass["value"]

    return list(aov_list), custom_passes


def get_aov_options(renderer: str) -> dict[str, str]:
    """Return the available AOV options based on the renderer name."""
    aov_options = {
        "combined": "use_pass_combined",
        "z": "use_pass_z",
        "mist": "use_pass_mist",
        "normal": "use_pass_normal",
        "diffuse_light": "use_pass_diffuse_direct",
        "diffuse_color": "use_pass_diffuse_color",
        "specular_light": "use_pass_glossy_direct",
        "specular_color": "use_pass_glossy_color",
        "emission": "use_pass_emit",
        "environment": "use_pass_environment",
        "ao": "use_pass_ambient_occlusion",
        "cryptomatte_object": "use_pass_cryptomatte_object",
        "cryptomatte_material": "use_pass_cryptomatte_material",
        "cryptomatte_asset": "use_pass_cryptomatte_asset",
    }
    if renderer == "BLENDER_EEVEE":
        eevee_options = {
            "shadow": "use_pass_shadow",
            "volume_light": "use_pass_volume_direct",
            "bloom": "use_pass_bloom",
            "transparent": "use_pass_transparent",
            "cryptomatte_accurate": "use_pass_cryptomatte_accurate",
        }
        aov_options.update(eevee_options)
    elif renderer == "CYCLES":
        cycles_options = {
            "position": "use_pass_position",
            "vector": "use_pass_vector",
            "uv": "use_pass_uv",
            "denoising": "denoising_store_passes",
            "object_index": "use_pass_object_index",
            "material_index": "use_pass_material_index",
            "sample_count": "pass_debug_sample_count",
            "diffuse_indirect": "use_pass_diffuse_indirect",
            "specular_indirect": "use_pass_glossy_indirect",
            "transmission_direct": "use_pass_transmission_direct",
            "transmission_indirect": "use_pass_transmission_indirect",
            "transmission_color": "use_pass_transmission_color",
            "volume_light": "use_pass_volume_direct",
            "volume_indirect": "use_pass_volume_indirect",
            "shadow": "use_pass_shadow_catcher",
        }
        aov_options.update(cycles_options)

    return aov_options


def existing_aov_options(
    renderer: str, view_layers: list["bpy.types.ViewLayer"]
) -> list[str]:
    aov_list = []
    aov_options = get_aov_options(renderer)
    for vl in view_layers:
        if renderer == "BLENDER_EEVEE":
            eevee_attrs = ["use_pass_shadow", "cryptomatte_accurate"]
            for pass_name, attr in aov_options.items():
                target = vl if attr in eevee_attrs else vl.eevee
                if getattr(target, attr, False):
                    aov_list.append(pass_name)

        elif renderer == "CYCLES":
            cycle_attrs = [
                "denoising_store_passes", "pass_debug_sample_count",
                "use_pass_volume_direct", "use_pass_volume_indirect",
                "use_pass_shadow_catcher"
            ]
            for pass_name, attr in aov_options.items():
                target = vl.cycles if attr in cycle_attrs else vl
                if getattr(target, attr, False):
                    aov_list.append(pass_name)

    return aov_list

def ensure_unique_output_node_name(
    tree: "bpy.types.NodeTree",
    output_node: "bpy.types.CompositorNodeOutputFile",
    name: str,
) -> str:
    """Ensure the given CompositorNodeOutputFile node has a unique name.

    Args:
        tree (bpy.types.NodeTree): The node tree to process.
        output_node (bpy.types.CompositorNodeOutputFile): The output node to
            rename if needed.
        name (str): The variant name to use in the output node name.

    Returns:
        str: The unique name assigned to the given output node.

    """
    base_name = name
    counter = 1
    while tree.nodes.get(base_name):
        base_name = f"{name}_{counter}"
        counter += 1

    output_node.name = base_name
    output_node.label = base_name
    return base_name

def get_base_render_output_path(
    variant_name: str,
    multi_exr: Optional[bool] = None,
    project_settings: Optional[dict] = None
) -> str:
    """Return the base render output path for the given variant name.

    Returns a Blender-relative path that uses a fixed renders folder structure
    without version numbering, allowing renders to overwrite in place.
    """
    # Use Blender-relative path: //renders/blender/<variant>
    return f"//renders/blender/{variant_name}"


def create_render_node_tree(
    variant_name: str,
    render_layer_nodes: set["bpy.types.CompositorNodeRLayers"],
    project_settings: dict,
) -> "bpy.types.CompositorNodeOutputFile":
    """Create a Compositor node tree for rendering based on project settings.

    Arguments:
        variant_name (str): The name of the variant to use in the output file
            names.
        view_layers (list[bpy.types.ViewLayer]): The list of view layers to
            create render layer nodes for.
        project_settings (dict): The project settings dictionary.
    """
    aov_sep = get_aov_separator(project_settings)
    # Force compositor outputs to multilayer EXR behavior.
    ext = "exr"
    multilayer = True
    compositing = get_compositing(project_settings)

    tree = lib.get_scene_node_tree(ensure_exists=True)

    comp_composite_type = "CompositorNodeComposite"

    # Find existing 'Composite' node
    composite_node = None
    for node in tree.nodes:
        if node.bl_idname == comp_composite_type:
            composite_node = node
            break

    # Create a new output node
    output: bpy.types.CompositorNodeOutputFile = tree.nodes.new(
        "CompositorNodeOutputFile"
    )

    # Ensure the output node has a unique name
    unique_name = ensure_unique_output_node_name(tree, output, variant_name)

    # Multi-exr
    multi_exr: bool = ext == "exr" and multilayer
    blender_version = lib.get_blender_version()
    if blender_version >= (5, 0, 0):
        output.format.media_type = (
            "MULTI_LAYER_IMAGE" if multi_exr else "IMAGE"
        )
    # By default, match output format from scene file format
    image_settings = bpy.context.scene.render.image_settings
    output.format.file_format = image_settings.file_format
    output.format.color_depth = "16"
    output.format.exr_codec = "DWAB"

    # Define the base path for the File Output node.
    base_path = get_base_render_output_path(
        unique_name, project_settings=project_settings
    )
    if blender_version >= (5, 0, 0):
        # For Blender 5+, set directory and filename separately
        output.directory = base_path
        # Append frame number and EXR extension to filename
        output.file_name = f"{unique_name}.####.exr"
        slots = output.file_output_items
    else:
        output.base_path = base_path
        slots = output.layer_slots if multi_exr else output.file_slots

    def _create_aov_slot(
        renderpass_name: str,
        render_layer: str,
        socket_type: str = "FLOAT",
    ) -> "bpy.types.RenderSlot":
        """Add a new render output slot to the slots.

        The slots usually are the file slots of the compositor output node.
        The filepath is based on the render layer, variant name and render pass.

        If it's multi-exr, the slot will be named after the render pass only.

        Returns:
            The created slot

        """
        if lib.get_blender_version() >= (5, 0, 0):
            new_output_item = output.file_output_items.new(
                socket_type, renderpass_name
            )
            return output.inputs[new_output_item.name]

        filename: str = (
            f"{render_layer}/"
            f"{variant_name}_{render_layer}{aov_sep}{renderpass_name}.####"
        )
        return slots.new(renderpass_name if multi_exr else filename)

    slots.clear()

    # Create a new socket for the Beauty output
    pass_name = "rgba"
    for render_layer_node in render_layer_nodes:
        render_layer = render_layer_node.layer
        slot = _create_aov_slot(pass_name, render_layer, socket_type="RGBA")
        tree.links.new(render_layer_node.outputs["Image"], slot)

    last_found_renderlayer_node = next(
        (node for node in reversed(list(render_layer_nodes))), None
    )
    if compositing and last_found_renderlayer_node:
        # Create a new socket for the Composite output
        # with only the one view layer
        pass_name = "Composite"
        render_layer = last_found_renderlayer_node.layer
        slot = _create_aov_slot(pass_name, render_layer)
        # If there's a composite node, we connect its 'Image' input with the
        # new slot on the output
        if composite_node:
            for link in composite_node.inputs["Image"].links:
                tree.links.new(link.from_socket, slot)
                break

    # For each active render pass, we add a new socket to the output node
    # and link it
    exclude_sockets: set[str] = {"Image", "Alpha", "Noisy Image"}
    for render_layer_node in render_layer_nodes:
        # Get the enabled output sockets, that are the active passes for the
        # render.
        render_layer = render_layer_node.layer
        for output_socket in render_layer_node.outputs:
            if output_socket.name in exclude_sockets:
                continue

            if not output_socket.enabled:
                continue

            socket_type: str = "FLOAT"  # Only relevant for Blender 5+
            if lib.get_blender_version() >= (5, 0, 0):
                socket_type = output_socket.type
                if socket_type == "VALUE":
                    socket_type = "FLOAT"

            slot = _create_aov_slot(
                output_socket.name,
                render_layer,
                socket_type=socket_type
            )
            tree.links.new(output_socket, slot)

    return output


def prepare_rendering(
    variant_name: str, project_settings: Optional[dict] = None
) -> "bpy.types.CompositorNodeOutputFile":
    """Initialize render setup using render settings from project settings."""
    assert bpy.data.filepath, "Workfile not saved. Please save the file first."

    if project_settings is None:
        project_name: str = get_current_project_name()
        project_settings = get_project_settings(project_name)

    # Force AYON render outputs to multilayer EXR.
    ext = "exr"
    multilayer = True
    renderer = get_renderer(project_settings)
    ver_major, ver_minor, _ = lib.get_blender_version()
    if renderer == "BLENDER_EEVEE" and (
        ver_major >= 4 and ver_minor >=2
    ):
        renderer = "BLENDER_EEVEE_NEXT"

    # Set scene render settings
    set_render_format(ext, multilayer)
    bpy.context.scene.render.engine = renderer
    view_layers = bpy.context.scene.view_layers
    set_render_passes(project_settings, renderer, view_layers)

    # Use selected renderlayer nodes, or assume we want a renderlayer node for
    # each view layer so we retrieve all of them.
    node_tree = lib.get_scene_node_tree(ensure_exists=True)
    selected_renderlayer_nodes = []
    
    # Check if node_tree is available before accessing nodes
    if node_tree is not None:
        for node in node_tree.nodes:
            if node.bl_idname == "CompositorNodeRLayers" and node.select:
                selected_renderlayer_nodes.append(node)

    if selected_renderlayer_nodes:
        render_layer_nodes = selected_renderlayer_nodes
    else:
        render_layer_nodes = get_or_create_render_layer_nodes(view_layers)

    # Generate Compositing nodes
    output_node = create_render_node_tree(
        variant_name,
        render_layer_nodes,
        project_settings
    )

    set_tmp_scene_render_output_path(project_settings)
    bpy.context.scene.render.use_overwrite = True

    return output_node


def get_tmp_scene_render_output_path(project_settings: dict) -> str:
    """Get the render output path for the temporary scene render.

    Returns a Blender-relative path for the scene-wide render output
    that can be disabled by Compositor output nodes.
    """
    # Use Blender-relative path: //renders/blender/tmp/<variant>
    return "//renders/blender/tmp/tmp"


def set_tmp_scene_render_output_path(project_settings: dict):
    # Clear the scene render filepath, so that the outputs are handled only by
    # the file output nodes in the compositor.
    path = get_tmp_scene_render_output_path(project_settings)
    bpy.context.scene.render.filepath = path


def get_or_create_render_layer_nodes(
    view_layers: list["bpy.types.ViewLayer"],
) -> set[bpy.types.CompositorNodeRLayers]:
    """Get existing render layer nodes or create new ones."""
    tree = lib.get_scene_node_tree(ensure_exists=True)

    view_layer_names: set[str] = {
        view_layer.name for view_layer in view_layers
    }

    # Find existing render layer nodes for each view layer
    render_layer_nodes: set[bpy.types.CompositorNodeRLayers] = set()
    found_view_layer_names: set[str] = set()
    for node in tree.nodes:
        if node.bl_idname != "CompositorNodeRLayers":
            continue

        # Skip if already found a render layer node for this view layer.
        if node.layer in found_view_layer_names:
            continue

        # Skip if the view layer is not meant to be included.
        if node.layer not in view_layer_names:
            continue

        found_view_layer_names.add(node.layer)
        render_layer_nodes.add(node)

    # Generate the missing render layer nodes
    missing_view_layer_names: set[str] = (
        view_layer_names - found_view_layer_names
    )
    for view_layer_name in missing_view_layer_names:
        render_layer_node = tree.nodes.new("CompositorNodeRLayers")
        render_layer_node.layer = view_layer_name
        render_layer_nodes.add(render_layer_node)

    return render_layer_nodes