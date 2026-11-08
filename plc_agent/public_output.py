"""Publish experiment evidence without copying credentials or vendor projects."""
import hashlib
import json
from pathlib import Path
import re

from plc_agent.storage import atomic_json

TEXT_SUFFIXES = {'.md', '.csv', '.log', '.txt', '.json', '.jsonl', '.xml', '.c', '.h',
                 '.i', '.smt2', '.cfd', '.cfd-original', '.cfd-reduced', '.st', '.scl',
                 '.cex', '.smv', '.script', '.dot', '.vc3', '.cfa-final'}
EXCLUDED_DIRS = {'project', 'card', 'virtual_card', 'workspace', 'codex-home', '.git',
                 '.runtime', '.venv', 'node_modules', 'private', 'bin', 'obj'}
SECRET_FIELDS = {'api_key', 'authorization', 'access_token', 'refresh_token',
                 'password', 'secret', 'client_secret', 'bearer_token'}


def export(source, destination, *, secrets=(), path_replacements=None):
    """Create a new immutable public snapshot and an original/export hash map.

    ST/SCL bytes remain exact, so source hashes in receipts still refer to them.
    Transformed JSON/logs retain their original hashes in PUBLIC_MANIFEST.json.
    """
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if not source.is_dir() or destination == source or destination.is_relative_to(source):
        raise ValueError('Public destination must be outside the source experiment')
    if destination.exists():
        raise ValueError('Public snapshot already exists; choose another name')
    keys = tuple(k for k in secrets if isinstance(k, str) and k)
    replacements = path_replacements or {}

    def clean_text(value):
        for key in keys:
            value = value.replace(key, '[redacted]')
        for before, after in sorted(replacements.items(), key=lambda p: len(p[0]), reverse=True):
            # Plain logs can embed JSON-escaped Windows paths as well.
            variants = {before, before.replace('\\', '/'), before.replace('\\', '\\\\')}
            for variant in sorted(variants, key=len, reverse=True):
                value = value.replace(variant, after)
        return value

    def clean(value):
        if isinstance(value, dict):
            return {k: '[redacted]' if k.lower() in SECRET_FIELDS else clean(v) for k, v in value.items()}
        if isinstance(value, list):
            return [clean(v) for v in value]
        return clean_text(value) if isinstance(value, str) else value

    payload, records, omitted = {}, {}, []
    for path in sorted(source.rglob('*')):
        if not path.is_file():
            continue
        relative = path.relative_to(source); name = relative.as_posix()
        if (path.is_symlink() or not path.resolve().is_relative_to(source)
                or EXCLUDED_DIRS.intersection(relative.parts) or path.suffix.lower() not in TEXT_SUFFIXES):
            omitted.append({'path': name, 'reason': 'project/runtime/binary or non-evidence file'})
            continue
        raw = path.read_bytes()
        if path.suffix.lower() in ('.scl', '.st'):
            if any(key.encode('utf-8') in raw for key in keys):
                raise ValueError('Credential found in source code; refusing to modify its evidence hash: ' + name)
            public = raw
        else:
            text = raw.decode('utf-8-sig')
            if path.suffix.lower() == '.json':
                public = json.dumps(clean(json.loads(text)), ensure_ascii=False, indent=2, allow_nan=False).encode('utf-8')
            elif path.suffix.lower() == '.jsonl':
                public = ''.join(json.dumps(clean(json.loads(line)), ensure_ascii=False, allow_nan=False) + '\n'
                                 for line in text.splitlines() if line.strip()).encode('utf-8')
            else:
                public = clean_text(text).encode('utf-8')
            if any(key.encode('utf-8') in public for key in keys):
                raise ValueError('Credential remains after export: ' + name)
            if re.search(rb'(?i)(?:authorization\s*[:=]\s*["\x27]?bearer\s+)(?!\[redacted\])\S+', public):
                raise ValueError('Unredacted authorization header in ' + name)
        payload[name] = public
        records[name] = {'original_sha256': hashlib.sha256(raw).hexdigest(),
                         'public_sha256': hashlib.sha256(public).hexdigest(),
                         'bytes': len(public), 'transformed': public != raw}
    if not payload:
        raise ValueError('No experiment evidence to export')
    destination.mkdir(parents=True)
    for name, content in payload.items():
        target = destination / name; target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(content)
    manifest = {'schema': 'plc-public-output-v1', 'files': records, 'omitted': omitted,
                'scope': 'Published evidence snapshot; source files preserve exact bytes; credentials/local paths in text are removed. Excluded vendor projects and binaries are listed explicitly.'}
    atomic_json(destination/'PUBLIC_MANIFEST.json', manifest)
    return manifest
