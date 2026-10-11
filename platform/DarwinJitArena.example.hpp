// SPDX-License-Identifier: MIT
// FUTURE native ARM64 translator example. Not linked by this Rosetta build.
// Requires com.apple.security.cs.allow-jit on the executable using the arena.
#pragma once
#include <libkern/OSCacheControl.h>
#include <pthread.h>
#include <sys/mman.h>
#include <unistd.h>
#include <cstddef>
#include <cstring>
#include <limits>
#include <mutex>
#include <new>
#include <stdexcept>

class DarwinJitArena {
    std::byte* base_ = nullptr;
    size_t capacity_ = 0;
    size_t used_ = 0;
    std::mutex mutex_;
public:
    explicit DarwinJitArena(size_t bytes) {
        const long page = sysconf(_SC_PAGESIZE);
        if (page <= 0 || bytes == 0 || bytes > std::numeric_limits<size_t>::max() - size_t(page))
            throw std::invalid_argument("Invalid JIT arena size");
        capacity_ = ((bytes + size_t(page) - 1) / size_t(page)) * size_t(page);
        void* p = mmap(nullptr, capacity_, PROT_READ | PROT_WRITE | PROT_EXEC,
                       MAP_PRIVATE | MAP_ANON | MAP_JIT, -1, 0);
        if (p == MAP_FAILED) throw std::runtime_error("MAP_JIT failed; inspect executable signing/entitlements");
        base_ = static_cast<std::byte*>(p);
        pthread_jit_write_protect_np(1);
    }
    DarwinJitArena(const DarwinJitArena&) = delete;
    DarwinJitArena& operator=(const DarwinJitArena&) = delete;
    ~DarwinJitArena() { if (base_) munmap(base_, capacity_); }
    // All executor threads must be stopped before destroying/resetting the arena.
    // Immutable new blocks only. Repatching executing blocks needs a quiescence protocol.
    const void* publish(const void* arm64_code, size_t length) {
        if (!arm64_code || !length || length % 4) throw std::invalid_argument("Invalid ARM64 code block");
        std::lock_guard<std::mutex> lock(mutex_);
        size_t aligned = (used_ + 15) & ~size_t(15);
        if (aligned > capacity_ || length > capacity_ - aligned) throw std::bad_alloc();
        std::byte* destination = base_ + aligned;
        // This simple guard assumes the caller is in execute-protected mode on entry.
        pthread_jit_write_protect_np(0);
        std::memcpy(destination, arm64_code, length);
        sys_icache_invalidate(destination, length);
        pthread_jit_write_protect_np(1);
        used_ = aligned + length;
        return destination;  // publish to executor with release/acquire synchronization
    }
};
