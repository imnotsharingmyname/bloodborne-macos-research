Bloodborne — experimental macOS application

Requires Apple Silicon, macOS 26 or newer within the release's tested support
range, Rosetta, and your own decrypted CUSA03173 v1.09 game folder.
This project is unofficial and includes no game files or decryption tools.
The experimental runtime and MoltenVK game compatibility require testing.

1. Drag Bloodborne.app into Applications.
2. Open Bloodborne. Follow the macOS first-open prompt for signed releases.
3. Select Game Folder (CUSA03173). Select the folder that contains eboot.bin,
   sce_sys/param.sfo, sce_module/libc.prx, sce_module/libSceFios2.prx,
   and the non-empty dvdroot_ps4 directory.
4. Begin at 720p / 30 FPS / FSR off, then press Launch Bloodborne.

No Xcode, Vulkan SDK, Homebrew, Python, or terminal commands are needed to
run a completed release. On macOS 26, Rosetta may require Apple's one-time
installation and consent flow. Rosetta availability on future macOS versions
must be checked before claiming compatibility.

60/90 FPS patches and FSR Quality are experimental. They are requests, not
performance promises. Use the conservative defaults when diagnosing issues.

The original game directory is not modified. Generated runtime images,
saves, settings, driver/shader caches, and logs are stored in:
  ~/Library/Application Support/BloodborneResearch/
Use Open Logs and Open Saves in the launcher to access them in Finder.

An archive named experimental-adhoc is a local development build. Ad-hoc
signing does not provide the Gatekeeper behavior of a notarized release.
Do not remove quarantine or disable Gatekeeper as a distribution method.
