"""Target-aware static -> vendor compile -> finite behavior validation.

Compiler configuration is local and independent of model credentials. Offline
mode remains explicit; it can never stand in for a CODESYS completion receipt.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, field
from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path
import re
import threading
import uuid

from plc_probe.backend import BackendError
from .bank_contracts import questions
from .config import ROOT, STATE_ROOT
from .storage import atomic_json
from .st_source import mask_noncode, split_units

COMPILER_LOCK = threading.Lock()
RESERVED = set('BOOL BYTE WORD DWORD LWORD SINT INT DINT LINT USINT UINT UDINT ULINT REAL LREAL STRING WSTRING TIME LTIME DATE LDATE TOD LTOD DT LDT TRUE FALSE IF THEN ELSE ELSIF END_IF CASE OF END_CASE FOR TO BY DO END_FOR WHILE END_WHILE REPEAT UNTIL END_REPEAT RETURN EXIT AND OR XOR NOT MOD FUNCTION FUNCTION_BLOCK PROGRAM TYPE STRUCT END_STRUCT VAR END_VAR END_TYPE'.split())


def home_for(session):
    return session.project.path.parent.parent


@dataclass
class ValidationConfig:
    mode: str = 'offline'
    executable: str = ''
    profile: str = 'CODESYS V3.5 SP22 Patch 4'
    compile_timeout: int = 120
    unsupported_interface_types: list[str] = field(default_factory=lambda: ['VARIANT'])

    def validate(self):
        if self.mode not in ('offline', 'codesys'): raise ValueError('validation mode must be offline or codesys')
        if not isinstance(self.executable, str) or not isinstance(self.profile, str): raise ValueError('Invalid compiler paths/profile')
        if any(c in self.profile for c in ('"', '\r', '\n')): raise ValueError('Invalid CODESYS profile')
        if type(self.compile_timeout) is not int or not 10 <= self.compile_timeout <= 300: raise ValueError('Compile timeout must be 10..300 seconds')
        if not isinstance(self.unsupported_interface_types, list) or any(not isinstance(t, str) for t in self.unsupported_interface_types):
            raise ValueError('unsupported_interface_types must be a list of type names')

    @classmethod
    def load(cls, home=STATE_ROOT):
        path = Path(home) / 'validation.json'
        data = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
        if not isinstance(data, dict) or set(data) - set(cls.__dataclass_fields__): raise ValueError('Invalid validation configuration')
        config = cls(**data)
        config.validate()
        return config

    def save(self, home=STATE_ROOT):
        self.validate()
        atomic_json(Path(home) / 'validation.json', asdict(self))


def content_hash(code):
    return hashlib.sha256(code.replace('\r\n', '\n').encode('utf-8')).hexdigest()


def static_check(code, question, config):
    clean = mask_noncode(code)
    issues = []
    for section in re.finditer(r'\bVAR(?:_INPUT|_OUTPUT|_IN_OUT|_TEMP|_EXTERNAL|_GLOBAL)?\b(.*?)\bEND_VAR\b', clean, re.I | re.S):
        for declaration in re.finditer(r'(?:^|[;\n])\s*([A-Za-z_]\w*(?:\s*,\s*[A-Za-z_]\w*)*)\s*:(?!=)', section[1]):
            for name in declaration[1].split(','):
                name = name.strip()
                if name.upper() in RESERVED:
                    offset = section.start(1) + declaration.start(1)
                    issues.append({'code': 'reserved_identifier', 'identifier': name,
                                   'line': code.count('\n', 0, offset) + 1,
                                   'message': 'Identifier conflicts with the case-insensitive ST keyword ' + name.upper(),
                                   'repair_hint': 'Rename this identifier and its references; preserve the task interface.'})
    units = split_units(code)
    defined_types = {u['name'].upper() for u in units if u['kind'] == 'TYPE'}
    blocked = []
    for dtype in config.unsupported_interface_types:
        if dtype.upper() in defined_types: continue
        if re.search(r'^\| (?:Input|Output|Input/Output) \| `[^`]+` \| `[^`]*\b' + re.escape(dtype) + r'\b', question['text'], re.M | re.I):
            blocked.append({'code': 'target_interface_unavailable', 'type': dtype,
                            'message': 'The required interface type is not configured on this CODESYS target. Resolve the platform adapter/library before generation; do not narrow the task interface.'})
    return {'status': 'platform_blocked' if blocked else 'static_error' if issues else 'pass',
            'diagnostics': blocked + issues}


@lru_cache(maxsize=16)
def _file_fingerprint(signature):
    hashes = {name: hashlib.sha256(Path(name).read_bytes()).hexdigest() for name, _, _ in signature}
    return hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()


def validation_fingerprint(config, home=None):
    files = [Path(__file__), ROOT / 'plc_agent/st_source.py', ROOT / 'plc_agent/codesys_bank.py',
             ROOT / 'scripts/codesys_batch.py', ROOT / 'plc_agent/workflow.py',
             ROOT / 'plc_agent/engine.py', ROOT / 'plc_agent/toolbox.py']
    if config.mode == 'codesys':
        executable = Path(config.executable)
        files.extend([executable, executable.parent / 'Compiler.dll',
                      executable.parent.parent / 'Profiles' / (config.profile + '.profile.xml'),
                      executable.parent.parent / 'Templates/Standard.project'])
        libraries = Path(os.environ.get('ProgramData', 'C:/ProgramData')) / 'CODESYS/Managed Libraries/System'
        for name in ('Standard', 'Standard64', 'IoStandard'):
            files.extend(sorted(p for p in (libraries / name).rglob('*') if p.is_file()))
    if home is not None: files.append(Path(home) / 'validation.json')
    signature = tuple((str(p.resolve()), p.stat().st_size, p.stat().st_mtime_ns) for p in files if p.is_file())
    return hashlib.sha256((json.dumps(asdict(config), sort_keys=True) + _file_fingerprint(signature)).encode()).hexdigest()


class CodesysCompiler:
    def __init__(self, config, home):
        self.config, self.home = config, Path(home)

    def compile(self, source, qid, fingerprint):
        from .codesys_bank import read_receipt, run_bank
        data = source.read_bytes()
        sha = hashlib.sha256(data).hexdigest()
        key = hashlib.sha256((qid + sha + fingerprint).encode()).hexdigest()
        cache = self.home / 'compiler_cache' / key
        with COMPILER_LOCK:
            cached = read_receipt(cache / 'receipt.json')
            evidence=read_receipt(cached.get('evidence_path',''))
            rows=evidence.get('results',[])
            if (cached.get('source_sha256') == sha and cached.get('validation_fingerprint') == fingerprint
                    and cached.get('status') in ('pass', 'compile_error')
                    and evidence.get('summary',{}).get('environment_validated') is True
                    and len(rows)==1 and rows[0].get('source_sha256')==sha
                    and rows[0].get('status')==cached['status'] and rows[0].get('stage')=='compiled'):
                return {**cached, 'cached': True}
            executable = Path(self.config.executable)
            if not executable.is_file():
                return {'status': 'missing_dependency', 'message': 'Configure the CODESYS executable before generation.', 'source_sha256': sha}
            run = cache / uuid.uuid4().hex[:12]
            inputs = run / 'inputs' / qid
            inputs.mkdir(parents=True)
            (inputs / 'final.st').write_bytes(data)
            output = run / 'measurement'
            try:
                measured = run_bank(executable, self.config.profile, [qid], inputs.parent, output, self.config.compile_timeout)
                result = measured['results'][0]
                if not measured['summary']['environment_validated'] or measured['summary']['not_measured']:
                    status = 'missing_dependency' if not measured['summary']['environment_validated'] else 'tool_error'
                else: status = result['status']
                receipt = {'status': status, 'source_sha256': sha, 'validation_fingerprint': fingerprint,
                           'errors': result.get('errors', []), 'warnings': result.get('warnings', []),
                           'seconds': measured['seconds'], 'cached': False,
                           'evidence_path': str(output / 'results.json'),
                           'message': result.get('message', ''), 'target': self.config.profile}
                if measured.get('timed_out'): receipt.update(status='timeout', message='CODESYS compiler exceeded its time budget')
                if status in ('pass', 'compile_error'): atomic_json(cache / 'receipt.json', receipt)
                return receipt
            except (OSError, ValueError) as exc:
                return {'status': 'tool_error', 'source_sha256': sha, 'message': str(exc)}


class ValidationPipeline:
    def __init__(self, config, home, compiler=None, behavior=None):
        from .extended_eval import evaluate
        self.config, self.home = config, Path(home)
        self.compiler = compiler or CodesysCompiler(config, home)
        self.behavior = behavior or evaluate

    def fingerprint(self):
        return validation_fingerprint(self.config, self.home)

    def notes(self):
        notes = [
            'Target is real ' + self.config.profile + '. Both CODESYS code generation and finite behavior tests must pass.',
            'Avoid case-insensitive ST keywords as identifiers. In particular LINT is a type keyword, so lint cannot be a variable name.',
            'PV_COUNT/PV_COMPATIBLE/PV_READ/PV_WRITE belong to the local R4 backend, not the configured CODESYS libraries. Do not invent helpers or change required interfaces.',
            'Compiler errors are target failures; behavioral counterexamples are distinct. Preserve earlier successful requirements while repairing.',
            'STRING(254): LEN(STRING) and ADR/POINTER TO BYTE work on this target. Do not declare CHAR or index a STRING with [] or .at(); read bytes through a BYTE pointer.',
            'Use LTIME for long runtime accumulators; convert with TIME_TO_LTIME / LTIME_TO_TIME. Do not assign TIME directly to LTIME.',
            'Declare STRUCT types as TYPE Name : STRUCT ... END_STRUCT END_TYPE; fields use ":" not ":=".',
            'Initialize every output and internal state at power-up; accumulate CycleTime on the first valid scan as well.',
            'Remove empty VAR/VAR_INPUT/VAR_OUTPUT/VAR_IN_OUT blocks; CODESYS rejects them and the error cascades.',
            'For POINTER TO BYTE, prefer p[i] indexing for compatibility with the offline R4 parser; pointer dereference is valid in CODESYS but not supported by that offline adapter.',
            'A minimum alarm hold is measured from the triggering scan, not from the scan where the fault clears; release at the first scan at least 500ms after the trigger.',
            'STRING(254) parsing: use p := ADR(ipText); b := p[i]; n := LEN(ipText). Do not use CHAR, ipText[i], .at(), or p^.',
        ]
        try:
            from .backend_r4 import notes as backend_notes
            notes.extend(backend_notes() or [])
        except Exception:
            pass
        return notes

    def preflight(self, question):
        if self.config.mode != 'codesys': return None
        if not Path(self.config.executable).is_file():
            return {'status': 'missing_dependency', 'failure_stage': 'codesys',
                    'message': 'Configure the CODESYS executable before requesting model generation.'}
        template=Path(self.config.executable).parent.parent/'Templates/Standard.project'
        if not template.is_file():
            return {'status':'missing_dependency','failure_stage':'codesys',
                    'message':'CODESYS Standard.project template is missing; complete the toolchain setup before generation.'}
        for dtype in self.config.unsupported_interface_types:
            if re.search(r'^\| (?:Input|Output|Input/Output) \| `[^`]+` \| `[^`]*\b' + re.escape(dtype) + r'\b', question['text'], re.M | re.I):
                return {'status': 'platform_blocked', 'failure_stage': 'static',
                        'diagnostics': [{'code': 'target_interface_unavailable', 'type': dtype,
                                         'message': 'The required target interface needs an installed and validated adapter/library; preserve the original interface.'}]}
        return None

    def evaluate(self, source, qid):
        self.config.validate()
        before = hashlib.sha256(source.read_bytes()).hexdigest()
        fingerprint = self.fingerprint()
        result = {'status': 'tool_error', 'source_sha256': before, 'validation_mode': self.config.mode,
                  'validation_fingerprint': fingerprint, 'stages': {}, 'behavior_tested': False}
        if self.config.mode == 'codesys':
            question = next(q for q in questions() if q['id'] == qid)
            try:
                from .workflow import validate_candidate
                code=source.read_text(encoding='utf-8-sig')
                validate_candidate(code,question)
                checked = static_check(code, question, self.config)
            except ValueError as exc: checked = {'status': 'static_error', 'diagnostics': [{'message': str(exc)}]}
            result['stages']['static'] = checked
            if checked['status'] != 'pass': return {**result, **checked, 'failure_stage': 'static'}
            if not Path(self.config.executable).is_file():
                return {**result, 'status': 'missing_dependency', 'failure_stage': 'codesys',
                        'message': 'CODESYS executable is missing; configure validation before model generation.'}
            compiled = self.compiler.compile(source, qid, fingerprint)
            result['stages']['codesys'] = compiled
            if compiled.get('source_sha256') != before or hashlib.sha256(source.read_bytes()).hexdigest() != before:
                return {**result, 'status': 'source_conflict', 'failure_stage': 'codesys', 'message': 'Compiler evidence belongs to a different source'}
            if compiled['status'] != 'pass':
                return {**result, 'status': compiled['status'], 'failure_stage': 'codesys',
                        'primary_diagnostics': compiled.get('errors', [])[:5], 'message': compiled.get('message', '')}
        try: behavior = self.behavior(source, qid)
        except BackendError as exc: behavior = exc.result
        result['stages']['behavior'] = {k: v for k, v in behavior.items() if k not in ('cases', 'suites')}
        if hashlib.sha256(source.read_bytes()).hexdigest() != before or self.fingerprint() != fingerprint:
            return {**result, 'status': 'source_conflict', 'message': 'Source or validation environment changed during evaluation'}
        if (behavior.get('source_sha256') not in (None,before)
                or behavior.get('status') == 'pass' and behavior.get('source_sha256') != before):
            return {**result, 'status': 'source_conflict', 'message': 'Behavior evidence belongs to a different source'}
        return {**behavior, **{k: v for k, v in result.items() if k not in ('status', 'behavior_tested')},
                'status': behavior['status'], 'behavior_tested': behavior.get('behavior_tested', False),
                'failure_stage': None if behavior['status'] == 'pass' else 'behavior',
                'scope': 'CODESYS compile + finite offline behavior checks; no CODESYS runtime or formal proof.' if self.config.mode == 'codesys' else behavior.get('scope', '')}


def pipeline_for(session):
    home = home_for(session)
    return ValidationPipeline(ValidationConfig.load(home), home)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('status')
    config_parser = sub.add_parser('configure')
    config_parser.add_argument('--mode', choices=('offline', 'codesys'), required=True)
    config_parser.add_argument('--executable', default='')
    config_parser.add_argument('--profile', default='CODESYS V3.5 SP22 Patch 4')
    check_parser=sub.add_parser('check',help='Validate an existing candidate without any model request')
    check_parser.add_argument('question_id',choices=[q['id'] for q in questions()])
    check_parser.add_argument('source',type=Path)
    check_parser.add_argument('--output',type=Path)
    args = parser.parse_args()
    if args.command == 'configure':
        config = ValidationConfig(mode=args.mode, executable=args.executable, profile=args.profile)
        if config.mode == 'codesys' and not Path(config.executable).is_file(): parser.error('CODESYS executable not found')
        config.save()
    config = ValidationConfig.load()
    if args.command=='check':
        result=ValidationPipeline(config,STATE_ROOT).evaluate(args.source.resolve(),args.question_id)
        if args.output:atomic_json(args.output,result)
        print(json.dumps({k:v for k,v in result.items() if k not in ('cases','suites')},ensure_ascii=False,indent=2))
        return 0 if result['status']=='pass' else 1
    print(json.dumps({'configuration': asdict(config), 'fingerprint': validation_fingerprint(config, STATE_ROOT),
                      'executable_exists': Path(config.executable).is_file(), 'model_calls': 0}, ensure_ascii=False, indent=2))


if __name__ == '__main__': raise SystemExit(main())
