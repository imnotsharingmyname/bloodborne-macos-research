# Automated Bloodborne macOS engineering and release guide

Verified source snapshot: 10 October 2026. This is an implementation kit, not evidence of a working game release.

## 1. Deliverable and architecture decision

The requested end-user experience is feasible only after a compatible game runtime has passed macOS testing. Packaging cannot repair CPU execution or renderer incompatibilities.

Three distinctions determine the build:

| Requirement | Implementation in this kit | Remaining work |
|---|---|---|
| Native Apple Silicon GUI | arm64 Objective-C++ / AppKit launcher | Compile and exercise on Mac |
| Run x86-64 game code | Pinned Metalborne x86-64 Mach-O runtime under Rosetta | Full-game tests with bundled MoltenVK |
| Entirely native ARM64 runtime | Separate arm64 toolchain and Darwin JIT example | Actual translator/ABI/platform integration is not implemented |
| No end-user SDK or Python setup | CPython, Vulkan loader/driver and dependency closure bundled | Rosetta's OS-managed installation/consent may still be needed on macOS 26 |
| Normal downloaded-app launch | Developer ID, hardened runtime, notarization and stapling | Maintainer credentials and downloaded-artifact testing |

The practical experimental route is:

1. An arm64 AppKit process validates settings and starts a bundled arm64 Python helper.
2. Python validates and prepares the user's plaintext PS4 images in Application Support.
3. Python replaces itself with the x86-64 Mach-O runtime. Rosetta translates the entire x86 process.
4. The runtime and x86-64 bbgpu communicate in that process; the x86-64 Vulkan loader loads an x86-64 MoltenVK driver.
5. MoltenVK submits Metal work to the Apple GPU. It translates Vulkan operations and shader code; it does not translate the PS4 CPU executable.

An arm64 process cannot load an x86-64 dylib. Rosetta is not a general ELF loader that can be bolted onto an arm64 process. Retaining the macOS fork's x86 loader, guest mapping, TLS, and ABI adaptations is essential.

The pinned fork is `Livio21/metalborne`, commit `c3720ecf067e33c118d2ab04647facfa882f26b7`, from `codex/macos-rosetta`. Its macOS CMake explicitly rejects architectures other than x86_64. Its documentation reports incomplete compatibility and performance testing, with game rendering observed using KosmicKrisp rather than a full MoltenVK game boot. Those observations are author reports, not results reproduced here.

Mrsuss60's Windows source and droogie/bbhost are different integration targets. Do not replace the repository URL in the lockfile and expect their target names, asset format, patch preparation, or launch arguments to match. A bbhost adapter must follow that repository's own loader contract; its documented decrypted ELF hash must not be used as a hash for Metalborne's plaintext SELF input.

## 2. Kit contents and generated layout

| File or directory | Purpose |
|---|---|
| `build_mac.sh`, `Build Mac.command` | Shell entry and clickable maintainer build |
| `scripts/build.py` | Tool bootstrap, source pinning, cross builds, staging and smoke test |
| `dependencies.lock.json` | Git commits, archive SHA-256 values and builder tool versions |
| `CMakeLists.txt`, `cmake/` | Native launcher and separate architecture toolchains |
| `launcher/main.mm` | Native folder picker, validation, settings, launch and logs |
| `runtime/launch.py` | Asset contract and upstream image-preparation execution |
| `scripts/patch_source.py` | Exact-context CMake/cache adjustments for the pinned fork |
| `graphics/bb_pipeline_store.hpp` | Bounded, device-qualified driver-cache persistence |
| `scripts/bundle.py`, `scripts/audit.py` | Mach-O dependency closure and relocation audit |
| `scripts/sign.py`, `entitlements/` | Inside-out ad-hoc or Developer ID signatures |
| `scripts/package_mac.sh`, `scripts/package.py` | ZIP/DMG, notarization/stapling and source archive |
| `scripts/acceptance_snapshot.py` | Signed-code/resource fingerprints for test evidence |
| `.github/workflows/mac-build.yml` | Manually triggered macOS build artifact workflow |
| `platform/DarwinJitArena.example.hpp` | Unintegrated example for future ARM64 translation |
| `tests/`, `scripts/test_portable.sh` | Portable contracts and upstream-format integration checks |

Generated bundle paths are listed here instead of an illustrative directory tree:

| Bundle path | Content |
|---|---|
| `Contents/MacOS/Bloodborne` | arm64 launcher, CFBundleExecutable |
| `Contents/Helpers/python3.13` | arm64 CPython helper |
| `Contents/Helpers/bb-runtime` | x86-64 game runtime |
| `Contents/Frameworks/arm64/` | CPython's non-system library closure |
| `Contents/Frameworks/x86_64/` | bbgpu, Vulkan loader, MoltenVK, other runtime dylibs |
| `Contents/Resources/python/lib/python3.13/` | Standard library and extension modules |
| `Contents/Resources/backend/scripts/` | Upstream image/link/patch preparation scripts |
| `Contents/Resources/backend/patches/` | Upstream patch definitions |
| `Contents/Resources/vulkan/icd.d/MoltenVK_icd.json` | Relocatable driver manifest |
| `Contents/Resources/game-policy.json` | CUSA03173, version and hash acceptance policy |
| `Contents/Resources/Licenses/` | Collected dependency notices |
| `Contents/Resources/build-manifest.json` | Versions and build provenance |

The app writes no caches or generated images into its bundle. Data goes under `~/Library/Application Support/BloodborneResearch/`: `out/`, `user/`, `driver-cache/`, `bbport.ini`, and `logs/`. This supports a read-only app location and Finder app translocation.

## 3. Builder prerequisites and automated compilation

The maintainer needs an Apple Silicon Mac, Xcode 26 or compatible selected command-line tools with a macOS 26 SDK, Git, network access, and Apple's developer-tools Python at `/usr/bin/python3`. Verify that `xcrun --find clang` and `xcrun --sdk macosx --show-sdk-version` work. Xcode installation and license acceptance are builder provisioning, not end-user requirements; this kit does not redistribute Apple's SDK.

Start with the UI-only milestone:

```bash
bash build_mac.sh --launcher-only
open out/Bloodborne.app
```

This mode builds a real arm64 launcher scaffold with an explicit missing-backend status. Its launch controls are disabled. It is not packaged as a working game.

Then build the experimental runtime:

```bash
bash build_mac.sh --jobs 4
```

The builder performs these operations without Homebrew or a system Vulkan SDK:

1. Creates a private Python venv in `.work/tools` and installs the pinned CMake/Ninja packages.
2. Fetches the exact source commit and initializes its pinned LibAtrac9, ImGui and FSR submodules.
3. Applies the kit's idempotent, exact-context renderer-cache and loader-default patches. Context drift fails the build.
4. Installs pinned Vulkan headers and builds an x86-64 Vulkan loader into a private prefix.
5. Builds static x86-64 SPIRV-Cross MSL/GLSL/core libraries into that prefix.
6. Runs upstream `scripts/build_macos.sh` with that prefix and loader. Upstream builds static SDL3, LibAtrac9 (`bbatrac9`), the runtime (`bbruntime`), `bb-probe`, and the shared `bbgpu` video core. Its remaining fetched dependencies retain their pinned upstream revisions; upstream currently consumes an FFmpeg prebuilt package rather than compiling every codec source here.
7. Downloads MoltenVK 1.4.2's standard macOS archive and verifies SHA-256 before extraction. This uses the public API artifact, not the private-API package.
8. Builds arm64 CPython 3.13.7 from its checksum-verified source archive, without pip/ensurepip or test modules in the shipped runtime.
9. Stages the native launcher, Python standard library, upstream preparation scripts, patches, runtime and GPU library.
10. Recursively bundles non-system Mach-O dependencies, checks architecture slices and rewrites their load commands.
11. Signs for local development, verifies the bundle, audits paths, and executes the runtime's `--vulkan-only` buffer submission/readback test.

The downloaded archive hashes and source commits are concrete pins in `dependencies.lock.json`. CMake/Ninja are pinned package versions; their bootstrap is not a fully hermetic supply-chain build. For a production build farm, mirror and hash-lock the builder wheels and upstream FetchContent archives, pin the Xcode runner image, and archive the exact toolchain/dependency manifest. Source pinning makes rebuild inputs reviewable; signing timestamps and SDK/compiler behavior mean binary output is not promised to be bit-for-bit identical.

The fork currently sets minimum macOS 26.0. Do not lower the target to 12/14 merely to widen the product's compatibility label. Its memory, TLS and linker choices must be retested against any older supported OS.

### CMake and Xcode configuration

The launcher is built with CMake's Ninja generator. To inspect it in Xcode:

```bash
.work/tools/bin/cmake -S . -B out/launcher-xcode -G Xcode \
  -DCMAKE_TOOLCHAIN_FILE="$PWD/cmake/apple-arm64.cmake"
open out/launcher-xcode/BloodborneLauncher.xcodeproj
```

Use these settings:

| Setting | Launcher | Current game process |
|---|---|---|
| `CMAKE_SYSTEM_NAME` | Darwin | Darwin |
| `CMAKE_OSX_ARCHITECTURES` / `ARCHS` | arm64 | x86_64 |
| `CMAKE_OSX_SYSROOT` / `SDKROOT` | macosx | macosx |
| `CMAKE_OSX_DEPLOYMENT_TARGET` | 26.0 | 26.0 |
| Language standard | C++17, Objective-C++ | Upstream C11/C++23/Objective-C++23 |
| ARC | `-fobjc-arc` | Preserve upstream per-file settings |
| App Sandbox | Off | Off |
| Code signing while compiling | Off; final script signs | Final script signs |
| Hardened runtime for public release | On through `codesign --options runtime` | On, with guest-memory entitlement |
| Header relocation room | `-headerpad_max_install_names` | Same, preserving upstream linker options |
| LTO | Optional | Upstream `BB_LTO=ON`, subject to compiler support |

Do not substitute `-march=native` into the x86 process build on an arm64 host. Do not statically link Apple's system frameworks or libSystem. Keep bbgpu shared because the current runtime exports callbacks used by the renderer; fully static bbgpu would require revisiting its symbol and lifetime contracts.

The fork uses special x86 Mach-O layout options, including low TLS reservation and a high image base. Preserve them. A conventional PIE launcher is appropriate for the arm64 GUI, but imposing its layout on the guest runtime can break guest mapping assumptions.

## 4. CPU execution and a genuinely native ARM64 route

The selected route retains the fork's Darwin guest FS/TLS adaptation, POSIX shared-memory backing, low-address guest allocations, synchronization, thread lifecycle and signal handling. It keeps Cocoa window creation/event polling on the runtime's main thread while guest execution moves to its worker.

Run loader/platform tests before attributing a crash to graphics. Check guest import resolution, guest-to-host ABI calls, TLS isolation across threads, direct-memory aliases, allocation reuse and zeroing, joining decoder threads, and occupied-map protection. Never overwrite an occupied host range with an unconditional `MAP_FIXED`.

For a true native arm64 runtime, the outstanding engineering sequence is:

1. Port a translator core to Darwin; FEX's Linux/Windows platform support is not an out-of-box macOS build target.
2. Replace Linux syscalls/signal contexts/futex/memfd/virtual-address assumptions with the corresponding Darwin mechanisms or runtime services.
3. Route translated code allocation through a process-owned JIT arena, implementing Apple's write/execute discipline and instruction-cache publication.
4. Add x86 guest ↔ arm64 host ABI thunks: integer/vector argument placement, stack alignment, variadic calls, callbacks, exceptions/unwind boundaries, and per-thread guest FS state.
5. Preserve PS4 syscall and HLE behavior. A userspace Linux translator does not itself implement PS4 kernel/library semantics.
6. Respect the host's actual page size. Do not assume that a 4 KiB guest protection or alias operation can be represented by an independent 4 KiB host mapping on an Apple Silicon host.
7. Establish self-modifying-code invalidation and synchronization with running translation blocks. Compile-only success proves none of these contracts.
8. Only then rebuild runtime, bbgpu, loader and driver for arm64 and remove Rosetta from the launcher.

`platform/DarwinJitArena.example.hpp` shows a single MAP_JIT arena, guarded code writes, `pthread_jit_write_protect_np`, and `sys_icache_invalidate`. It is an unintegrated example, not FEX integration or a tested translator. Publish immutable blocks with release/acquire synchronization, coordinate repatching with executor quiescence, and respect the one-arena constraint documented by Apple for hardened apps using allow-jit. Do not mix the newer JIT write-allowlist entitlement/callback model with this example without adapting its API.

`entitlements/arm64-jit.example.plist` belongs on that future translator executable. It is not added to the GUI. The current Rosetta helper instead receives `allow-unsigned-executable-memory`, because it loads/patches unsigned guest instructions rather than using this ARM64 MAP_JIT allocator. This broader exception must be validated under the hardened runtime. The kit does not add `get-task-allow` or disable library validation.

## 5. Vulkan, MoltenVK and pipeline caches

The implemented route uses a Vulkan loader and one private driver manifest. It does not depend on `/usr/local/share/vulkan`, a user SDK, or driver discovery in Homebrew. At launch the worker sets an absolute `VK_DRIVER_FILES` path resolved from the current bundle, and an absolute bundled `BB_VULKAN_LOADER` path. The ICD's library path is relative to the JSON and reaches `Contents/Frameworks/x86_64/libMoltenVK.dylib`.

The renderer already handles Metal surfaces, portability enumeration and enabling `VK_KHR_portability_subset` when advertised. Device creation must still request only supported feature bits. A Vulkan version string is not evidence that every shader, format, extension, subgroup operation or synchronization pattern required by the PS4 renderer is supported.

`cmake/MoltenVK.cmake` supplies an optional static-link integration function for a renderer adapted to direct MoltenVK dispatch. Do not add it alongside the current loader and assume the APIs become interchangeable: direct dispatch, extension discovery, validation layers and runtime driver selection have different integration requirements.

### Shader and pipeline work

The game's GPU code is GCN, so it first passes through the renderer's GCN→SPIR-V recompiler. MoltenVK then translates SPIR-V to MSL and creates Metal objects. A Metal compile flag cannot fix incorrect GCN semantics or a shader feature absent from the portability implementation.

The kit patches the pinned `PipelineCache` constructor to load driver cache bytes before shader/pipeline warmup. On orderly destruction it serializes the driver cache using `getPipelineCacheData`. The helper checks the Vulkan cache header's vendor, device and UUID; file names additionally include driver version and a namespace covering game hash, source/dependency pins, OS build and MoltenVK settings. Incompatible, truncated or oversized blobs fall back to cold compilation. Writes use a temporary file, fsync and atomic rename.

Upstream's shader metadata/SPIR-V cache and this driver cache are separate. Driver cache persistence can reduce repeat translation work; it does not guarantee that Metal PSO creation or specialization work disappears. Save after pipeline creation workers have stopped. Crashes or forced termination can lose newly created entries. The C++ file contract was tested here; the Vulkan-Hpp patch still requires compilation and workload verification on Mac.

The initial settings prioritize reproducible correctness:

| Parameter | Initial value | Tuning approach |
|---|---|---|
| `MVK_CONFIG_FAST_MATH_ENABLED` | 0 | Compare against 2 after shader correctness tests; preserve precise behavior where needed |
| `MVK_CONFIG_USE_METAL_ARGUMENT_BUFFERS` | 1 | Profile descriptor pressure and test binding correctness |
| `MVK_CONFIG_PREFILL_METAL_COMMAND_BUFFERS` | 0 | Baseline; compare 1 only after auditing update-after-bind/reset/reuse behavior |
| `MVK_CONFIG_LOG_LEVEL` | 2 | Increase only for diagnostics |
| `BB_PRESENT_MODE` | Fifo | Verify actual swapchain support and display pacing |
| `BB_FRAMES_AHEAD` | 1 | Compare 2 for latency/stall tradeoffs after correctness |
| `BB_PREP_WORKERS` | 0 | Retains fork workaround pending race diagnosis |

There is no proven universal M1/M2/M3/M4 "optimal flags" set. Optional concurrent compilation should be measured for startup time, transient memory and frame-time spikes; more compiler work is not automatically faster. Do not force private Metal APIs or driver-specific semaphore workarounds into a general release without evidence.

Collect cold and warmed measurements in identical scenes. Track guest flip arrival, CPU command encoding, pipeline compile duration, GPU completion, drawable acquire, present enqueue and actual presentation time separately. A guest FPS counter is not screen cadence. On Apple tile-based GPUs, audit pass endings, attachment store actions, memory aliasing, upload-ring pressure and unnecessary readbacks before increasing worker counts. Do not remove fences or discard stores whose contents later guest/GPU work consumes.

FSR 3.1 requires valid motion vectors, depth, jitter, resource formats and synchronization in this renderer. The launcher maps its checkbox to the upstream `fsr3` Quality setting; enabling it is not an assertion that MoltenVK supports the complete path. Higher FPS caps apply actual upstream 60/90 patches, not display-only sleep loops. Neither setting promises a given frame rate.

## 6. Assets and launch flow

The native picker accepts a directory containing:

- `eboot.bin`: plaintext PS4 SELF for this backend.
- `sce_sys/param.sfo`: TITLE_ID CUSA03173, APP_VER 01.09.
- `sce_module/libc.prx` and `sce_module/libSceFios2.prx`: required plaintext modules.
- Non-empty `dvdroot_ps4/`: game assets.

No assets are included or downloaded. The launcher accepts paths containing spaces/Unicode and passes arguments as arrays, never by constructing a shell command.

Validation bounds SFO offsets, verifies metadata, parses the SELF layout with the pinned upstream parser, rejects encrypted/compressed payloads and checks required modules. These checks do not prove that every asset is complete. A production release should validate a reviewed file inventory, with appropriate hashes for required assets/modules.

The default policy has no eboot hash allowlist. It explicitly reports metadata/layout validation rather than an exact executable-version proof. Before a public release, add hashes independently verified from compatible, legally supplied v1.09 SELF dumps and set `require_verified_hash` to true in `config/game-policy.json`; rebuild afterward. Do not claim the bbhost ELF hash identifies this SELF file.

`launch.py` executes upstream prepare, libc-link, module-link, content-profile and patch scripts with the bundled interpreter. Prepared images are generated on macOS so guest TLS transformations match the Darwin runtime. It then execs `bb-runtime` with `boot-linked.bin`, `content.bin`, `patches.bin`, `--app0`, `--user` and timeout arguments.

A file lock survives exec to prevent multiple app copies from overwriting the same prepared images while a game is running. The original dump is read-only in this flow. The launcher keeps a remembered game path, shows launch/validation failures, captures runtime logs and offers Finder access to logs/saves. Normal game exit is preferred before quitting so saves can finish.

## 7. Signing and distribution automation

`codesign --force --deep --sign -` does not make a public download trusted by Gatekeeper. Ad-hoc signing provides a local code signature, not a Developer ID identity or notarization ticket. This kit signs nested binaries individually and the app last; it uses `--deep` to verify the resulting closure.

For local research packaging:

```bash
bash scripts/package_mac.sh --adhoc
```

The generated filenames explicitly say `experimental-adhoc`. They are not suitable for promising normal Gatekeeper first-launch behavior.

For a signed experimental candidate, provision the release builder's Developer ID Application certificate/private key and a notarization keychain profile. Apple account/private-key setup is a maintainer responsibility; credentials are never embedded in the app. One supported profile setup is:

```bash
xcrun notarytool store-credentials BloodborneNotary \
  --apple-id 'maintainer@example.com' --team-id 'TEAMID' \
  --password 'APP-SPECIFIC-PASSWORD'
export SIGN_IDENTITY='Developer ID Application: Your Organization (TEAMID)'
export NOTARY_PROFILE='BloodborneNotary'
bash scripts/package_mac.sh --candidate
```

Prefer interactive or secret-managed credential provisioning so shell history/logs do not retain passwords. The command above illustrates fields, not supplied credentials. CI can use App Store Connect API-key credentials supported by notarytool, with a temporary restricted keychain and cleanup after the job.

The script signs all nested code with the same Developer ID, enables the hardened runtime, adds the guest entitlement only to the helper, signs the app, verifies and audits it, submits a ZIP to notarytool, staples and validates the app ticket, and checks Gatekeeper assessment. It then creates a final ZIP and a compressed DMG containing the app, Read Me and Applications alias. The DMG is also signed, notarized, stapled and assessed.

Candidate mode exists so a notarized download can be tested before marking the public-release acceptance checks passed. Test that candidate on clean accounts/Macs, including a browser-downloaded quarantined artifact, offline launch with Rosetta already available, and an app copied into Applications.

After hardware testing, create a fingerprint snapshot of the Developer ID-signed app:

```bash
python3 scripts/acceptance_snapshot.py out/Bloodborne.app
```

This creates `release-acceptance.json` with checks still false. Record genuine results for the required test cases and M1–M4 coverage. CodeDirectory hashes bind signed executables; SHA-256 values bind resources. Do not mark checks true merely because a compile or smoke test passed. A changed app or settings policy requires another snapshot and relevant retesting.

The default public package command is:

```bash
bash scripts/package_mac.sh
```

It requires the verified hash policy, matching source/driver versions, resource/code fingerprints and completed acceptance evidence. It produces `dist/Bloodborne-macOS.zip`, `dist/Bloodborne-macOS.dmg`, a corresponding-source archive and checksums. Packaging finishes on the builder; users only download, drag the app, select their dump and launch.

Notarization is not a compatibility certification and cannot override managed-device policy or guarantee that no future OS ever blocks a binary. It is the normal outside-App-Store distribution mechanism. Do not remove quarantine, disable Gatekeeper, or modify signed bundle contents after packaging.

## 8. CI and release specification

The included manually triggered workflow uses GitHub's macOS 26 arm64 runner and defaults to the launcher-only milestone. Full experimental builds are opt-in. It uploads a labeled build artifact and does not publish a public release. Pin GitHub Actions to reviewed commit SHAs for production and monitor runner image/Xcode changes.

Use these build-farm stages:

| Stage | Inputs | Exit condition |
|---|---|---|
| Source/dependency resolution | Lockfile, recursive submodules, verified archives | Exact pins and checksums match |
| Host launcher build | arm64 toolchain, AppKit | Compile/link and GUI smoke |
| Runtime/dependency build | x86-64 toolchain, upstream Darwin adaptations | Loader, LibAtrac9, SDL3, GPU, shader dependencies compile |
| Staging/relocation | Built binaries, Python runtime, driver | No non-system external load paths; compatible slices |
| Local signing/smoke | Ad-hoc signatures | Strict verification and Vulkan submission/readback |
| Real-game acceptance | User-owned local dump, Apple hardware | Boot, input, audio, save, stability and cache tests |
| Candidate distribution | Developer ID and notary credentials | Signed/stapled artifacts, downloaded-app tests |
| Public release | Exact tested signatures/resources and evidence | Release gate, packaging, license/source reconciliation |

A hosted runner cannot establish interactive game compatibility or the requested multi-GPU performance matrix. Use a controlled Apple hardware test pool for those stages. Do not upload game dumps, saves, generated guest images or game-derived shader caches to public CI artifacts. The app package excludes these inputs by construction; the source archive excludes runtime/game binary formats.

The generated source archive includes kit adjustments, pinned source checkouts and fetched source directories. Review it against every dependency actually shipped. The upstream FFmpeg prebuilt package particularly needs a matching source/license reconciliation. Automated notice collection is useful but is not a substitute for satisfying each actual dependency's redistribution terms.

## 9. Debugging and optimization milestones

1. **Dependency closure:** Run `scripts/audit.py`, relocate the app to paths with spaces/Unicode, and launch with Homebrew/developer tools absent from PATH. Test from a read-only installation and another account.
2. **CPU contracts:** Exercise the fork's platform/runtime checks under Rosetta; check TLS across workers, import scope, shared aliases and occupied ranges before game boot. Repeat under final Developer ID/hardened signatures.
3. **GPU contracts:** Begin with the bundled `--vulkan-only` test. Then verify surface presentation, shader compilation, resource formats, descriptor limits, barriers and timeline synchronization independently. Buffer readback does not prove the renderer's features work.
4. **Game boot:** Use 720p, 30 FPS, FSR off and intro enabled initially. Collect failures from guest initialization, codec threads, pipeline creation and map loading. Skipping intro is a convenience only after the underlying path is understood.
5. **Interaction:** Test movement, combat, camera, controller, audio, save/load, quit/restart and long sessions. Check missing/corrupt assets produce intelligible failures.
6. **Caches:** Compare cold/warmed startup and scene transitions. Verify cache rejection after OS/driver/settings updates and corruption. Stop compilation workers before serialization; preserve upstream SPIR-V specialization invalidation.
7. **Performance:** Run identical scenes on representative M1/M2/M3/M4 Macs. Record p50/p95/p99 frame intervals, GPU time, CPU encoding, peak memory, shader compile stalls and presentation timing. Low-resolution speedups distinguish pixel costs from CPU/submission costs.
8. **Experimental options:** Enable FSR Quality, then test 60 FPS and 90 FPS patches separately. Measure correctness as well as speed. Do not change allocation/protection/fence semantics simply to improve a counter.
9. **Distribution:** Download the notarized candidate in a browser, verify offline stapling behavior, Rosetta installation handling, first-open prompts and logs. Recheck after copying into Applications.

If MoltenVK fails a required shader/feature path, fix the renderer or use a separately tested driver/backend. Borrowing a KosmicKrisp binary from another app is not this pipeline's implementation and must not be silently substituted. A full native Metal renderer or native ARM64 translator would be separate research projects.

## 10. Verification performed for this kit

On Linux, the Python/shell/JSON/plist syntax checks passed; 17 Python contracts passed using the pinned fork's parser and resolution helpers; the standalone C++17 pipeline-cache contract passed, including corrupt/incompatible caches and concurrent atomic writers; the source patch applied to the pinned files and was idempotent. AddressSanitizer/UndefinedBehaviorSanitizer passed for that standalone helper with leak detection disabled. See VALIDATION.md for scope.

No Xcode/AppKit build, Mach-O bundling execution, Rosetta run, Vulkan/Metal device test, full game boot, signing, notarization or playable frame-rate result was performed in this environment. These are explicit remaining verification steps, not assumed outcomes.

## Primary references

- Metalborne source and limitations: https://github.com/Livio21/metalborne and https://github.com/Livio21/metalborne/blob/codex/macos-rosetta/docs/MACOS.md
- bbhost's separate architecture/input contract: https://github.com/droogie/bbhost
- Windows source fork: https://github.com/Mrsuss60/bloodborne_pc_windows_port
- MoltenVK runtime integration: https://github.com/KhronosGroup/MoltenVK/blob/main/Docs/MoltenVK_Runtime_UserGuide.md
- MoltenVK configuration: https://github.com/KhronosGroup/MoltenVK/blob/main/Docs/MoltenVK_Configuration_Parameters.md
- MoltenVK release artifacts: https://github.com/KhronosGroup/MoltenVK/releases/tag/v1.4.2
- Vulkan Loader builds: https://github.com/KhronosGroup/Vulkan-Loader/blob/main/BUILD.md
- Apple JIT guidance: https://developer.apple.com/documentation/apple-silicon/porting-just-in-time-compilers-to-apple-silicon
- Apple Developer ID: https://developer.apple.com/developer-id/
- Apple notarization: https://developer.apple.com/documentation/security/notarizing-macos-software-before-distribution
- Apple Rosetta installation: https://support.apple.com/102527
- GitHub runner reference: https://docs.github.com/en/actions/reference/runners/github-hosted-runners
