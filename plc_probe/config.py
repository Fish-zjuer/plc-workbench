from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import urllib.request
import zipfile
from functools import lru_cache

ROOT = Path(__file__).resolve().parents[1]
VERSION = "0.7.0"
ARCHIVE_SHA256 = "4f97fcacffc3e26622f7b570b533e2ccab2fb6b61442b38c0cfde1d31096767e"
ARCHIVE_URL = f"https://github.com/Autonomy-Logic/STruCpp/releases/download/v{VERSION}/strucpp-win32-x64.zip"


def base_cache_dir() -> Path:
    for parent in ROOT.parents:
        if (parent / "_cache").is_dir():
            return parent / "_cache" / "plc-probe"
    return Path.home() / ".cache" / "plc-probe"


def backend_profile_path() -> Path:
    return Path(os.environ.get('PLC_AGENT_HOME',ROOT/'agent_data'))/'backend.json'


def selected_backend() -> Path | None:
    override=os.environ.get('STRUC_PP_HOME')
    if override:return Path(override).expanduser().resolve()
    path=backend_profile_path()
    if path.exists():
        profile=json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(profile,dict) or not isinstance(profile.get('home'),str):raise ValueError('后端配置损坏；原文件保留')
        return Path(profile['home']).resolve()
    return None


@lru_cache(maxsize=8)
def _identity(signature):
    digest=hashlib.sha256()
    for path,_,_ in signature:
        digest.update(path.encode('utf-8'))
        with Path(path).open('rb') as stream:
            for chunk in iter(lambda:stream.read(1024*1024),b''):digest.update(chunk)
    return digest.hexdigest()[:20]


def cache_dir() -> Path:
    override=os.environ.get('PLC_PROBE_CACHE')
    if override:return Path(override).expanduser().resolve()
    home=selected_backend()
    if home is None:return base_cache_dir()
    files=[home/('strucpp.exe' if os.name=='nt' else 'strucpp'),home/'compiler.cjs',home/'plc-r4.json',home/'node-path.txt',home/'cli-path.txt']
    files.extend(sorted((home/'runtime/include').glob('*.hpp')))
    files.extend(sorted((home/'libs').glob('*.stlib')))
    node_path=home/'node-path.txt'
    if node_path.exists():files.append(Path(node_path.read_text(encoding='utf-8').strip()))
    cxx=os.environ.get('CXX') or shutil.which('g++')
    if cxx and Path(cxx).is_file():files.append(Path(cxx))
    signature=tuple((str(p),p.stat().st_size,p.stat().st_mtime_ns) for p in files if p.is_file())
    key=_identity(signature) if signature else hashlib.sha256(str(home).encode()).hexdigest()[:20]
    directory=base_cache_dir()/'backends'/key
    directory.mkdir(parents=True,exist_ok=True)
    return directory


def toolchain_dir() -> Path:
    selected=selected_backend()
    if selected is not None:return selected
    base=Path(os.environ['PLC_PROBE_CACHE']).expanduser().resolve() if os.environ.get('PLC_PROBE_CACHE') else base_cache_dir()
    return base / f"strucpp-{VERSION}" / "strucpp"


def bootstrap() -> dict:
    """Download a pinned portable dependency; do not install system-wide."""
    if os.name != "nt":
        raise RuntimeError("Automatic bootstrap currently supports Windows x64 only; set STRUC_PP_HOME elsewhere.")
    root = Path(os.environ['PLC_PROBE_CACHE']).expanduser().resolve() if os.environ.get('PLC_PROBE_CACHE') else base_cache_dir()
    root.mkdir(parents=True, exist_ok=True)
    archive = root / f"strucpp-v{VERSION}.zip"
    if not archive.exists():
        temporary = archive.with_suffix(".download")
        with urllib.request.urlopen(ARCHIVE_URL, timeout=90) as response, temporary.open("wb") as output:
            shutil.copyfileobj(response, output)
        temporary.replace(archive)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    if digest != ARCHIVE_SHA256:
        raise RuntimeError(f"Dependency checksum mismatch: {digest}")
    target = root / f"strucpp-{VERSION}"
    with zipfile.ZipFile(archive) as zipped:
        for item in zipped.infolist():
            if not (target / item.filename).resolve().is_relative_to(target.resolve()):
                raise ValueError("Archive path leaves dependency directory")
        zipped.extractall(target)
    return {"status": "ready", "directory": str(target), "sha256": digest, "version": VERSION}


def command_version(command: list[str]) -> str | None:
    try:
        result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10)
        return (result.stdout or result.stderr).splitlines()[0] if result.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired, IndexError):
        return None


def doctor() -> dict:
    compiler = toolchain_dir() / ("strucpp.exe" if os.name == "nt" else "strucpp")
    cxx = os.environ.get("CXX") or shutil.which("g++")
    codesys = []
    if os.name == "nt":
        import winreg
        for hive, branch in [
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
            (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
        ]:
            try:
                with winreg.OpenKey(hive, branch) as key:
                    for index in range(winreg.QueryInfoKey(key)[0]):
                        try:
                            with winreg.OpenKey(key, winreg.EnumKey(key, index)) as app:
                                name = winreg.QueryValueEx(app, "DisplayName")[0]
                                if "codesys" in name.lower():
                                    codesys.append(name)
                        except OSError:
                            pass
            except OSError:
                pass
    compiler_version = command_version([str(compiler), "--version"]) if compiler.exists() else None
    cxx_version = command_version([cxx, "--version"]) if cxx else None
    return {
        "status": "ready" if compiler_version and cxx_version else "missing_dependency",
        "offline_backend": {"compiler": str(compiler), "version": compiler_version, "cxx": cxx, "cxx_version": cxx_version},
        "codesys_detected_installations": sorted(set(codesys)),
        "codesys_compile_executed": False,
        "formal_verifier_executed": False,
        "cache": str(cache_dir()),
    }


def save_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
