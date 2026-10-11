# Verification record

Environment: Linux x86_64, Python 3, GCC 13.3. Date: 2026-10-10.

Passed:

- Python bytecode compilation, Bash syntax, JSON parsing, and plist parsing.
- 17 Python tests: asset metadata/plaintext SELF validation against the pinned upstream parser; wrong title/update, encrypted SELF, flat ELF and missing module rejection; hash allowlist; resolution wiring; atomic config writes; archive traversal protection; patch idempotence/drift; source-package exclusion; release gate; Mach-O format detection.
- Standalone C++17 pipeline-cache test: header compatibility, device UUID mismatch, invalid/truncated cache rejection, atomic persistence, concurrent readers/writers, and namespace traversal rejection.
- Same C++ test under AddressSanitizer and UndefinedBehaviorSanitizer. Leak detection was disabled because this runner cannot support its process-inspection requirements; no leak-check result is claimed.
- Final renderer/CMake source adjustments apply to the exact pinned Metalborne files and are idempotent.
- Linux builder and packager entry points stop explicitly instead of attempting an Apple build.
- Downloaded CPython archive SHA-256 confirmed; MoltenVK archive downloaded and its expected dylib/include/package layout inspected. Both archive downloads are hash-checked by the builder.

Not performed:

- Xcode/Apple Clang compilation of AppKit or the Vulkan-Hpp source patch.
- Actual Mach-O dependency copying/relocation and signature execution.
- Rosetta/TLS/guest runtime execution.
- Vulkan or Metal GPU smoke tests on Apple hardware.
- Game boot, input/audio/save verification or performance measurement.
- Developer ID signing, notarization, stapling or Gatekeeper download tests.

The kit is source automation for an experimental build. These checks do not establish a playable or distributable game release. The release-acceptance example intentionally contains no passing game/hardware claims.
