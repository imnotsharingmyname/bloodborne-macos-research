#!/usr/bin/env python3
"""Fail if a bundled Mach-O still loads non-system code outside the app."""
import argparse
import json
from pathlib import Path
import subprocess
from bundle import dependencies, is_macho, out, rpaths, system

def audit(app):
    app = app.resolve()
    report = []
    for f in app.rglob('*'):
        if f.is_symlink():
            resolved = f.resolve()
            if app not in resolved.parents:
                raise RuntimeError('Bundle symlink escapes: ' + str(f))
        if not is_macho(f):
            continue
        ids = out('otool', '-D', f).splitlines()[1:]
        dylib_id = ids[0].strip() if ids else ''
        archs = out('lipo', '-archs', f).split()
        if f == app / 'Contents/MacOS/Bloodborne' and archs != ['arm64']:
            raise RuntimeError('Launcher is not arm64')
        if f == app / 'Contents/Helpers/bb-runtime' and archs != ['x86_64']:
            raise RuntimeError('Rosetta runtime is not x86-64')
        for dep in dependencies(f):
            if system(dep) or dep == dylib_id:
                continue
            if not dep.startswith('@loader_path/'):
                raise RuntimeError('External/unresolved load command: ' + dep + ' in ' + str(f))
            target = (f.parent / dep[len('@loader_path/'):]).resolve()
            if app not in target.parents or not target.is_file():
                raise RuntimeError('Missing bundled dependency: ' + dep)
            target_archs = out('lipo', '-archs', target).split()
            if not set(archs).issubset(target_archs):
                raise RuntimeError('Incompatible library slices: ' + str(target))
        if any(p.startswith(('/opt/homebrew/', '/usr/local/', '/Users/', '/workspace/')) for p in rpaths(f)):
            raise RuntimeError('Developer machine RPATH remains')
        report.append({'file': str(f.relative_to(app)), 'architectures': archs})
    if not report:
        raise RuntimeError('No Mach-O binaries in app')
    subprocess.run(['codesign', '--verify', '--deep', '--strict', '--verbose=2', str(app)], check=True)
    return report

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('app', type=Path)
    args = parser.parse_args()
    print(json.dumps(audit(args.app), indent=2))
