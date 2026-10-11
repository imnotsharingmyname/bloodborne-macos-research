#!/usr/bin/env python3
"""Copy each Mach-O dependency closure and rewrite load commands before signing."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

def out(*args):
    return subprocess.check_output(list(map(str, args)), text=True)

def run(*args):
    subprocess.run(list(map(str, args)), check=True)

def is_macho(path):
    if not path.is_file() or path.is_symlink():
        return False
    with path.open('rb') as f:
        magic = f.read(4)
    return magic in (b'\xfe\xed\xfa\xce', b'\xce\xfa\xed\xfe',
                     b'\xfe\xed\xfa\xcf', b'\xcf\xfa\xed\xfe',
                     b'\xca\xfe\xba\xbe', b'\xbe\xba\xfe\xca',
                     b'\xca\xfe\xba\xbf', b'\xbf\xba\xfe\xca')

def system(path):
    return path.startswith('/System/Library/') or path.startswith('/usr/lib/')

def dependencies(path):
    lines = out('otool', '-L', path).splitlines()[1:]
    return [line.strip().split(' (compatibility version', 1)[0] for line in lines if 'compatibility version' in line]

def rpaths(path):
    return re.findall(r'cmd LC_RPATH\n\s+cmdsize \d+\n\s+path (.*?) \(offset', out('otool', '-l', path))

class Closure:
    def __init__(self, app, arch, executable, search=()):
        self.app = app
        self.arch = arch
        self.executable = executable.resolve()
        self.search = list(map(Path, search))
        self.frameworks = app / ('Contents/Frameworks/' + arch)
        self.frameworks.mkdir(parents=True, exist_ok=True)
        self.mapping = {}
        self.names = {}
        self.rows = []

    def expand(self, text, owner):
        text = text.replace('@loader_path', str(owner.parent))
        return text.replace('@executable_path', str(self.executable.parent))

    def resolve(self, dep, owner, inherited):
        if dep.startswith('@rpath/'):
            tail = dep[len('@rpath/'):]
            roots = [self.expand(p, owner) for p in rpaths(owner)] + inherited
            roots += [str(p) for p in self.search]
            candidates = [Path(p) / tail for p in roots]
        elif dep.startswith('@'):
            candidates = [Path(self.expand(dep, owner))]
        elif dep.startswith('/'):
            candidates = [Path(dep)]
        else:
            candidates = [owner.parent / dep] + [p / dep for p in self.search]
        for path in candidates:
            if path.is_file():
                return path.resolve()
        raise RuntimeError('Unresolved dependency: ' + dep + ' required by ' + str(owner))

    def add(self, source, dest=None, inherited=()):
        source = source.resolve()
        if source in self.mapping:
            return self.mapping[source]
        if '.framework' in str(source) and not system(str(source)):
            raise RuntimeError('External framework needs resource-aware bundling: ' + str(source))
        if self.arch not in out('lipo', '-archs', source).split():
            raise RuntimeError('Wrong architecture dependency: ' + str(source))
        dest = dest or self.frameworks / source.name
        if dest.name in self.names and self.names[dest.name] != source:
            raise RuntimeError('Dependency basename collision: ' + dest.name)
        self.names[dest.name] = source
        self.mapping[source] = dest  # register before recursion, allowing dependency cycles
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.resolve() != source:
            shutil.copy2(source, dest)
        slices = out('lipo', '-archs', source).split()
        if len(slices) > 1:
            temporary = dest.with_name(dest.name + '.thin')
            run('lipo', dest, '-thin', self.arch, '-output', temporary)
            temporary.replace(dest)
        # Remove stale signatures; the entire closure is signed again later.
        subprocess.run(['codesign', '--remove-signature', str(dest)],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        ids = out('otool', '-D', source).splitlines()[1:]
        old_id = ids[0].strip() if ids else None
        own_rpaths = [self.expand(p, source) for p in rpaths(source)]
        for dep in dependencies(source):
            if system(dep) or dep == old_id:
                continue
            target = self.add(self.resolve(dep, source, own_rpaths + list(inherited)),
                              inherited=own_rpaths + list(inherited))
            relative = os.path.relpath(target, dest.parent)
            run('install_name_tool', '-change', dep, '@loader_path/' + relative, dest)
        if old_id:
            run('install_name_tool', '-id', '@rpath/' + dest.name, dest)
        for rp in set(rpaths(dest)):
            run('install_name_tool', '-delete_rpath', rp, dest)
        self.rows.append({'file': str(dest.relative_to(self.app)), 'architecture': self.arch,
                          'original_basename': source.name})
        return dest

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('app', type=Path)
    for name in ('guest', 'gpu', 'loader', 'driver', 'python'):
        p.add_argument('--' + name, type=Path, required=True)
    a = p.parse_args()
    a.app = a.app.resolve()
    guest = Closure(a.app, 'x86_64', a.guest, [a.gpu.parent, a.loader.parent])
    # Canonical names are used by the launch environment and ICD.
    guest.add(a.loader, guest.frameworks / 'libvulkan.1.dylib')
    guest.add(a.driver, guest.frameworks / 'libMoltenVK.dylib')
    guest.add(a.gpu, guest.frameworks / 'libbbgpu.dylib')
    guest.add(a.guest, a.app / 'Contents/Helpers/bb-runtime')
    python = Closure(a.app, 'arm64', a.python, [a.python.parent.parent / 'lib'])
    python.add(a.python, a.app / 'Contents/Helpers/python3.13')
    source_stdlib = a.python.parent.parent / 'lib/python3.13'
    for module in source_stdlib.rglob('*.so'):
        if is_macho(module):
            dest = a.app / 'Contents/Resources/python/lib/python3.13' / module.relative_to(source_stdlib)
            if dest.exists():
                python.add(module, dest)
    report = guest.rows + python.rows
    (a.app / 'Contents/Resources/dependency-report.json').write_text(json.dumps(report, indent=2))

if __name__ == '__main__':
    main()
