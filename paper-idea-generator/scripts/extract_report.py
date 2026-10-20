#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""提取可行性研究报告全文，保留标题层级、表格和图片位置。

用法（用工作区自带的 Python 运行，不要安装依赖）::

    python extract_report.py 报告.docx
    python extract_report.py 报告.docx -o report.md --outline outline.json

支持 .docx / .txt / .md；PDF 仅在环境已安装 pypdf 时可用（扫描版 PDF 无文本层，
脚本会明确报错，请改用 docx 或提供可复制文本）。

输出为 Markdown：Word 标题按大纲级别转成 ``#``，表格转成管道表，图片标成
``[图片]``，表格内多段文字用 ``<br>`` 连接。末尾打印字符数、标题/表格/图片
统计，以及三级以内目录，便于快速定位章节。

已知限制：Word 自动编号（列表编号）不会展开成文字；复杂合并单元格按行去重，
列对齐可能不完美，但不影响阅读。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HEADING_RE = re.compile(r"^(?:Heading|标题)\s*([1-9]\d*)$", re.IGNORECASE)
TOP_CN_RE = re.compile(r"^(?:第[一二三四五六七八九十百]+[章节部分]|[一二三四五六七八九十百]+、)")
SEC_CN_RE = re.compile(r"^[（(][一二三四五六七八九十]+[）)]")
APPENDIX_RE = re.compile(r"^附\s*件\s*\d+")


def die(message: str) -> "NoReturn":
    print(f"错误：{message}", file=sys.stderr)
    raise SystemExit(1)


def heading_level(paragraph) -> int:
    """返回标题级别（1-6），正文返回 0。

    Word 里常见"所有标题都用 Heading 2"的扁平写法。若标题文字本身带
    "一、" / "第一章" / "（一）" 这类编号，按编号纠正级别，保证目录有层次。
    """
    style = getattr(paragraph.style, "name", "") or ""
    match = HEADING_RE.match(style.strip())
    level = min(int(match.group(1)), 6) if match else 0

    p_pr = paragraph._p.pPr
    if not level and p_pr is not None:
        outline = p_pr.find("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}outlineLvl")
        if outline is not None:
            value = outline.get("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}val")
            if value and value.isdigit():
                level = min(int(value) + 1, 6)

    if not level:
        return 0

    text = paragraph.text.strip()
    if TOP_CN_RE.match(text) or APPENDIX_RE.match(text):
        return 1
    if SEC_CN_RE.match(text):
        return max(level, 2) if level < 2 else level
    return level


def iter_blocks(container, parent):
    """按文档顺序产出段落与表格，并下钻内容控件（w:sdt）。"""
    w_p = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p"
    w_tbl = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}tbl"
    w_sdt = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}sdt"
    w_sdt_content = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}sdtContent"

    for child in container.iterchildren():
        if child.tag == w_p:
            from docx.text.paragraph import Paragraph

            yield Paragraph(child, parent)
        elif child.tag == w_tbl:
            from docx.table import Table

            yield Table(child, parent)
        elif child.tag == w_sdt:
            content = child.find(w_sdt_content)
            if content is not None:
                yield from iter_blocks(content, parent)


def cell_text(cell) -> str:
    parts = [p.text.strip() for p in cell.paragraphs if p.text and p.text.strip()]
    if not parts:
        return ""
    return "<br>".join(parts).replace("|", r"\|").replace("\n", " ")


def table_to_markdown(table) -> str:
    w_tc = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}tc"
    rows = []
    for row in table.rows:
        cells, seen = [], set()
        for cell in row.cells:
            if id(cell._tc) in seen:
                continue
            seen.add(id(cell._tc))
            cells.append(cell_text(cell))
        if any(cells):
            rows.append(cells)

    if not rows:
        return ""

    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]
    lines = ["| " + " | ".join(rows[0]) + " |", "|" + "|".join(["---"] * width) + "|"]
    lines.extend("| " + " | ".join(r) + " |" for r in rows[1:])
    return "\n".join(lines)


def extract_docx(path: Path) -> tuple[str, dict]:
    try:
        from docx import Document
    except ImportError:
        die("缺少 python-docx，请用 load_workspace_dependencies 返回的 Python 运行本脚本")

    document = Document(str(path))
    lines: list[str] = []
    outline: list[dict] = []
    stats = {"paragraphs": 0, "headings": 0, "tables": 0, "images": 0}

    for block in iter_blocks(document.element.body, document):
        if block.__class__.__name__ == "Table":
            stats["tables"] += 1
            markdown = table_to_markdown(block)
            if markdown:
                lines.extend(["", markdown, ""])
            continue

        stats["paragraphs"] += 1
        text = block.text.strip()
        has_image = "graphicData" in block._p.xml
        if has_image:
            stats["images"] += 1

        if not text:
            if has_image:
                lines.append("[图片]")
            continue

        level = heading_level(block)
        if level:
            stats["headings"] += 1
            outline.append({"level": level, "title": text, "line": len(lines) + 1})
            lines.extend(["", "#" * level + " " + text, ""])
        else:
            lines.append(("[图片] " + text) if has_image else text)

    # 压缩连续空行
    cleaned: list[str] = []
    for line in lines:
        if not line.strip():
            if cleaned and cleaned[-1] == "":
                continue
            cleaned.append("")
        else:
            cleaned.append(line.rstrip())
    text = "\n".join(cleaned).strip() + "\n"
    return text, {"outline": outline, **stats}


def decode_text(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "gb18030", "utf-16"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "replace")


def extract_plain(path: Path) -> tuple[str, dict]:
    text = decode_text(path.read_bytes())
    outline = []
    for number, line in enumerate(text.splitlines(), start=1):
        match = re.match(r"^(#{1,6})\s+(.+)$", line.strip())
        if match:
            title = re.sub(r"^\[(?:Heading|标题)\s*\d+\]\s*", "", match.group(2).strip())
            outline.append({"level": len(match.group(1)), "title": title, "line": number})
    stats = {
        "paragraphs": len([l for l in text.splitlines() if l.strip()]),
        "headings": len(outline),
        "tables": text.count("\n|"),
        "images": text.count("[图片]"),
    }
    return text, {"outline": outline, **stats}


def extract_pdf(path: Path) -> tuple[str, dict]:
    try:
        from pypdf import PdfReader
    except ImportError:
        die("未安装 pypdf，无法直接读取 PDF。请把报告另存为 docx，或复制正文为 txt 后重试")

    reader = PdfReader(str(path))
    pages = [(page.extract_text() or "") for page in reader.pages]
    text = "\n\n".join(page for page in pages if page.strip())
    if not text.strip():
        die("PDF 没有可提取的文本层（可能是扫描件或纯图片），请提供 docx 或可复制文本")
    outline = []
    for number, line in enumerate(text.splitlines(), start=1):
        match = re.match(r"^(#{1,6})\s+(.+)$", line.strip())
        if match:
            title = re.sub(r"^\[(?:Heading|标题)\s*\d+\]\s*", "", match.group(2).strip())
            outline.append({"level": len(match.group(1)), "title": title, "line": number})
    return text, {"outline": outline, "paragraphs": len(text.splitlines()), "headings": len(outline), "tables": 0, "images": 0}


def main() -> None:
    parser = argparse.ArgumentParser(description="提取可行性研究报告全文（标题层级 + 表格 + 图片位置）")
    parser.add_argument("input", help="报告文件路径（.docx / .txt / .md / .pdf）")
    parser.add_argument("-o", "--output", help="输出 Markdown 路径，默认 <文件名>.extracted.md")
    parser.add_argument("--outline", help="可选：把目录写入指定 JSON 文件")
    args = parser.parse_args()

    source = Path(args.input).expanduser().resolve()
    if not source.is_file():
        die(f"找不到文件：{source}")

    suffix = source.suffix.lower()
    if suffix == ".docx":
        text, info = extract_docx(source)
    elif suffix in {".txt", ".md", ".markdown"}:
        text, info = extract_plain(source)
    elif suffix == ".pdf":
        text, info = extract_pdf(source)
    else:
        die(f"不支持的文件类型：{suffix}；请提供 docx、txt、md 或带文本层的 pdf")

    output = Path(args.output).expanduser().resolve() if args.output else source.with_suffix(".extracted.md")
    output.write_text(text, encoding="utf-8")

    if args.outline:
        Path(args.outline).expanduser().resolve().write_text(
            json.dumps(info["outline"], ensure_ascii=False, indent=2), encoding="utf-8"
        )

    print(f"已写入：{output}")
    print(
        f"字符 {len(text)}；段落 {info['paragraphs']}；标题 {info['headings']}；"
        f"表格 {info['tables']}；图片 {info['images']}"
    )
    if info["outline"]:
        print("目录（三级以内）：")
        for item in info["outline"]:
            if item["level"] <= 3:
                print(f"  {'  ' * (item['level'] - 1)}- {item['title']}")
    else:
        print("未识别到标题样式；正文已完整提取，请按编号或关键词定位章节。")


if __name__ == "__main__":
    main()
