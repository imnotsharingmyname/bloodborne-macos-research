// SPDX-License-Identifier: MIT
// Bounded, device-qualified Vulkan pipeline-cache persistence. Mac POSIX I/O.
#pragma once
#include <algorithm>
#include <array>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <string>
#include <vector>
#include <fcntl.h>
#include <unistd.h>

namespace bb_cache {
struct DeviceKey {
    uint32_t vendor, device, driver;
    std::array<uint8_t, 16> uuid;
};
inline uint32_t little32(const uint8_t* p) {
    return uint32_t(p[0]) | uint32_t(p[1]) << 8 | uint32_t(p[2]) << 16 | uint32_t(p[3]) << 24;
}
inline bool compatible(const std::vector<uint8_t>& data, const DeviceKey& key) {
    return data.size() >= 32 && little32(data.data()) >= 32 &&
           little32(data.data()) <= data.size() && little32(data.data() + 4) == 1 &&
           little32(data.data() + 8) == key.vendor && little32(data.data() + 12) == key.device &&
           std::memcmp(data.data() + 16, key.uuid.data(), key.uuid.size()) == 0;
}
inline std::filesystem::path path(const DeviceKey& key) {
    const char* dir = std::getenv("BB_PIPELINE_CACHE_DIR");
    const char* ns = std::getenv("BB_PIPELINE_CACHE_NAMESPACE");
    if (!dir || !ns || std::strlen(ns) != 64) return {};
    for (const char* p = ns; *p; ++p) if (!((*p >= '0' && *p <= '9') || (*p >= 'a' && *p <= 'f'))) return {};
    constexpr const char* hex = "0123456789abcdef";
    std::string uuid;
    for (uint8_t b : key.uuid) { uuid += hex[b >> 4]; uuid += hex[b & 15]; }
    std::string name = std::string(ns) + "-" + std::to_string(key.vendor) + "-" +
        std::to_string(key.device) + "-" + std::to_string(key.driver) + "-" + uuid + ".vkcache";
    return std::filesystem::path(dir) / name;
}
inline std::vector<uint8_t> load(const DeviceKey& key) noexcept {
    try {
        auto p = path(key);
        if (p.empty()) return {};
        std::ifstream f(p, std::ios::binary | std::ios::ate);
        if (!f) return {};
        auto size = f.tellg();
        if (size < 32 || size > 128 * 1024 * 1024) return {};
        std::vector<uint8_t> data(static_cast<size_t>(size));
        f.seekg(0);
        if (!f.read(reinterpret_cast<char*>(data.data()), size) || !compatible(data, key)) return {};
        return data;
    } catch (...) { return {}; }  // cache failure falls back to cold compilation
}
inline bool save(const DeviceKey& key, const std::vector<uint8_t>& data) noexcept {
    int fd = -1;
    std::filesystem::path temp;
    try {
        if (data.size() > 128 * 1024 * 1024 || !compatible(data, key)) return false;
        auto p = path(key);
        if (p.empty()) return false;
        std::filesystem::create_directories(p.parent_path());
        std::string pattern = p.string() + ".XXXXXX";
        std::vector<char> buffer(pattern.begin(), pattern.end()); buffer.push_back(0);
        fd = mkstemp(buffer.data());
        if (fd < 0) return false;
        temp = buffer.data();
        size_t written = 0;
        while (written < data.size()) {
            auto count = ::write(fd, data.data() + written, data.size() - written);
            if (count <= 0) { ::close(fd); fd = -1; std::filesystem::remove(temp); return false; }
            written += static_cast<size_t>(count);
        }
        if (::fsync(fd) != 0) { ::close(fd); fd = -1; std::filesystem::remove(temp); return false; }
        ::close(fd); fd = -1;
        std::filesystem::rename(temp, p);
        return true;
    } catch (...) {
        if (fd >= 0) ::close(fd);
        std::error_code ignored;
        if (!temp.empty()) std::filesystem::remove(temp, ignored);
        return false;
    }
}
} // namespace bb_cache
