#!/usr/bin/env python3
"""Record the signed build under test; does not mark any acceptance test passed."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
from bundle import is_macho

ROOT = Path(__file__).resolve().parents[1]

def fingerprints(app):
    hashes = {}
    for file in app.rglob('*'):
        if not file.is_file() or file.is_symlink() or '_CodeSignature' in file.parts:
            continue
        relative = str(file.relative_to(app))
        if is_macho(file):
            result = subprocess.run(['codesign', '-d', '--verbose=4', str(file)],
                                    text=True, capture_output=True, check=True)
            match = re.search(r'^CDHash=(\w+)$', result.stderr, re.MULTILINE)
            if not match:
                raise RuntimeError('Signed code has no CDHash: ' + relative)
            hashes[relative] = 'cdhash:' + match.group(1)
        else:
            hashes[relative] = 'sha256:' + hashlib.sha256(file.read_bytes()).hexdigest()
    return hashes

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('app', type=Path)
    p.add_argument('--output', type=Path, default=ROOT / 'release-acceptance.json')
    a = p.parse_args()
    record = json.loads((ROOT / 'release-acceptance.example.json').read_text())
    record['resource_hashes'] = fingerprints(a.app.resolve())
    a.output.write_text(json.dumps(record, indent=2) + '\n')
    print('Snapshot written; checks remain false:', a.output)
