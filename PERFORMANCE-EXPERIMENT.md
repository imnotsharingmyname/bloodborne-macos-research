# Experimental M1 Pro performance branch

This branch is **not** a verified 60 FPS release. It preserves the working `main` branch.

## Current Mac baseline

- Existing playable app: macOS x86-64 guest runtime under Rosetta using the x86-64 KosmicKrisp driver.
- Same-scene measurements from the tester: 720p ~20 FPS; 540p ~22 FPS; 1080p ~16 FPS.
- GPU active residency sampled at 100% during gameplay. This does not attribute time to individual rendering passes.
- The tester's CUSA00900 v01.09 eboot came from a modified 60FPS-1080-DEBUG update. Upstream `60 FPS++` patches caused a SIGSEGV; disabling the extra patch made it playable.

## What this branch actually changes

1. Experimental game policy accepts CUSA00900 metadata in addition to the existing CUSA03173 policy, but **does not verify the executable hash**. Validation is not proof of correctness.
2. Launcher automatically selects a **bundled** KosmicKrisp ICD when present; without one, keeps the existing MoltenVK path.
3. Adds opt-in `--perf-diagnostics`, exposed as a native checkbox; requests `BB_FRAME_STATS`, `BB_PRESENT_STATS`, and `BB_BUFFER_STATS`. Supported output depends on the pinned native runtime; missing counters are not evidence of success.
4. Adds an experimental GPU scheduling selector: `baseline` (current default), `queue2` (`BB_FRAMES_AHEAD=2`), and `direct-record` (`BB_VK_RECORD_THREAD=0`). None is a verified performance optimization; benchmark the same scene with each setting and compare warm runs.
5. Rejects 60/90 FPS++ on the experimental CUSA00900 title until a verified executable-specific timing patch is implemented.
6. Builds an isolated GitHub Actions artifact incorporating the exact previously tested x86-64 KosmicKrisp build, then re-signs and audits the app.

## Build and install

See Actions → **M1 Pro experimental KosmicKrisp build**. When the run **succeeds**, obtain the `Bloodborne-KosmicKrisp-experimental` artifact. It contains the `.app` ZIP, not any game data. The app is ad-hoc signed and not notarized. Do not bypass Gatekeeper warnings without validating the artifact and code signature.

The CI build is **not a gameplay validation**. Only a run with passing build, bundled ICD, signing and audit steps establishes that an artifact was produced. No measured FPS benefit is claimed.

**Keep the known-working 20 FPS app unchanged.** This experimental app uses `~/Library/Application Support/BloodborneResearch` by default, so it shares game saves/settings with other builds. Before testing, quit all instances and back up that directory; never run both builds simultaneously against the same directory.

To collect diagnostics: check **Collect frame/present/buffer diagnostics**, select 720p, 30 FPS, and use the same scene as your baseline. Press **Open Logs**. Some counters may be unsupported by the pinned core. 60 FPS gameplay is not implemented by this feature branch.

## Engineering next step

Profile scheduler host-copy waits, GPU timeline waits, render-pass boundaries and shader PSO misses in the pinned Metalborne source. Do not claim a throughput optimisation until a modified runtime compiles and produces same-scene frame-time measurements on Apple Silicon.

## Same-scene GPU scheduling benchmark

With the working app preserved, test the three **GPU scheduling** modes independently, selecting **30 FPS**, **720p**, **FSR off**, and **Collect frame/present/buffer diagnostics**. Restart the game between modes, allow shader caches to warm, and measure a fixed gameplay location for at least 30 seconds per mode. Do not run copies simultaneously. Keep gameplay, camera view, power source and thermal state identical. Record the mode from `Vulkan driver: ...; GPU mode: ...` in the launch log.

- **Baseline:** `BB_FRAMES_AHEAD=1` and existing recorder thread.
- **Queue 2 frames:** Changes `BB_FRAMES_AHEAD` to 2 and can add input latency. A rise in FPS without stable host presentation pacing is not a confirmed display improvement.
- **Direct recording:** Sets `BB_VK_RECORD_THREAD=0`; potentially changes CPU scheduling, recording overhead and stability. If rendering breaks, return to Baseline.

Neither mode directly speeds up Metal shader execution, so an unchanged FPS result is plausible. The pinned upstream already contains macOS atomic host-copy waits; avoid reapplying the same optimization. A real 60 FPS solution requires deeper GPU profiler work and benchmarked native core changes.
