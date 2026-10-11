#!/usr/bin/env python3
"""Maintainer build orchestrator. Apple SDK/toolchain required only on builder."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tarfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / '.work'
OUT = ROOT / 'out'

def run(*args, cwd=None, env=None):
    print('+', ' '.join(map(str, args)), flush=True)
    subprocess.run(list(map(str, args)), cwd=cwd, env=env, check=True)

def output(*args):
    return subprocess.check_output(list(map(str, args)), text=True).strip()

def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()

def safe_extract(archive, destination):
    destination = Path(destination).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive) as tf:
        for entry in tf.getmembers():
            target = (destination / entry.name).resolve()
            if target != destination and destination not in target.parents:
                raise ValueError('archive path escapes extraction root')
            if entry.isdev() or entry.isfifo():
                raise ValueError('archive contains special files')
            if entry.issym() or entry.islnk():
                base = target.parent if entry.issym() else destination
                link = (base / entry.linkname).resolve()
                if link != destination and destination not in link.parents:
                    raise ValueError('archive link escapes extraction root')
        tf.extractall(destination)

def download(item, name):
    dest = WORK / 'downloads' / name
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists() or sha256(dest) != item['sha256']:
        temp = dest.with_suffix(dest.suffix + '.partial')
        print('Downloading', item['url'], flush=True)
        with urllib.request.urlopen(item['url'], timeout=120) as src, temp.open('wb') as dst:
            shutil.copyfileobj(src, dst)
        if sha256(temp) != item['sha256']:
            temp.unlink()
            raise RuntimeError('download SHA-256 mismatch: ' + name)
        temp.replace(dest)
    return dest

def checkout(item, path):
    if not (path / '.git').exists():
        path.mkdir(parents=True, exist_ok=True)
        run('git', 'init', path)
        run('git', '-C', path, 'remote', 'add', 'origin', item['url'])
    if output('git', '-C', path, 'remote', 'get-url', 'origin') != item['url']:
        raise RuntimeError('cached repository origin changed: ' + str(path))
    try:
        current = output('git', '-C', path, 'rev-parse', 'HEAD')
    except subprocess.CalledProcessError:
        current = ''
    if current != item['commit']:
        run('git', '-C', path, 'fetch', '--depth', '1', 'origin', item['commit'])
        run('git', '-C', path, 'checkout', '--detach', item['commit'])
    if output('git', '-C', path, 'rev-parse', 'HEAD') != item['commit']:
        raise RuntimeError('source pin mismatch')
    run('git', '-C', path, 'submodule', 'update', '--init', '--recursive')

def tools(lock):
    venv = WORK / 'tools'
    python = venv / 'bin/python3'
    if not python.exists():
        run(sys.executable, '-m', 'venv', venv)
    stamp = venv / 'versions.json'
    wanted = lock['builder_tools']
    if not stamp.exists() or json.loads(stamp.read_text()) != wanted:
        run(python, '-m', 'pip', 'install', '--disable-pip-version-check',
            'cmake==' + wanted['cmake'], 'ninja==' + wanted['ninja'])
        stamp.write_text(json.dumps(wanted))
    return venv / 'bin/cmake', venv / 'bin/ninja'

def cmake_build(cmake, source, build, arch, jobs, prefix=None, options=(), install=False):
    args = [cmake, '-S', source, '-B', build, '-G', 'Ninja',
            '-DCMAKE_MAKE_PROGRAM=' + str(WORK / 'tools/bin/ninja'),
            '-DCMAKE_BUILD_TYPE=RelWithDebInfo',
            '-DCMAKE_EXE_LINKER_FLAGS=-Wl,-headerpad_max_install_names',
            '-DCMAKE_SHARED_LINKER_FLAGS=-Wl,-headerpad_max_install_names',
            '-DCMAKE_TOOLCHAIN_FILE=' + str(ROOT / ('cmake/apple-' + arch + '.cmake'))]
    if prefix:
        args += ['-DCMAKE_INSTALL_PREFIX=' + str(prefix), '-DCMAKE_PREFIX_PATH=' + str(prefix)]
    run(*(args + list(options)))
    run(cmake, '--build', build, '--parallel', jobs)
    if install:
        run(cmake, '--install', build)

def copy_licenses(source, dest):
    dest.mkdir(parents=True, exist_ok=True)
    for p in source.rglob('*'):
        if p.is_file() and not p.is_symlink() and p.stat().st_size < 2_000_000:
            name = p.name.lower()
            if name.startswith(('license', 'licence', 'copying', 'notice')):
                rel = p.relative_to(source)
                if '.git' in rel.parts:
                    continue
                q = dest / rel
                q.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(p, q)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--launcher-only', action='store_true', help='UI scaffold; cannot launch a game')
    parser.add_argument('--runtime-arch', choices=['x86_64', 'arm64'], default='x86_64')
    parser.add_argument('--jobs', type=int, default=min(os.cpu_count() or 4, 8))
    args = parser.parse_args()
    if platform.system() != 'Darwin':
        raise RuntimeError('Use an Apple Silicon Mac/Xcode 26 builder')
    if output('/usr/sbin/sysctl', '-n', 'hw.optional.arm64') != '1':
        raise RuntimeError('This pipeline requires Apple Silicon')
    if args.runtime_arch == 'arm64' and not args.launcher_only:
        raise RuntimeError('No native ARM64 guest backend is implemented. See GUIDE.md section 4; changing CMAKE_OSX_ARCHITECTURES cannot translate game code.')
    if not args.launcher_only:
        probe = subprocess.run(['/usr/bin/arch', '-x86_64', '/usr/bin/true'],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if probe.returncode:
            raise RuntimeError('Install Rosetta through Apple\'s supported flow on this builder; generated x86-64 shader tools must execute during the build')
    if int(output('xcrun', '--sdk', 'macosx', '--show-sdk-version').split('.')[0]) < 26:
        raise RuntimeError('The pinned fork needs a macOS 26 SDK; select Xcode 26 tools')
    WORK.mkdir(exist_ok=True)
    OUT.mkdir(exist_ok=True)
    lock = json.loads((ROOT / 'dependencies.lock.json').read_text())
    cmake, _ = tools(lock)
    cmake_build(cmake, ROOT, WORK / 'launcher', 'arm64', args.jobs)
    built = WORK / 'launcher/Bloodborne.app'
    app = OUT / 'Bloodborne.app'
    if app.exists():
        shutil.rmtree(app)  # generated output only
    shutil.copytree(built, app, symlinks=True)
    resources = app / 'Contents/Resources'
    helpers = app / 'Contents/Helpers'
    resources.mkdir(exist_ok=True)
    helpers.mkdir(exist_ok=True)
    shutil.copy2(ROOT / 'config/game-policy.json', resources)
    shutil.copy2(ROOT / 'dependencies.lock.json', resources)
    shutil.copy2(ROOT / 'README-END-USER.txt', resources)
    if args.launcher_only:
        (resources / 'BUILD-STATUS.txt').write_text('Launcher-only scaffold. No game runtime is bundled.\n')
        run(sys.executable, ROOT / 'scripts/sign.py', app, '--identity', '-')
        print('Built UI scaffold:', app)
        return

    source = WORK / 'source'
    checkout(lock['source'], source)
    from patch_source import apply
    apply(source)
    # Pinned upstream patch application/configuration lives in its build script.
    for key in ('vulkan_headers', 'vulkan_loader', 'spirv_cross'):
        checkout(lock[key], WORK / key)
    prefix = WORK / 'prefix-x86_64'
    cmake_build(cmake, WORK / 'vulkan_headers', WORK / 'headers-build', 'x86_64', args.jobs,
                prefix, install=True, options=['-DVULKAN_HEADERS_ENABLE_TESTS=OFF'])
    cmake_build(cmake, WORK / 'vulkan_loader', WORK / 'loader-build', 'x86_64', args.jobs,
                prefix, install=True, options=['-DBUILD_TESTS=OFF', '-DBUILD_WSI_XLIB_SUPPORT=OFF',
                '-DBUILD_WSI_XCB_SUPPORT=OFF', '-DBUILD_WSI_WAYLAND_SUPPORT=OFF',
                '-DUPDATE_DEPS=OFF', '-DVULKAN_HEADERS_INSTALL_DIR=' + str(prefix)])
    cmake_build(cmake, WORK / 'spirv_cross', WORK / 'cross-build', 'x86_64', args.jobs,
                prefix, install=True, options=['-DSPIRV_CROSS_SHARED=OFF', '-DSPIRV_CROSS_STATIC=ON',
                '-DSPIRV_CROSS_CLI=OFF', '-DSPIRV_CROSS_ENABLE_TESTS=OFF'])
    loader = (prefix / 'lib/libvulkan.1.dylib').resolve(strict=True)
    env = dict(os.environ)
    env['PATH'] = str(WORK / 'tools/bin') + ':' + env.get('PATH', '')
    env['CMAKE'] = str(cmake)
    env['BB_BUILD_JOBS'] = str(args.jobs)
    env['BB_VULKAN_LOADER'] = str(loader)
    # Force the private prefix for direct native guest MSL compiler dependencies.
    run('/bin/bash', source / 'scripts/build_macos.sh',
        '-DCMAKE_PREFIX_PATH=' + str(prefix), '-DCMAKE_OSX_DEPLOYMENT_TARGET=26.0',
        '-DCMAKE_EXE_LINKER_FLAGS=-Wl,-headerpad_max_install_names',
        '-DCMAKE_SHARED_LINKER_FLAGS=-Wl,-headerpad_max_install_names',
        '-DBB_SPIRV_CROSS_INCLUDE=' + str(prefix / 'include'),
        '-DBB_SPIRV_CROSS_MSL=' + str(prefix / 'lib/libspirv-cross-msl.a'),
        '-DBB_SPIRV_CROSS_GLSL=' + str(prefix / 'lib/libspirv-cross-glsl.a'),
        '-DBB_SPIRV_CROSS_CORE=' + str(prefix / 'lib/libspirv-cross-core.a'), env=env)

    mvkroot = WORK / 'moltenvk'
    safe_extract(download(lock['moltenvk'], 'MoltenVK-macos.tar'), mvkroot)
    candidates = [p for p in mvkroot.rglob('libMoltenVK.dylib') if not p.is_symlink()]
    if not candidates:
        raise RuntimeError('MoltenVK package layout changed: no dynamic driver')
    driver = candidates[0]
    if 'x86_64' not in output('lipo', '-archs', driver).split():
        raise RuntimeError('The driver must contain an x86-64 slice for this runtime')

    # Build an arm64 CPython helper; no system Python is needed on the user's Mac.
    py_archive = download(lock['python'], 'Python-' + lock['python']['version'] + '.tgz')
    pyr = WORK / 'python-source'
    safe_extract(py_archive, pyr)
    pysrc = pyr / ('Python-' + lock['python']['version'])
    pyprefix = WORK / 'python-install'
    pybuild = WORK / 'python-build'
    pybuild.mkdir(exist_ok=True)
    pyenv = dict(os.environ)
    pyenv.update(MACOSX_DEPLOYMENT_TARGET='26.0', CFLAGS='-O2 -arch arm64',
                 LDFLAGS='-arch arm64', PKG_CONFIG='/usr/bin/false')
    run(pysrc / 'configure', '--prefix=' + str(pyprefix), '--enable-shared',
        '--without-ensurepip', '--disable-test-modules', '--with-pkg-config=no', cwd=pybuild, env=pyenv)
    run('make', '-j' + str(args.jobs), cwd=pybuild, env=pyenv)
    run('make', 'install', cwd=pybuild, env=pyenv)
    pybin = pyprefix / 'bin/python3.13'
    pydir = resources / 'python'
    shutil.copytree(pyprefix / 'lib/python3.13', pydir / 'lib/python3.13', symlinks=True,
                    ignore=shutil.ignore_patterns('__pycache__', 'test', 'tests', 'site-packages'))
    shutil.copy2(pybin, helpers / 'python3.13')
    shutil.copy2(source / 'out/bb-probe', helpers / 'bb-runtime')
    backend = resources / 'backend'
    backend.mkdir()
    for directory in ('scripts', 'patches'):
        shutil.copytree(source / directory, backend / directory,
                        ignore=shutil.ignore_patterns('__pycache__'))
    shutil.copy2(ROOT / 'runtime/launch.py', backend / 'launch.py')
    run(sys.executable, ROOT / 'scripts/bundle.py', app,
        '--guest', source / 'out/bb-probe', '--gpu', source / 'out/macos/gpu/libbbgpu.dylib',
        '--loader', loader, '--driver', driver, '--python', pybin)
    # The ICD is written with a path relative to its JSON, unaffected by translocation.
    icddir = resources / 'vulkan/icd.d'
    icddir.mkdir(parents=True)
    (icddir / 'MoltenVK_icd.json').write_text(json.dumps({
        'file_format_version': '1.0.0', 'ICD': {
            'library_path': '../../../Frameworks/x86_64/libMoltenVK.dylib',
            'api_version': '1.4.0', 'is_portability_driver': True}}, indent=2))
    notice = resources / 'Licenses'
    for name, location in [('metalborne', source), ('Vulkan-Headers', WORK / 'vulkan_headers'),
                           ('Vulkan-Loader', WORK / 'vulkan_loader'), ('SPIRV-Cross', WORK / 'spirv_cross'),
                           ('MoltenVK', mvkroot), ('Python', pysrc), ('BuildKit', ROOT / 'LICENSES')]:
        copy_licenses(location, notice / name)
    # Capture both declared pins and exact submodule / FetchContent provenance.
    manifest = dict(lock, host=platform.platform(), sdk=output('xcrun', '--show-sdk-version'),
                    compiler=output('xcrun', 'clang', '--version'),
                    source_submodules=output('git', '-C', source, 'submodule', 'status', '--recursive'),
                    architecture={'launcher': 'arm64', 'python': 'arm64', 'game_runtime': 'x86_64'},
                    status='experimental; full-game MoltenVK and public release acceptance unverified')
    (resources / 'build-manifest.json').write_text(json.dumps(manifest, indent=2))
    run(sys.executable, ROOT / 'scripts/sign.py', app, '--identity', '-')
    run(sys.executable, ROOT / 'scripts/audit.py', app)
    # Buffer submission/readback is a build smoke test, NOT game boot acceptance.
    smoke_env = dict(os.environ, BB_VULKAN_LOADER=str(app / 'Contents/Frameworks/x86_64/libvulkan.1.dylib'),
                     VK_DRIVER_FILES=str(icddir / 'MoltenVK_icd.json'), VK_LOADER_LAYERS_DISABLE='~implicit~')
    run(app / 'Contents/Helpers/bb-runtime', '--vulkan-only', env=smoke_env)
    print('Built experimental app:', app)
    print('Public release is gated; read GUIDE.md and scripts/package_mac.sh.')

if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, OSError, ValueError, subprocess.CalledProcessError) as exc:
        print('BUILD STOPPED:', exc, file=sys.stderr)
        sys.exit(1)
