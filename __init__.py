import bpy

# Global dictionary to store original sizes of background images
original_bg_image_scales = {}

bl_info = {
    "name": "Overscan Render",
    "author": "Blender Bob ChatGPT",
    "version": (1, 2, 3),
    "blender": (4, 2, 0),
    "location": "View3D > Sidebar > Overscan Tab",
    "description": "Adjust render size with various options, modify camera attributes, and handle safe areas",
    "category": "Render",
}

def on_update(self, context):
    scene = context.scene
    cam = scene.camera
    if not cam:
        return

    camera = cam.data

    # Store original values once
    if 'original_width' not in camera:
        camera['original_width'] = scene.render.resolution_x
        camera['original_height'] = scene.render.resolution_y

        if camera.type == 'ORTHO':
            camera['original_ortho_scale'] = camera.ortho_scale
        else:
            camera['original_sensor_width'] = camera.sensor_width
            camera['original_sensor_fit'] = camera.sensor_fit

        # Store background image scales
        for index, bg_image in enumerate(camera.background_images):
            if hasattr(bg_image, 'scale'):
                camera[f"bg_image_scale_{index}"] = bg_image.scale

    update_overscan(self, context)


def update_overscan(self, context):
    scene = context.scene
    overscan = scene.overscan_settings
    cam = scene.camera
    if not cam:
        return

    camera = cam.data
    safe_areas = scene.safe_areas

    # Restore original values if available
    original_width = camera.get('original_width', scene.render.resolution_x)
    original_height = camera.get('original_height', scene.render.resolution_y)

    if camera.type == 'ORTHO':
        original_scale = camera.get('original_ortho_scale', camera.ortho_scale)
    else:
        original_sensor = camera.get('original_sensor_width', camera.sensor_width)

    # -----------------------------
    # Compute new resolution
    # -----------------------------
    if overscan.mode == 'PERCENTAGE':
        overscan_value = overscan.percentage / 100
        new_width = round(original_width * (1 + overscan_value))
        new_height = round(original_height * (1 + overscan_value))

        new_safe_area = (((100 / (overscan.percentage + 100)) - 1) * -1)
        safe_areas.action = (new_safe_area, new_safe_area)
        safe_areas.title = (1, 1)

    elif overscan.mode == 'PIXELS':
        extra = overscan.extra_pixels

        new_width = original_width + extra
        new_height = original_height + extra

        new_safe_area_x = (extra / 2) / (extra + original_width) * 2
        new_safe_area_y = (extra / 2) / (extra + original_height) * 2

        safe_areas.action = (new_safe_area_x, new_safe_area_y)
        safe_areas.title = (1, 1)

    else:  # SPECIFIC_X
        requested_width = overscan.specific_x_resolution
        clamped_width = max(requested_width, original_width)

        if requested_width < original_width:
            overscan.specific_x_resolution = original_width  # update UI too

        new_width = clamped_width
        aspect_ratio = original_height / original_width
        new_height = round(new_width * aspect_ratio)

        new_safe_area = ((new_width - original_width) / new_width)
        safe_areas.action = (new_safe_area, new_safe_area)
        safe_areas.title = (1, 1)

    # -----------------------------
    # Apply resolution
    # -----------------------------
    scene.render.resolution_x = new_width
    scene.render.resolution_y = new_height

    # -----------------------------
    # Correct camera scale
    # -----------------------------
    scale_factor = new_width / original_width

    if camera.type == 'ORTHO':
        camera.ortho_scale = original_scale * scale_factor
    else:
        camera.sensor_width = original_sensor * scale_factor

        # Force horizontal fit during overscan to keep scaling stable
        camera.sensor_fit = 'HORIZONTAL'

    # Rename camera if needed
    if not cam.name.endswith("_o"):
        cam.name = cam.name.rstrip("_o") + "_o"

    # Enable safe area overlay
    camera.show_safe_areas = True

    # Optional: mark as applied
    camera['overscan_applied'] = True



class OverscanPanel(bpy.types.Panel):
    bl_label = "Overscan"
    bl_idname = "RENDER_PT_overscan"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = 'output'

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        overscan = scene.overscan_settings

        layout.use_property_split = False
        layout.use_property_decorate = True

        col = layout.column_flow(columns=3, align=True)
        col.prop(
            overscan,
            "overscan_panel",
            icon="DOWNARROW_HLT" if overscan.overscan_panel else "RIGHTARROW",
            text="Overscan",
            emboss=False
        )

        if overscan.overscan_panel:
            layout.prop(overscan, "mode")

            if overscan.mode == 'PERCENTAGE':
                layout.prop(overscan, "percentage")
            elif overscan.mode == 'PIXELS':
                layout.prop(overscan, "extra_pixels")
            else:
                layout.prop(overscan, "specific_x_resolution")

            layout.operator("render.revert_overscan", icon="LOOP_BACK")



class OverscanSettings(bpy.types.PropertyGroup):
    mode_items = [
        ('PERCENTAGE', "Percentage", ""),
        ('PIXELS', "Extra Pixels", ""),
        ('SPECIFIC_X', "Specific X Resolution", "")
    ]

    mode: bpy.props.EnumProperty(
        name="Mode",
        items=mode_items,
        description="Choose the method for overscan",
        default='PERCENTAGE',
        update=on_update
    )

    percentage: bpy.props.FloatProperty(
        name="Percentage",
        description="Percentage of overscan to apply to the render",
        default=0.0,
        min=0.0,
        max=100.0,
        subtype='PERCENTAGE',
        update=on_update
    )

    extra_pixels: bpy.props.IntProperty(
        name="Extra Pixels",
        description="Number of extra pixels to add to the render dimensions",
        default=0,
        min=0,
        update=on_update
    )

    specific_x_resolution: bpy.props.IntProperty(
        name="Specific X Resolution",
        description="Set a specific X resolution while maintaining aspect ratio",
        default=1920,
        min=1,
        update=on_update
    )

    overscan_panel: bpy.props.BoolProperty(
        name="Overscan",
        default=True
    )



class RevertOverscan(bpy.types.Operator):
    bl_idname = "render.revert_overscan"
    bl_label = "Revert"

    def execute(self, context):
        scene = context.scene
        camera = scene.camera.data
        safe_areas = scene.safe_areas
        active_camera = scene.camera

        if 'original_width' not in camera or 'original_height' not in camera:
            self.report({'WARNING'}, "No overscan settings to revert.")
            return {'CANCELLED'}

        # Block updates temporarily
        camera['overscan_applied'] = False

        # Restore resolution
        scene.render.resolution_x = camera['original_width']
        scene.render.resolution_y = camera['original_height']

        # Restore camera attributes
        if camera.type == 'ORTHO':
            if 'original_ortho_scale' in camera:
                camera.ortho_scale = camera['original_ortho_scale']
        else:
            if 'original_sensor_width' in camera:
                camera.sensor_width = camera['original_sensor_width']

            # Restore original sensor fit
            if 'original_sensor_fit' in camera:
                camera.sensor_fit = camera['original_sensor_fit']

        # Restore background image scale
        for index, bg_image in enumerate(camera.background_images):
            prop = f"bg_image_scale_{index}"
            if prop in camera:
                bg_image.scale = camera[prop]

        # Restore safe areas
        safe_areas.action = (1, 1)
        safe_areas.title = (1, 1)

        # Restore camera name
        if active_camera.name.endswith("_o"):
            active_camera.name = active_camera.name[:-2]

        # Clean-up tags
        keys_to_remove = [
            'original_width',
            'original_height',
            'original_sensor_width',
            'original_ortho_scale',
            'original_sensor_fit',
            'overscan_applied'
        ]

        for key in keys_to_remove:
            if key in camera:
                del camera[key]

        # Clean background image keys
        for key in list(camera.keys()):
            if key.startswith("bg_image_scale_"):
                del camera[key]

        camera.show_safe_areas = False

        return {'FINISHED'}



def register():
    bpy.utils.register_class(OverscanSettings)
    bpy.utils.register_class(RevertOverscan)
    bpy.utils.register_class(OverscanPanel)
    bpy.types.Scene.overscan_settings = bpy.props.PointerProperty(type=OverscanSettings)


def unregister():
    bpy.utils.unregister_class(OverscanSettings)
    bpy.utils.unregister_class(RevertOverscan)
    bpy.utils.unregister_class(OverscanPanel)
    del bpy.types.Scene.overscan_settings



if __name__ == "__main__":
    register()
