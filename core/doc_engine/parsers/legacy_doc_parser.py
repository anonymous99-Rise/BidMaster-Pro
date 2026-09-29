from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from core.doc_engine.parsers.base import ParsedDocument

# OLE2 复合文档魔数 (Word 97-2003 .doc)
_OLE2_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


class LegacyDocParser:
    """老版 Word .doc / .wps 解析器

    python-docx 只能读 .docx(zip 包),老 .doc 是 OLE2 复合文档,
    直接解析会报 "Package not found"。
    先用 LibreOffice 无头模式转换为 .docx(保留表格结构,招标文件评标
    表格关键),再复用 DocxParser。
    """

    def parse(self, file_path: str) -> ParsedDocument:
        from core.doc_engine.parsers.docx_parser import DocxParser

        src = Path(file_path)
        if not src.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")

        with open(src, "rb") as f:
            magic = f.read(8)

        # 扩展名是 .doc 但实际已是 docx(zip) → 直接走 DocxParser
        if magic != _OLE2_MAGIC:
            return DocxParser().parse(file_path)

        soffice = shutil.which("soffice") or shutil.which("libreoffice")
        if not soffice:
            raise RuntimeError(
                "服务器未安装 LibreOffice,无法解析老版 .doc 文件;"
                "请将文件另存为 .docx 后重新上传"
            )

        with tempfile.TemporaryDirectory(prefix="bmp_doc_") as tmpdir:
            # LibreOffice 并发调用共用 profile 会锁死,必须指定独立 profile
            subprocess.run(
                [
                    soffice, "--headless", "--norestore",
                    f"-env:UserInstallation=file://{tmpdir}/lo_profile",
                    "--convert-to", "docx",
                    "--outdir", tmpdir, str(src),
                ],
                check=True,
                timeout=180,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            converted = Path(tmpdir) / (src.stem + ".docx")
            if not converted.exists():
                raise RuntimeError("LibreOffice 转换失败: 未生成 .docx")

            result = DocxParser().parse(str(converted))
            result.metadata["parser"] = "libreoffice+python-docx"
            result.metadata["source_format"] = src.suffix
            return result
