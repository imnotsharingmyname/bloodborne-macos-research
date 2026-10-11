#!/usr/bin/env python3
"""Sign nested code first; use --deep for verification, never as the signing algorithm."""
import argparse
from pathlib import Path
import subprocess
from bundle import is_macho

ROOT = Path(__file__).resolve().parents[1]

def sign(app, identity):
    app = app.resolve()
    public = identity != '-'
    for file in sorted(app.rglob('*'), key=lambda p: len(p.parts), reverse=True):
        if not is_macho(file) or file == app / 'Contents/MacOS/Bloodborne':
            continue
        cmd = ['codesign', '--force', '--sign', identity]
        if public:
            cmd += ['--options', 'runtime', '--timestamp']
        if file == app / 'Contents/Helpers/bb-runtime':
            cmd += ['--entitlements', str(ROOT / 'entitlements/guest-x86_64.plist')]
        cmd += [str(file)]
        subprocess.run(cmd, check=True)
    cmd = ['codesign', '--force', '--sign', identity,
           '--entitlements', str(ROOT / 'entitlements/launcher.plist')]
    if public:
        cmd += ['--options', 'runtime', '--timestamp']
    subprocess.run(cmd + [str(app)], check=True)
    subprocess.run(['codesign', '--verify', '--deep', '--strict', '--verbose=2', str(app)], check=True)

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('app', type=Path)
    p.add_argument('--identity', default='-')
    a = p.parse_args()
    sign(a.app, a.identity)
