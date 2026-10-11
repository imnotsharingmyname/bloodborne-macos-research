# Separate Mach-O process: guest runtime + all libraries loaded into it.
set(CMAKE_SYSTEM_NAME Darwin)
set(CMAKE_SYSTEM_PROCESSOR x86_64)
set(CMAKE_OSX_ARCHITECTURES x86_64 CACHE STRING "" FORCE)
set(CMAKE_OSX_DEPLOYMENT_TARGET 26.0 CACHE STRING "" FORCE)
set(CMAKE_OSX_SYSROOT macosx CACHE STRING "" FORCE)
set(CMAKE_C_COMPILER "/usr/bin/clang")
set(CMAKE_CXX_COMPILER "/usr/bin/clang++")
set(CMAKE_OBJCXX_COMPILER "/usr/bin/clang++")
