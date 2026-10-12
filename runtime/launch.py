#!/usr/bin/env python3
"""Bundled CPython worker: validate supplied data, prepare private images, exec runtime.

No network, SDK, compiler, shell quoting, or system Python is used on the end user's Mac.
"""
import argparse
import contextlib
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import runpy
import struct
import sys
import tempfile

SCRIPT = Path(__file__).resolve()
RESOURCES = SCRIPT.parent.parent
BACKEND = SCRIPT.parent
CONTENTS = RESOURCES.parent

def atomic_text(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + '.', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporary, path)
    finally:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(temporary)

def read_sfo(data):
    if len(data) < 20:
        raise ValueError('Truncated param.sfo')
    magic, version, keys, values, count = struct.unpack_from('<4sIIII', data)
    if magic != b'\0PSF' or count > 4096 or 20 + count * 16 > len(data):
        raise ValueError('Invalid param.sfo header')
    if not 20 + count * 16 <= keys <= values <= len(data):
        raise ValueError('Invalid param.sfo tables')
    result = {}
    for i in range(count):
        key, fmt, size, capacity, offset = struct.unpack_from('<HHIII', data, 20 + i * 16)
        start = keys + key
        if not keys <= start < values:
            raise ValueError('Invalid param.sfo key offset')
        end = data.find(b'\0', start, values)
        if end < 0:
            raise ValueError('Unterminated param.sfo key')
        if size > capacity or values + offset + capacity > len(data):
            raise ValueError('Invalid param.sfo value range')
        name = data[start:end].decode('utf-8', 'strict')
        if name in result:
            raise ValueError('Duplicate param.sfo key')
        value = data[values + offset:values + offset + size]
        if fmt in (0x204, 0x004):
            result[name] = value.rstrip(b'\0').decode('utf-8', 'strict')
        elif fmt == 0x404 and size == 4:
            result[name] = struct.unpack('<I', value)[0]
        else:
            raise ValueError('Unsupported param.sfo value format')
    return result

def load_prepare(scripts):
    spec = importlib.util.spec_from_file_location('prepare', scripts / 'prepare.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def validate(game, policy, scripts):
    game = Path(game).expanduser().resolve(strict=True)
    required = ['eboot.bin', 'sce_sys/param.sfo', 'sce_module/libc.prx', 'sce_module/libSceFios2.prx']
    for name in required:
        p = game / name
        if not p.is_file() or not 0 < p.stat().st_size <= 512 * 1024 * 1024:
            raise ValueError('Missing, empty, or oversized required file: ' + name)
    assets = game / 'dvdroot_ps4'
    if not assets.is_dir() or not any(assets.iterdir()):
        raise ValueError('dvdroot_ps4 is missing or empty')
    sfo = read_sfo((game / 'sce_sys/param.sfo').read_bytes())
    allowed_ids = {policy['title_id'], *policy.get('experimental_title_ids', [])}
    if sfo.get('TITLE_ID') not in allowed_ids or sfo.get('APP_VER') != policy['app_version']:
        raise ValueError('Expected ' + policy['title_id'] + ' v' + policy['app_version'] + '; found ' +
                         str(sfo.get('TITLE_ID')) + ' v' + str(sfo.get('APP_VER')))
    prepare = load_prepare(scripts)
    # This backend expects plaintext SELF, not bbhost's decrypted flat ELF.
    eboot = (game / 'eboot.bin').read_bytes()
    prepare.parse_self(eboot)
    for name in required[2:]:
        prepare.parse_self((game / name).read_bytes())
    digest = hashlib.sha256(eboot).hexdigest()
    accepted = policy.get('accepted_eboot_sha256', [])
    if policy.get('require_verified_hash') and digest not in accepted:
        raise ValueError('This executable hash is not an approved v1.09 SELF dump for this release')
    return {'ok': True, 'game': str(game), 'title_id': sfo['TITLE_ID'], 'app_version': sfo['APP_VER'],
            'eboot_sha256': digest, 'hash_verified': digest in accepted,
            'message': 'Game files validated' if digest in accepted else
                       'v1.09 metadata and plaintext layout validated; exact executable hash unverified'}

def run_script(name, arguments):
    old = sys.argv
    sys.argv = [str(BACKEND / 'scripts' / name)] + list(map(str, arguments))
    try:
        runpy.run_path(sys.argv[0], run_name='__main__')
    except SystemExit as exc:
        if exc.code not in (None, 0):
            raise RuntimeError(name + ' failed with status ' + str(exc.code)) from exc
    finally:
        sys.argv = old

def make_config(resolution, fsr):
    sizes = ('1280x720', '1920x1080', '2560x1440', '3840x2160')
    return '\n'.join(['output_res=' + sizes[resolution], 'live_resolution=0',
                      'upscaler=' + ('fsr3' if fsr else 'off'),
                      'preset=' + ('1' if fsr else '0'), 'show_fps=1',
                      'debug_menu=0', 'debug_camera=0', 'skip_intro=0']) + '\n'

def launch(a, policy):
    checked = validate(a.game, policy, BACKEND / 'scripts')
    game = Path(checked['game'])
    data = Path(a.data).expanduser().resolve()
    data.mkdir(parents=True, exist_ok=True)
    # Held through exec. One app copy cannot overwrite prepared images of another live instance.
    lockfd = os.open(data / 'runtime.lock', os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(lockfd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        os.close(lockfd)
        raise RuntimeError('Bloodborne is already running with this data directory') from exc
    os.set_inheritable(lockfd, True)
    generated = data / 'out'
    user = data / 'user'
    generated.mkdir(exist_ok=True)
    user.mkdir(exist_ok=True)
    cfg = data / 'bbport.ini'
    atomic_text(cfg, make_config(a.resolution, a.fsr))
    env = {k: v for k, v in os.environ.items() if not k.startswith(('DYLD_', 'VK_', 'BB_', 'MVK_'))}
    env.update(BB_CONFIG=str(cfg), BB_GPU_USER_DIR=str(user), BB_USER_DIR=str(user),
               BB_VULKAN_LOADER=str(CONTENTS / 'Frameworks/x86_64/libvulkan.1.dylib'),
               VK_DRIVER_FILES=str(RESOURCES / 'vulkan/icd.d/MoltenVK_icd.json'),
               VK_LOADER_LAYERS_DISABLE='~implicit~', BB_PRESENT_MODE='Fifo',
               BB_FPS=a.fps, BB_VBLANK_HZ='90' if a.fps == '90' else '60',
               BB_UPSCALER='fsr3' if a.fsr else 'off', BB_PREP_WORKERS='0',
               BB_FRAMES_AHEAD='1', BB_INPUT_MODE='auto',
               MVK_CONFIG_FAST_MATH_ENABLED='0', MVK_CONFIG_USE_METAL_ARGUMENT_BUFFERS='1',
               MVK_CONFIG_PREFILL_METAL_COMMAND_BUFFERS='0', MVK_CONFIG_LOG_LEVEL='2')
    # Driver selection is based only on a bundled ICD, never an inherited VK_* path.
    kosmic_icd = RESOURCES / 'vulkan/kosmickrisp/kosmickrisp_mesa_icd.json'
    driver_name = 'MoltenVK'
    if kosmic_icd.is_file():
        driver_name = 'KosmicKrisp'
        env['VK_DRIVER_FILES'] = str(kosmic_icd)
        for key in tuple(env):
            if key.startswith('MVK_'):
                del env[key]
    if a.perf_diagnostics:
        env.update(BB_FRAME_STATS='1', BB_PRESENT_STATS='1', BB_BUFFER_STATS='1')
    namespace = {'driver': driver_name, 'game': checked['eboot_sha256'], 'os': platform.mac_ver()[0],
                 'os_build': os.uname().version,
                 'build': json.loads((RESOURCES / 'dependencies.lock.json').read_text()),
                 'mvk': {k: v for k, v in env.items() if k.startswith('MVK_')},
                 'cache_schema': 1}
    env['BB_PIPELINE_CACHE_NAMESPACE'] = hashlib.sha256(json.dumps(namespace, sort_keys=True).encode()).hexdigest()
    env['BB_PIPELINE_CACHE_DIR'] = str(data / 'driver-cache')
    # Preserve the fork's temporary conservative DrawPipeline workaround.
    toggle = data / 'macos-gpu-toggles.txt'
    atomic_text(toggle, '137438953472\n')
    env['BB_TOGGLE_FILE'] = str(toggle)
    os.environ.clear()
    os.environ.update(env)
    sys.path.insert(0, str(BACKEND / 'scripts'))
    os.chdir(BACKEND)
    print(checked['message'], flush=True)
    print('Preparing private guest images. Original dump remains read-only.', flush=True)
    print('Vulkan driver: ' + driver_name + '; performance diagnostics: ' + ('on' if a.perf_diagnostics else 'off'), flush=True)
    run_script('prepare.py', [game, '--out', generated])
    run_script('link_libc.py', [game, '--out', generated])
    run_script('link_modules.py', [game, '--out', generated])
    run_script('content_profile.py', [game, '--out', generated, '--sku', 'full'])
    # Derive resolution from upstream patch helpers, keeping the UI at output resolution.
    import patches
    settings = patches.read_settings(cfg)
    scaled = patches.scaled_sizes(settings)
    patchargs = ['--out', generated, '--fps', a.fps, '--settings', cfg, '--game-dir', game,
                 '--extra', 'Skip Intro + warning message' if a.skip_intro else '',
                 '--patches-dir', data / 'patches', '--patches-config', data / 'patches.json']
    if scaled:
        render, output_res = scaled
        patchargs += ['--render-res', str(render[0]) + 'x' + str(render[1]),
                      '--output-res', str(output_res[0]) + 'x' + str(output_res[1])]
        env['BB_DMEM_MB'] = '9152'
        env['BB_RENDER_RES'] = str(render[0]) + 'x' + str(render[1])
        env['BB_OUTPUT_RES'] = str(output_res[0]) + 'x' + str(output_res[1])
    run_script('patches.py', patchargs)
    command = [str(CONTENTS / 'Helpers/bb-runtime'), str(generated / 'boot-linked.bin'),
               '--content-profile', str(generated / 'content.bin'), '--patches', str(generated / 'patches.bin'),
               '--app0', str(game), '--user', str(user), '--timeout', '0']
    print('Starting x86-64 macOS runtime under Rosetta.', flush=True)
    os.execve(command[0], command, env)

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--validate', action='store_true')
    p.add_argument('--game', type=Path, required=True)
    p.add_argument('--data', type=Path, default=Path.home() / 'Library/Application Support/BloodborneResearch')
    p.add_argument('--fps', choices=['30', '60', '90'], default='30')
    p.add_argument('--resolution', type=int, choices=[0, 1, 2, 3], default=0)
    p.add_argument('--fsr', action='store_true')
    p.add_argument('--perf-diagnostics', action='store_true', help='Enable runtime frame/present/buffer statistics where supported')
    p.add_argument('--skip-intro', action='store_true')
    a = p.parse_args()
    try:
        policy = json.loads((RESOURCES / 'game-policy.json').read_text())
        if a.validate:
            print(json.dumps(validate(a.game, policy, BACKEND / 'scripts')))
        else:
            launch(a, policy)
    except (ValueError, OSError, RuntimeError, struct.error, ImportError) as exc:
        if a.validate:
            print(json.dumps({'ok': False, 'message': str(exc)}))
        else:
            print('LAUNCH STOPPED: ' + str(exc), file=sys.stderr, flush=True)
        return 1
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
