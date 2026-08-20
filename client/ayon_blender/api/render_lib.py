import os
from pathlib import Path
from typing import Optional, Iterable
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


# Labels match server/settings/render_settings.py aov_list_enum.
AOV_LIST_ITEMS: list[tuple[str, str]] = [
    ("combined", "Combined"),
    ("z", "Z"),
    ("mist", "Mist"),
    ("normal", "Normal"),
    ("position", "Position (Cycles Only)"),
    ("vector", "Vector (Cycles Only)"),
    ("uv", "UV (Cycles Only)"),
    ("denoising", "Denoising Data (Cycles Only)"),
    ("object_index", "Object Index (Cycles Only)"),
    ("material_index", "Material Index (Cycles Only)"),
    ("sample_count", "Sample Count (Cycles Only)"),
    ("diffuse_light", "Diffuse Light/Direct"),
    ("diffuse_indirect", "Diffuse Indirect (Cycles Only)"),
    ("diffuse_color", "Diffuse Color"),
    ("specular_light", "Specular (Glossy) Light/Direct"),
    ("specular_indirect", "Specular (Glossy) Indirect (Cycles Only)"),
    ("specular_color", "Specular (Glossy) Color"),
    ("transmission_light", "Transmission Light/Direct (Cycles Only)"),
    ("transmission_indirect", "Transmission Indirect (Cycles Only)"),
    ("transmission_color", "Transmission Color (Cycles Only)"),
    ("volume_light", "Volume Light/Direct"),
    ("volume_indirect", "Volume Indirect (Cycles Only)"),
    ("emission", "Emission"),
    ("environment", "Environment"),
    ("shadow", "Shadow/Shadow Catcher"),
    ("ao", "Ambient Occlusion"),
    ("bloom", "Bloom (Eevee Only)"),
    ("transparent", "Transparent (Eevee Only)"),
    ("cryptomatte_object", "Cryptomatte Object"),
    ("cryptomatte_material", "Cryptomatte Material"),
    ("cryptomatte_asset", "Cryptomatte Asset"),
    ("cryptomatte_accurate", "Cryptomatte Accurate Mode (Eevee Only)"),
]

_CYCLES_ONLY_AOVS = {
    "position",
    "vector",
    "uv",
    "denoising",
    "object_index",
    "material_index",
    "sample_count",
    "diffuse_indirect",
    "specular_indirect",
    "transmission_light",
    "transmission_indirect",
    "transmission_color",
    "volume_indirect",
}
_EEVEE_ONLY_AOVS = {
    "bloom",
    "transparent",
    "cryptomatte_accurate",
}


def get_aov_presets(project_settings: dict) -> list[dict]:
    """Return named AOV presets from project settings.

    Older settings stored a single ``aov_list`` / ``custom_passes`` pair.
    Those are treated as a ``Default`` preset until the studio saves the
    new schema.
    """
    render_settings = project_settings["blender"]["RenderSettings"]
    presets = render_settings.get("aov_presets") or []
    if presets:
        return presets
    return [{
        "name": "Default",
        "aov_list": render_settings.get("aov_list") or ["combined"],
        "custom_passes": render_settings.get("custom_passes") or [],
    }]


def get_default_aov_preset(project_settings: dict) -> dict:
    """Return the AOV preset used as the Create-dialog default."""
    render_settings = project_settings["blender"]["RenderSettings"]
    presets = get_aov_presets(project_settings)
    default_name = render_settings.get("default_aov_preset") or "Default"
    for preset in presets:
        if preset.get("name") == default_name:
            return preset
    return presets[0]


def get_aov_enum_items(renderer: Optional[str] = None) -> dict[str, str]:
    """Return AOV value-to-label items, optionally filtered by renderer."""
    skip: set[str] = set()
    if renderer == "CYCLES":
        skip = _EEVEE_ONLY_AOVS
    elif renderer in {"BLENDER_EEVEE", "BLENDER_EEVEE_NEXT"}:
        skip = _CYCLES_ONLY_AOVS
    return {
        value: label
        for value, label in AOV_LIST_ITEMS
        if value not in skip
    }


def set_render_format(ext: str, multilayer: bool):
    """Set Blender scene to save render file with the right extension"""
    bpy.context.scene.render.use_file_extension = True
    image_settings = bpy.context.scene.render.image_settings

    # Force AYON renders to multilayer EXR with half-float and DWAB.
    ext = "exr"
    multilayer = True

    if lib.get_blender_version() >= (5, 0, 0):
        if multilayer:
            image_settings.media_type = "MULTI_LAYER_IMAGE"
        else:
            image_settings.media_type = "IMAGE"

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


def set_render_passes(
    settings,
    renderer,
    view_layers,
    aov_list: Optional[Iterable[str]] = None,
):
    """Set render passes for the given view layers.

    Args:
        settings (dict): The project settings.
        renderer (str): The renderer to use, either CYCLES or BLENDER_EEVEE.
        view_layers (list[bpy.types.ViewLayer]): The list of view layers to
            set the passes for.
        aov_list (Optional[Iterable[str]]): Explicit AOVs to enable. When
            provided, only those passes are enabled on the selected view
            layers. When omitted, the default AOV preset is used and already
            enabled per-layer AOVs are kept.
    """
    preset = get_default_aov_preset(settings)
    custom_passes = preset.get("custom_passes") or []
    if aov_list is None:
        base_aov_list = set(preset.get("aov_list") or [])
        authoritative = False
    else:
        base_aov_list = set(aov_list)
        authoritative = True

    aov_list_combined: set[str] = set()
    for vl in view_layers:
        if authoritative:
            enabled_aovs = set(base_aov_list)
        else:
            # Preserve per-layer AOV differences instead of propagating all
            # layers' AOVs everywhere.
            existing_aov_list = set(existing_aov_options(renderer, vl))
            enabled_aovs = base_aov_list.union(existing_aov_list)
        aov_list_combined.update(enabled_aovs)

        if _is_legacy_eevee_renderer(renderer):
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
                setattr(target, attr, pass_name in enabled_aovs)
        elif renderer == "CYCLES":
            aov_options = get_aov_options(renderer)
            cycle_attrs: set[str] = {
                "denoising_store_passes", "pass_debug_sample_count",
                "use_pass_volume_direct", "use_pass_volume_indirect",
                "use_pass_shadow_catcher"
            }
            for pass_name, attr in aov_options.items():
                target = vl.cycles if attr in cycle_attrs else vl
                setattr(target, attr, pass_name in enabled_aovs)
        else:
            # Modern Eevee (BLENDER_EEVEE / BLENDER_EEVEE_NEXT)
            aov_options = get_aov_options(renderer)
            for pass_name, attr in aov_options.items():
                if hasattr(vl, attr):
                    setattr(vl, attr, pass_name in enabled_aovs)

        aovs_names: set[str] = {aov.name for aov in vl.aovs}
        for custom_pass in custom_passes:
            custom_pass_name = custom_pass["attribute"]
            if custom_pass_name not in aovs_names:
                aov = vl.aovs.add()
                aov.name = custom_pass_name
            else:
                aov = vl.aovs[custom_pass_name]
            aov.type = custom_pass["value"]

    return list(aov_list_combined), custom_passes


def _is_legacy_eevee_renderer(renderer):
    """Return whether renderer is Eevee in Blender lower than 4.2.

    Note:
      In Blender <4.2 'BLENDER_EEVEE' represents Eevee renderer.
      In Blender 4.2-5.1 'BLENDER_EEVEE_NEXT' represents Eevee renderer.
      In Blender >5.2 'BLENDER_EEVEE' represents Eevee renderer.

    Args:
        renderer (str): Renderer name.

    Returns:
        bool: Whether renderer is Eevee in Blender version lower than 4.2.
    """
    if renderer != "BLENDER_EEVEE":
        return False

    ver_major, ver_minor, _ = lib.get_blender_version()
    if (ver_major, ver_minor) < (4, 2):
        return True
    return False


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
    if _is_legacy_eevee_renderer(renderer):
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
            "transmission_light": "use_pass_transmission_direct",
            "transmission_indirect": "use_pass_transmission_indirect",
            "transmission_color": "use_pass_transmission_color",
            "volume_light": "use_pass_volume_direct",
            "volume_indirect": "use_pass_volume_indirect",
            "shadow": "use_pass_shadow_catcher",
        }
        aov_options.update(cycles_options)

    return aov_options


def existing_aov_options(
    renderer: str, view_layer:"bpy.types.ViewLayer"
) -> list[str]:
    aov_list = []
    aov_options = get_aov_options(renderer)
    if _is_legacy_eevee_renderer(renderer):
        eevee_attrs = ["use_pass_shadow", "cryptomatte_accurate"]
        for pass_name, attr in aov_options.items():
            target = view_layer.eevee if attr in eevee_attrs else view_layer
            if getattr(target, attr, False):
                aov_list.append(pass_name)

    elif renderer == "CYCLES":
        cycle_attrs = [
            "denoising_store_passes", "pass_debug_sample_count",
            "use_pass_volume_direct", "use_pass_volume_indirect",
            "use_pass_shadow_catcher"
        ]
        for pass_name, attr in aov_options.items():
            target = view_layer.cycles if attr in cycle_attrs else view_layer
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

    Uses a fixed renders folder structure without version numbering, allowing
    renders to overwrite in place.

    The path is absolute and based on the workfile folder. It must not be a
    Blender-relative `//` path, because the farm renders the published copy of
    the workfile and relative paths would resolve next to that copy instead of
    the work directory that AYON collects the expected files from.
    """
    workfile_filepath: str = bpy.data.filepath
    if not workfile_filepath:
        raise RuntimeError("Workfile not saved. Please save the file first.")

    if project_settings is None:
        project_settings = get_project_settings(get_current_project_name())

    render_folder = get_default_render_folder(project_settings)
    base_folder = Path(workfile_filepath).parent / render_folder
    return str(base_folder / variant_name)


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
    # By default, match output format from scene file format
    image_settings = bpy.context.scene.render.image_settings
    file_format = image_settings.file_format
    if blender_version >= (5, 0, 0):
        output.format.media_type = (
            "MULTI_LAYER_IMAGE" if multi_exr else "IMAGE"
        )
        # OPEN_EXR_MULTILAYER only valid when multi_exr is True
        # For non multilayer exr and exr format is used, file format
        # should be OPEN_EXR, otherwise it should follow the scene file format
        if multi_exr:
            file_format = "OPEN_EXR_MULTILAYER"
        elif ext == "exr":
            file_format = "OPEN_EXR"
        else:
            file_format = image_settings.file_format

    output.format.file_format = file_format
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

def get_selected_render_layer_nodes(
        node_tree: "bpy.types.NodeTree",
        selected_all: bool = False,
        selected_view_layers: Optional[list[str]] = None
) -> set["bpy.types.CompositorNodeRLayers"]:
    """Get the selected render layer nodes from the given node tree.

    Args:
        node_tree (bpy.types.NodeTree): The node tree to search for selected render layer nodes.
        selected_all (bool): If True, all render layer nodes are returned regardless of selection.
            If False, only selected nodes are returned.
        selected_view_layers (Optional[list[str]]): Optional list of Blender view-layer names
        to limit which render layer nodes are included. If provided,
        only nodes whose view-layer names are included.

    Returns:
        set[bpy.types.CompositorNodeRLayers]: A set of selected render layer nodes.

    """
    selected_nodes = set()
    for node in node_tree.nodes:
        if node.bl_idname == "CompositorNodeRLayers" and (selected_all or node.select):
            if (
                selected_view_layers
                and not has_selected_view_layers(selected_view_layers, node)
            ):
                continue
            selected_nodes.add(node)

    return selected_nodes


def prepare_rendering(
    variant_name: str,
    project_settings: Optional[dict] = None,
    *,
    selected_view_layers: Optional[list[str]] = None,
    aov_list: Optional[Iterable[str]] = None,
) -> "bpy.types.CompositorNodeOutputFile":
    """Initialize render setup using render settings from project settings.

    Args:
        variant_name (str): Render variant name used when generating the output
            node tree and output paths.
        project_settings (Optional[dict]): Project settings dictionary. If ``None``, the
            settings are loaded for the current project.
        selected_view_layers (Optional[list[str]]): Optional list of Blender view-layer
            names to limit which render layer nodes are used or created. Use ``None``
            to apply the setup to all available view layers. An empty list is
            currently treated the same as ``None`` because it is falsy, so it
            also results in all view layers being considered rather than no
            layers.
        aov_list (Optional[Iterable[str]]): Explicit AOVs to enable on the
            selected view layers. When omitted, the default AOV preset is used.

    Returns:
        bpy.types.CompositorNodeOutputFile: The compositor file output node created
            for the render setup.

    """
    assert bpy.data.filepath, "Workfile not saved. Please save the file first."

    if project_settings is None:
        project_name: str = get_current_project_name()
        project_settings = get_project_settings(project_name)

    # Force AYON render outputs to multilayer EXR.
    ext = "exr"
    multilayer = True
    renderer = get_renderer(project_settings)
    ver_major, ver_minor, _ = lib.get_blender_version()

    # Between Blender 4.2 and 5.1, the Eevee renderer is BLENDER_EEVEE_NEXT
    if renderer == "BLENDER_EEVEE" and (
        (4, 2) <= (ver_major, ver_minor) <= (5, 1)
    ):
        renderer = "BLENDER_EEVEE_NEXT"

    # Set scene render settings
    set_render_format(ext, multilayer)
    bpy.context.scene.render.engine = renderer
    view_layers = get_selected_view_layers(selected_view_layers=selected_view_layers)
    set_render_passes(
        project_settings, renderer, view_layers, aov_list=aov_list
    )

    # Use selected renderlayer nodes, or assume we want a renderlayer node for
    # each view layer so we retrieve all of them.
    node_tree = lib.get_scene_node_tree(ensure_exists=True)
    selected_renderlayer_nodes = get_selected_render_layer_nodes(
        node_tree,
        # If no specific view layers are selected,
        # consider all nodes as selected
        selected_all=not selected_view_layers,
        selected_view_layers=selected_view_layers
    )

    if selected_renderlayer_nodes:
        render_layer_nodes = selected_renderlayer_nodes
    else:
        render_layer_nodes = get_or_create_render_layer_nodes(
            view_layers,
            selected_view_layers=selected_view_layers
        )

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

    This is the scene-wide render path that AYON essentially does not use,
    but it cannot be disabled in Blender. So we store at least a temporary
    path for the scene render output.

    Like the Compositor output paths this must be absolute so that the farm
    does not write it next to the published copy of the workfile.
    """
    render_folder = get_default_render_folder(project_settings)

    workdir: str = os.getenv("AYON_WORKDIR") or os.path.dirname(
        bpy.data.filepath
    )
    if not workdir:
        raise RuntimeError("Workfile not saved. Please save the file first.")

    path = os.path.join(workdir, render_folder, "tmp", "tmp")
    return path.replace("\\", "/")


def set_tmp_scene_render_output_path(project_settings: dict):
    # Clear the scene render filepath, so that the outputs are handled only by
    # the file output nodes in the compositor.
    path = get_tmp_scene_render_output_path(project_settings)
    bpy.context.scene.render.filepath = path


def get_or_create_render_layer_nodes(
    view_layers: list["bpy.types.ViewLayer"],
    selected_view_layers: Optional[list[str]] = None
) -> set[bpy.types.CompositorNodeRLayers]:
    """Get existing render layer nodes or create new ones.
    By default, this reuses or creates compositor render layer nodes for all
    provided ``view_layers``. When ``selected_view_layers`` is provided, only
    nodes whose view-layer names are in that selection are reused or created.

    Args:
        view_layers (list[bpy.types.ViewLayer]): Available view layers to
            consider.
        selected_view_layers (Optional[list[str]]): Specific view-layer names
            to include. If None, all provided view layers are included.

    Returns:
        set[bpy.types.CompositorNodeRLayers]: Existing or newly created render
            layer nodes matching the requested view layers.

    """
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
    if selected_view_layers:
        missing_view_layer_names = missing_view_layer_names.intersection(
            set(selected_view_layers)
        )

    for view_layer_name in missing_view_layer_names:
        render_layer_node = tree.nodes.new("CompositorNodeRLayers")
        render_layer_node.layer = view_layer_name
        render_layer_nodes.add(render_layer_node)

    return render_layer_nodes


def has_selected_view_layers(
        selected_view_layers: Optional[list[str]],
        node: bpy.types.CompositorNodeRLayers
) -> bool:
    """Check if the given compositor view layer node has a view
    layer that is in the selected view layers.

    Args:
        selected_view_layers (Optional[list[str]]): selected view layers to consider 
            for inclusion. If None or empty, the function returns False; use this 
            function only when you know selected_view_layers is non-empty.
        node (bpy.types.CompositorNodeRLayers): the compositor node to check against 
            the selected view layers.

    Returns:
        bool: True if selected_view_layers is non-empty and the node's layer is in it,
            False otherwise (including when selected_view_layers is None or empty).
    """
    if not selected_view_layers:
        return False
    for view_layer_name in selected_view_layers:
        if view_layer_name == node.layer:
            return True
    return False


def get_selected_view_layers(
    selected_view_layers: Optional[list[str]] = None
) -> list["bpy.types.ViewLayer"]:
    """Get the selected view layers based on the provided names.

    Args:
        selected_view_layers (Optional[list[str]]): List of view layer names to select.
            If None, all view layers are returned.

    Returns:
        list[bpy.types.ViewLayer]: List of selected view layers.
    """
    if not selected_view_layers:
        return bpy.context.scene.view_layers
    selected_view_layers_list = []
    for view_layer in bpy.context.scene.view_layers:
        if view_layer.name in selected_view_layers:
            selected_view_layers_list.append(view_layer)

    return selected_view_layers_list
