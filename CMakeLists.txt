cmake_minimum_required(VERSION 3.28)
project(BloodborneLauncher LANGUAGES CXX OBJCXX)
if(NOT APPLE)
  message(FATAL_ERROR "The launcher requires AppKit and an Apple SDK")
endif()
set(CMAKE_CXX_STANDARD 17)
add_executable(Bloodborne MACOSX_BUNDLE launcher/main.mm)
target_compile_options(Bloodborne PRIVATE -fobjc-arc -Wall -Wextra)
target_link_libraries(Bloodborne PRIVATE "-framework Cocoa")
set_target_properties(Bloodborne PROPERTIES
  MACOSX_BUNDLE_INFO_PLIST "${CMAKE_CURRENT_SOURCE_DIR}/launcher/Info.plist.in"
  MACOSX_BUNDLE_BUNDLE_NAME Bloodborne
  MACOSX_BUNDLE_GUI_IDENTIFIER org.bloodborne.research.mac
  MACOSX_BUNDLE_BUNDLE_VERSION 1
  MACOSX_BUNDLE_SHORT_VERSION_STRING 0.1.0
  XCODE_ATTRIBUTE_CODE_SIGNING_ALLOWED NO)
