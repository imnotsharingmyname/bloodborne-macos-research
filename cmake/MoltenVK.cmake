# OPTIONAL direct-link route for a renderer explicitly converted to direct dispatch.
# Current Metalborne uses a Vulkan loader; build.py uses the loader + ICD route.
function(bb_link_moltenvk target package_root)
  add_library(bb_mvk STATIC IMPORTED)
  set_target_properties(bb_mvk PROPERTIES
    IMPORTED_LOCATION "${package_root}/MoltenVK/static/MoltenVK.xcframework/macos-arm64_x86_64/libMoltenVK.a"
    INTERFACE_INCLUDE_DIRECTORIES "${package_root}/MoltenVK/include")
  target_compile_definitions(${target} PRIVATE VK_USE_PLATFORM_METAL_EXT)
  target_link_libraries(${target} PRIVATE bb_mvk
    "-framework Metal" "-framework Foundation" "-framework QuartzCore"
    "-framework IOSurface" "-framework IOKit" "-framework AppKit")
endfunction()
