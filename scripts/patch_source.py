#!/usr/bin/env python3
"""Small exact-context adjustments, valid only for dependencies.lock.json's fork."""
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]

def replace_once(path, before, after):
    content = path.read_text()
    if after in content:
        return
    if content.count(before) != 1:
        raise RuntimeError('Pinned source context changed: ' + str(path))
    path.write_text(content.replace(before, after, 1))

def apply(source):
    vkdir = source / 'gpu/shadps4/video_core/renderer_vulkan'
    shutil.copy2(ROOT / 'graphics/bb_pipeline_store.hpp', vkdir / 'bb_pipeline_store.hpp')
    cpp = vkdir / 'vk_pipeline_cache.cpp'
    replace_once(cpp, '#include <atomic>', '#include "bb_pipeline_store.hpp"\n#include <atomic>')
    before = '''    WarmUp();

    auto [cache_result, cache] = instance.GetDevice().createPipelineCacheUnique({});'''
    after = '''    // BuildKit: populate the driver cache BEFORE upstream shader/pipeline warmup.
    const auto props = instance.GetPhysicalDevice().getProperties();
    bb_cache::DeviceKey disk_key{props.vendorID, props.deviceID, props.driverVersion, {}};
    std::copy(props.pipelineCacheUUID.begin(), props.pipelineCacheUUID.end(), disk_key.uuid.begin());
    const auto disk_data = bb_cache::load(disk_key);
    vk::PipelineCacheCreateInfo cache_info{};
    cache_info.initialDataSize = disk_data.size();
    cache_info.pInitialData = disk_data.data();
    auto [cache_result, cache] = instance.GetDevice().createPipelineCacheUnique(cache_info);
    // Retry cold only when a previously saved blob was supplied.
    if (cache_result != vk::Result::eSuccess && !disk_data.empty()) {
        auto fresh = instance.GetDevice().createPipelineCacheUnique({});
        cache_result = fresh.result; cache = std::move(fresh.value);
    }'''
    replace_once(cpp, before, after)
    replace_once(cpp, '    pipeline_cache = std::move(cache);\n}',
                 '    pipeline_cache = std::move(cache);\n    WarmUp();\n}')
    replace_once(cpp, 'PipelineCache::~PipelineCache() = default;', '''PipelineCache::~PipelineCache() {
    try {
    // Caller must stop pipeline creation workers before destroying this owner.
    const auto props = instance.GetPhysicalDevice().getProperties();
    bb_cache::DeviceKey key{props.vendorID, props.deviceID, props.driverVersion, {}};
    std::copy(props.pipelineCacheUUID.begin(), props.pipelineCacheUUID.end(), key.uuid.begin());
    const auto result = instance.GetDevice().getPipelineCacheData(*pipeline_cache);
    if (result.result == vk::Result::eSuccess) bb_cache::save(key, result.value);
    } catch (...) { /* Cache persistence must not make shutdown fail. */ }
}''')
    gpu_cmake = source / 'gpu/CMakeLists.txt'
    replace_once(gpu_cmake, 'BB_VULKAN_LOADER_DEFAULT="${Vulkan_LIBRARY}"',
                 'BB_VULKAN_LOADER_DEFAULT="libvulkan.1.dylib"')

if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('source', type=Path)
    apply(p.parse_args().source)
