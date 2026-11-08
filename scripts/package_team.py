"""Build a source-only team ZIP, optionally bundling hash-pinned Python wheels."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
FOLDERS = ('plc_agent', 'plc_probe', 'optional_local_tests', 'datasets', 'docs',
           'examples', 'scripts', 'tools', 'tests', 'course_materials',
           'integrations', 'reports/tia_final_20261104')
FILES = ('README.md', 'start.cmd', 'requirements.lock', '.env.example',
         '.gitignore', '.gitattributes', 'outputs/README.md', 'reports/README.md')
EXCLUDED = {'__pycache__', 'node_modules', '.pytest_cache', '.venv', '.runtime',
            'agent_data', '.git', 'private', 'bin', 'obj', '.vs'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--wheels', type=Path, help='Existing directory with scripts/dependencies.json wheels')
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error('Output already exists; choose a new name to preserve the previous package')
    payload = {}
    for folder in FOLDERS:
        for path in (ROOT / folder).rglob('*'):
            relative = path.relative_to(ROOT)
            if (path.is_file() and not path.is_symlink()
                    and not EXCLUDED.intersection(relative.parts)
                    and path.suffix not in ('.pyc', '.pyo', '.log', '.tmp')):
                payload[relative.as_posix()] = path.read_bytes()
    for name in FILES:
        payload[name] = (ROOT / name).read_bytes()
    if args.wheels:
        for item in json.loads((ROOT / 'scripts/dependencies.json').read_text(encoding='utf-8')):
            content = (args.wheels / item['filename']).read_bytes()
            if hashlib.sha256(content).hexdigest() != item['sha256']:
                raise ValueError('Wheel digest mismatch: ' + item['filename'])
            payload['vendor/wheels/' + item['filename']] = content
    try:
        revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
        dirty = bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT))
    except (OSError, subprocess.CalledProcessError):
        revision, dirty = 'unavailable', None
    manifest = {'schema': 'plc-team-package-v2', 'revision': revision, 'working_tree_dirty': dirty,
                'scope': 'Source and regression fixtures; no credentials, runtime or private run outputs.',
                'files': {name: hashlib.sha256(content).hexdigest() for name, content in sorted(payload.items())}}
    payload['PACKAGE_MANIFEST.json'] = json.dumps(manifest, ensure_ascii=False, indent=2).encode('utf-8')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(args.output, 'x', zipfile.ZIP_DEFLATED) as archive:
        for name, content in sorted(payload.items()):
            archive.writestr('PLC-Workbench/' + name, content)
    checksum = hashlib.sha256(args.output.read_bytes()).hexdigest()
    args.output.with_suffix(args.output.suffix + '.sha256').write_text(checksum + '  ' + args.output.name + '\n', encoding='utf-8')
    print(json.dumps({'file': str(args.output), 'sha256': checksum, 'files': len(payload),
                      'revision': revision, 'working_tree_dirty': dirty}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
