"""文件型记忆库：markdown 文件组织的持久化记忆。

抽象自知识站的记忆目录形态：一个根目录，记忆按「类别前缀」平铺成
markdown 文件（反馈、项目、参考资料、用户画像各占一类），另有一份
索引文件列出全部记忆的标题与位置。文件是人类可读可改的，
索引由库重建，不靠人维护。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class MemoryEntry:
    category: str
    slug: str
    path: Path
    title: str

    @property
    def filename(self) -> str:
        return f"{self.category}_{self.slug}.md"


def _title_of(text: str, fallback: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip() or fallback
        if stripped:
            return stripped[:80]
    return fallback


class FileMemoryVault:
    """平铺 markdown 记忆库：写读列三项基本操作，索引按需重建。"""

    def __init__(self, root: Path, index_name: str = "MEMORY.md") -> None:
        self.root = Path(root)
        self.index_name = index_name

    def write(self, category: str, slug: str, content: str) -> Path:
        if not category or not slug:
            raise ValueError("category and slug must be non-empty")
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / f"{category}_{slug}.md"
        path.write_text(content, encoding="utf-8")
        return path

    def read(self, category: str, slug: str) -> str | None:
        path = self.root / f"{category}_{slug}.md"
        if not path.is_file():
            return None
        return path.read_text(encoding="utf-8")

    def entries(self, category: str | None = None) -> list[MemoryEntry]:
        if not self.root.is_dir():
            return []
        result: list[MemoryEntry] = []
        for path in sorted(self.root.glob("*.md")):
            if path.name == self.index_name:
                continue
            name, _, _ = path.name.rpartition(".md")
            category_part, sep, slug_part = name.partition("_")
            if not sep or not slug_part:
                continue
            if category is not None and category_part != category:
                continue
            text = path.read_text(encoding="utf-8")
            result.append(
                MemoryEntry(
                    category=category_part,
                    slug=slug_part,
                    path=path,
                    title=_title_of(text, fallback=name),
                )
            )
        return result

    def rebuild_index(self) -> Path:
        """重建索引文件：每条记忆一行，标题链接到文件。返回索引路径。"""
        lines = ["# Memory Index", ""]
        entries = self.entries()
        if entries:
            lines.extend(f"- [{entry.title}]({entry.filename})" for entry in entries)
        else:
            lines.append("(empty)")
        index_path = self.root / self.index_name
        index_path.parent.mkdir(parents=True, exist_ok=True)
        index_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return index_path
