#!/usr/bin/env python3
"""Package experimental artifacts or an acceptance-gated Developer ID release."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = ['game_boot', 'movement_combat', 'audio', 'controller', 'save_roundtrip',
            'fps_60_patch', 'fps_90_patch', 'fsr_quality', 'cold_warm_cache',
            'download_gatekeeper', 'read_only_app', 'relocation_spaces_unicode',
            'offline_launch', 'hardened_runtime', 'license_source_compliance']

def run(*args):
    subprocess.run(list(map(str, args)), check=True)

def release_gate(app, evidence):
    policy = json.loads((app / 'Contents/Resources/game-policy.json').read_text())
    if not policy.get('require_verified_hash') or not policy.get('accepted_eboot_sha256'):
        raise RuntimeError('Public release requires a verified SELF hash allowlist baked into the app')
    for digest in policy['accepted_eboot_sha256']:
        if len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
            raise RuntimeError('Invalid verified eboot hash')
    record = json.loads(evidence.read_text())
    lock = json.loads((ROOT / 'dependencies.lock.json').read_text())
    if record.get('source_commit') != lock['source']['commit']:
        raise RuntimeError('Release evidence is for a different source revision')
    if record.get('driver_version') != lock['moltenvk']['version']:
        raise RuntimeError('Release evidence is for a different driver')
    for name in REQUIRED:
        if record.get('checks', {}).get(name) is not True:
            raise RuntimeError('Missing release acceptance: ' + name)
    if not {'M1', 'M2', 'M3', 'M4'}.issubset(set(record.get('tested_gpu_families', []))):
        raise RuntimeError('The requested M1–M4 support matrix has not been tested')
    # CodeDirectory hashes bind executable code; resource hashes bind the wrapper/assets.
    from acceptance_snapshot import fingerprints
    actual = fingerprints(app)
    expected = record.get('resource_hashes', {})
    if actual != expected:
        raise RuntimeError('Resource fingerprints changed; generate evidence for this exact build')

def source_archive(destination):
    # Include build scripts, patches, upstream/dependency sources, and downloaded source archives.
    # Never collect app0, user saves, prepared eboot/module images, or shader caches.
    roots = [ROOT, ROOT / '.work/source', ROOT / '.work/vulkan_headers',
             ROOT / '.work/vulkan_loader', ROOT / '.work/spirv_cross',
             ROOT / '.work/python-source', ROOT / '.work/source/out/macos/_deps']
    with tarfile.open(destination, 'w:gz') as tf:
        for index, base in enumerate(roots):
            if not base.exists():
                continue
            for f in base.rglob('*'):
                rel = f.relative_to(base)
                if any(part in ('.git', '.work', 'out', 'dist', 'user', '__pycache__') for part in rel.parts):
                    continue
                if index == 6 and not any(part.endswith('-src') for part in rel.parts):
                    continue
                if f.is_file() and not f.is_symlink():
                    if f.name.lower().endswith(('.bin', '.prx', '.sprx', '.spv', '.vkcache',
                                                '.a', '.o', '.dylib', '.dll', '.exe')):
                        continue
                    tf.add(f, arcname='source-' + str(index) + '/' + str(rel), recursive=False)
    # Dependency licenses (especially the upstream prebuilt FFmpeg package) require
    # human source/license reconciliation before license_source_compliance is marked true.

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--adhoc', action='store_true', help='Local experimental package; Gatekeeper is not cleared')
    p.add_argument('--candidate', action='store_true', help='Signed/notarized experimental candidate for acceptance testing')
    p.add_argument('--acceptance', type=Path, default=ROOT / 'release-acceptance.json')
    a = p.parse_args()
    if a.adhoc and a.candidate:
        raise RuntimeError('Choose --adhoc or --candidate')
    if sys.platform != 'darwin':
        raise RuntimeError('Packaging requires macOS codesign, ditto, hdiutil, and xcrun')
    app = ROOT / 'out/Bloodborne.app'
    if not (app / 'Contents/Helpers/bb-runtime').is_file():
        raise RuntimeError('A launcher-only scaffold cannot be packaged as the game runtime')
    identity = '-' if a.adhoc else os.environ.get('SIGN_IDENTITY', '')
    profile = os.environ.get('NOTARY_PROFILE', '')
    if not a.adhoc:
        if not identity.startswith('Developer ID Application:') or not profile:
            raise RuntimeError('Set SIGN_IDENTITY and a stored NOTARY_PROFILE on the release builder')
        if not a.candidate:
            release_gate(app, a.acceptance)
    run(sys.executable, ROOT / 'scripts/sign.py', app, '--identity', identity)
    if not a.adhoc and not a.candidate:
        release_gate(app, a.acceptance)  # final signatures must still match the tested code
    run(sys.executable, ROOT / 'scripts/audit.py', app)
    dist = ROOT / 'dist'
    dist.mkdir(exist_ok=True)
    if not a.adhoc:
        submit = dist / 'notary-submit.zip'
        run('ditto', '-c', '-k', '--keepParent', app, submit)
        run('xcrun', 'notarytool', 'submit', submit, '--keychain-profile', profile, '--wait')
        run('xcrun', 'stapler', 'staple', app)
        run('xcrun', 'stapler', 'validate', app)
        run('spctl', '--assess', '--type', 'execute', '--verbose=4', app)
        submit.unlink()
    label = ('Bloodborne-experimental-adhoc' if a.adhoc else
             'Bloodborne-experimental-candidate' if a.candidate else 'Bloodborne-macOS')
    stage = ROOT / '.work/package-stage'
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)
    run('ditto', app, stage / 'Bloodborne.app')
    shutil.copy2(ROOT / 'README-END-USER.txt', stage / 'Read Me.txt')
    if a.adhoc:
        (stage / 'BUILD-STATUS.txt').write_text('Experimental ad-hoc build. Not notarized. Full-game compatibility is not established.\n')
    # Create zip before adding the Applications alias so unzip never creates /Applications links.
    zipfile = dist / (label + '.zip')
    run('ditto', '-c', '-k', '--sequesterRsrc', stage, zipfile)
    (stage / 'Applications').symlink_to('/Applications', target_is_directory=True)
    dmg = dist / (label + '.dmg')
    if dmg.exists():
        dmg.unlink()
    run('hdiutil', 'create', '-volname', 'Bloodborne', '-srcfolder', stage,
        '-format', 'UDZO', '-ov', dmg)
    if not a.adhoc:
        run('codesign', '--force', '--sign', identity, '--timestamp', dmg)
        run('xcrun', 'notarytool', 'submit', dmg, '--keychain-profile', profile, '--wait')
        run('xcrun', 'stapler', 'staple', dmg)
        run('xcrun', 'stapler', 'validate', dmg)
        run('spctl', '--assess', '--type', 'open', '--context', 'context:primary-signature', '--verbose=4', dmg)
    source_archive(dist / 'Bloodborne-corresponding-source.tar.gz')
    sums = []
    for f in sorted(dist.iterdir()):
        if f.suffix in ('.zip', '.dmg', '.gz'):
            h = hashlib.sha256()
            with f.open('rb') as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                    h.update(chunk)
            sums.append(h.hexdigest() + '  ' + f.name)
    (dist / 'SHA256SUMS.txt').write_text('\n'.join(sums) + '\n')
    print('Packaged:', zipfile, dmg)

if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, ValueError, OSError, subprocess.CalledProcessError) as exc:
        print('RELEASE STOPPED:', exc, file=sys.stderr)
        sys.exit(1)
