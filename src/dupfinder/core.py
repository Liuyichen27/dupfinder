"""重复文件查找：先按大小分桶，再按头部哈希分桶，最后算全文件哈希。

三级筛选的意义：真实磁盘上 90% 的文件在第一步就被排除，只有大小相同的才需要
读内容。要扫 10 万个文件，全量哈希要跑十几分钟，这样通常几秒就完事。
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

HEAD_BYTES = 64 * 1024   # 头部取样大小
CHUNK = 1024 * 1024      # 分块读取

# 默认跳过的目录：这些里面的重复没意义，还会拖慢扫描
SKIP_DIRS = {
    ".git", ".svn", ".hg", "node_modules", "__pycache__", ".venv", "venv",
    "$RECYCLE.BIN", "System Volume Information", ".gradle", ".idea", ".cache",
}


def human_size(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


@dataclass
class FileMeta:
    path: Path
    size: int


@dataclass
class DuplicateGroup:
    """一组内容完全相同的文件。"""

    files: list[FileMeta]

    @property
    def size(self) -> int:
        return self.files[0].size

    @property
    def wasted(self) -> int:
        """删掉多余副本能省多少空间。"""
        return self.size * (len(self.files) - 1)

    @property
    def key(self) -> str:
        """用来排序，体积大的组更值得先看。"""
        return self.files[0].path.name.lower()


def iter_files(roots: Iterable[str], recursive: bool = True,
               min_size: int = 1,
               skip_hidden: bool = False) -> Iterable[FileMeta]:
    """遍历给定路径下的文件，跳过系统/构建目录。"""
    for root in roots:
        p = Path(root).expanduser()
        if p.is_file():
            try:
                st = p.stat()
                if st.st_size >= min_size:
                    yield FileMeta(p, st.st_size)
            except OSError:
                pass
            continue
        if not p.is_dir():
            continue

        walker = os.walk(p) if recursive else [(str(p), [], [f.name for f in p.iterdir() if f.is_file()])]
        for dirpath, dirnames, filenames in walker:
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS
                           and not (skip_hidden and d.startswith("."))]
            for name in filenames:
                if skip_hidden and name.startswith("."):
                    continue
                fp = Path(dirpath) / name
                try:
                    st = fp.stat()
                except OSError:
                    continue  # 权限不够或文件刚被删，跳过就行
                if st.st_size >= min_size:
                    yield FileMeta(fp, st.st_size)


def _hash_head(path: Path, limit: int = HEAD_BYTES) -> str:
    h = hashlib.blake2b(digest_size=16)
    with open(path, "rb") as f:
        h.update(f.read(limit))
    return h.hexdigest()


def _hash_full(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            block = f.read(CHUNK)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def find_duplicates(roots: Iterable[str], *, recursive: bool = True,
                    min_size: int = 1, skip_hidden: bool = False,
                    progress: Callable[[str, int, int], None] | None = None
                    ) -> tuple[list[DuplicateGroup], int, int]:
    """返回 (重复组, 扫描文件数, 总字节数)。progress(阶段, 已完成, 总数)。"""

    # 第一级：按大小分桶
    by_size: dict[int, list[FileMeta]] = {}
    count = 0
    total = 0
    for meta in iter_files(roots, recursive, min_size, skip_hidden):
        by_size.setdefault(meta.size, []).append(meta)
        count += 1
        total += meta.size
        if progress and count % 200 == 0:
            progress("扫描", count, 0)

    # 大小唯一的直接出局，不用读内容
    candidates = [m for group in by_size.values() if len(group) > 1 for m in group]
    if progress:
        progress("筛选", len(candidates), count)

    # 第二级：头部哈希
    by_head: dict[tuple[int, str], list[FileMeta]] = {}
    done = 0
    for m in candidates:
        try:
            head = _hash_head(m.path)
        except OSError:
            continue
        by_head.setdefault((m.size, head), []).append(m)
        done += 1
        if progress:
            progress("取样", done, len(candidates))

    # 第三级：全文件哈希（只剩同大小同头部的，通常很少）
    remaining = [m for group in by_head.values() if len(group) > 1 for m in group]
    by_full: dict[str, list[FileMeta]] = {}
    done = 0
    for m in remaining:
        try:
            digest = _hash_full(m.path)
        except OSError:
            continue
        by_full.setdefault(digest, []).append(m)
        done += 1
        if progress:
            progress("校验", done, len(remaining))

    groups = [DuplicateGroup(sorted(g, key=lambda x: str(x.path)))
              for g in by_full.values() if len(g) > 1]
    groups.sort(key=lambda g: g.wasted, reverse=True)
    return groups, count, total
