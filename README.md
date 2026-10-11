# Bloodborne macOS BuildKit

This kit supplies an automated **experimental macOS build and distribution pipeline**, an arm64 AppKit launcher, asset validation, dependency bundling, signing, notarization, and packaging scripts.

It is **not a compiled or validated playable release**. The selected macOS fork executes x86-64 game code in an x86-64 Mach-O runtime under Rosetta. Native ARM64 guest execution remains unimplemented. The fork's documented game boots used KosmicKrisp, so this MoltenVK pipeline still needs full-game validation. Ad-hoc signing does not clear Gatekeeper.

Read [GUIDE.md](GUIDE.md) for the complete implementation and release procedure. All scripts are included as source, with no game files or decryption tools.

On an Apple Silicon maintainer Mac with Xcode 26 tools:

```bash
bash build_mac.sh --launcher-only   # arm64 UI scaffold, no game backend
bash build_mac.sh                   # experimental Rosetta backend and dependencies
bash scripts/package_mac.sh --adhoc # local experimental ZIP + DMG
```

`Build Mac.command` invokes the full experimental build by double-click. Users of a completed release do not run this builder or install its tools.

The public release route uses a Developer ID certificate, a stored notarization profile, verified game-version hashes, and test evidence. See GUIDE.md. `--runtime-arch arm64` explicitly stops instead of pretending that an architecture build flag translates the game's x86-64 code.

Portable contract checks:

```bash
BB_TEST_UPSTREAM=/absolute/path/to/pinned-metalborne bash scripts/test_portable.sh
```

The included tests passed on Linux. AppKit, Mach-O relocation, Rosetta, Metal, and notarization must be checked on macOS.
