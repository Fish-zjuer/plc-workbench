"""Copy user-selected files; bounded text extraction, never execute attachments."""
from __future__ import annotations

import hashlib
from pathlib import Path, PurePosixPath
import re
import uuid
import zipfile
import xml.etree.ElementTree as ET

from .storage import Project

MAX_FILE = 32 * 1024 * 1024
MAX_TEXT = 2_000_000
SUPPORTED = {".txt", ".md", ".st", ".json", ".csv", ".log", ".yaml", ".yml", ".pdf", ".docx", ".zip"}


def safe_name(name: str) -> str:
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .")[:120]
    return value or "attachment"


def _decode(data: bytes) -> str:
    for encoding in ("utf-8-sig", "gb18030"):
        try:
            return data.decode(encoding)
        except UnicodeError:
            continue
    return data.decode("utf-8", errors="replace")


def extract(path: Path) -> tuple[str, str]:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        from pypdf import PdfReader
        reader = PdfReader(path)
        if reader.is_encrypted:
            raise ValueError("加密 PDF 请先解密后导入")
        pieces, size, has_text = [], 0, False
        for index, page in enumerate(reader.pages[:500]):
            content = page.extract_text() or ""
            has_text = has_text or bool(content.strip())
            piece = f"\n[第 {index + 1} 页]\n" + content
            pieces.append(piece)
            size += len(piece)
            if size >= MAX_TEXT:
                break
        text = "".join(pieces)
        if not has_text:
            return text, "no_text_ocr_needed"
        return text[:MAX_TEXT], "truncated" if size >= MAX_TEXT or len(reader.pages) > 500 else "ready"
    if suffix == ".docx":
        with zipfile.ZipFile(path) as archive:
            info = archive.getinfo("word/document.xml")
            if info.file_size > MAX_FILE:
                raise ValueError("DOCX 正文解压后过大")
            document = ET.fromstring(archive.read(info))
        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        text = "\n".join("".join(p.itertext()) for p in document.findall(".//w:p", ns))
        return text[:MAX_TEXT], "truncated" if len(text) > MAX_TEXT else "ready"
    text = _decode(path.read_bytes())
    return text[:MAX_TEXT], "truncated" if len(text) > MAX_TEXT else "ready"


def attach(project: Project, source: str | Path) -> list[dict]:
    source = Path(str(source).strip().strip('"')).expanduser().resolve()
    if not source.is_file() or source.suffix.lower() not in SUPPORTED:
        raise ValueError("请选择 TXT、MD、ST、JSON、CSV、PDF、DOCX 或 ZIP 文件")
    if source.stat().st_size > MAX_FILE:
        raise ValueError("单个文件不能超过 32 MiB")
    uploads = project.workspace / "uploads"
    uploads.mkdir(exist_ok=True)
    ident = uuid.uuid4().hex[:12]
    destination = uploads / (ident + "_" + safe_name(source.name))
    # Read once: the hash and copied bytes always describe the same snapshot.
    data = source.read_bytes()
    if len(data) > MAX_FILE:
        raise ValueError("文件在导入过程中超过大小限制")
    entries = []
    if source.suffix.lower() == ".zip":
        # Validate entire directory before writing; no traversal, symlinks or zip bombs.
        import io
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            infos = archive.infolist()
            if len(infos) > 1000 or sum(i.file_size for i in infos) > MAX_FILE:
                raise ValueError("ZIP 最多 1000 项，解压总量最多 32 MiB")
            for info in infos:
                name = PurePosixPath(info.filename.replace("\\", "/"))
                if name.is_absolute() or ".." in name.parts or ":" in str(name) or (info.external_attr >> 16) & 0o170000 == 0o120000:
                    raise ValueError("ZIP 包含不安全路径或符号链接")
                if info.flag_bits & 1:
                    raise ValueError("不支持加密 ZIP")
            # Every member receives a unique ID; flattened filenames cannot collide.
            for info in infos:
                if not info.is_dir() and Path(info.filename).suffix.lower() in SUPPORTED - {".zip"}:
                    entries.append((info.filename, archive.read(info)))
    destination.write_bytes(data)
    records = []
    def register(path: Path, original: str, content: bytes, archive_container=False):
        record = {"id": uuid.uuid4().hex[:12], "name": original, "path": path.relative_to(project.workspace).as_posix(),
                  "size": len(content), "sha256": hashlib.sha256(content).hexdigest(), "status": "archive" if archive_container else "pending"}
        if not archive_container:
            try:
                text, status = extract(path)
                text_path = uploads / ".text" / (record["id"] + ".txt")
                text_path.parent.mkdir(exist_ok=True)
                text_path.write_text(text, encoding="utf-8")
                record.update(status=status, text_path=text_path.relative_to(project.workspace).as_posix(), text_chars=len(text))
            except Exception as exc:
                record.update(status="extraction_error", message=f"{type(exc).__name__}: {exc}"[:300])
        records.append(record)
    register(destination, source.name, data, source.suffix.lower() == ".zip")
    for name, content in entries:
        child = uploads / (uuid.uuid4().hex[:12] + "_" + safe_name(PurePosixPath(name.replace("\\", "/")).name))
        child.write_bytes(content)
        register(child, name, content)
    project.data["attachments"].extend(records)
    project.save()
    return records
