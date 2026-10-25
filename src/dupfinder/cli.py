"""dupfinder 命令行入口。

刻意不提供删除功能：删文件不可逆，报告出来之后你自己决定怎么处理。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from . import __version__, core


def parse_size(text: str) -> int:
    t = text.strip().upper().replace(" ", "")
    units = {"B": 1, "K": 1024, "KB": 1024, "M": 1024 ** 2, "MB": 1024 ** 2,
             "G": 1024 ** 3, "GB": 1024 ** 3}
    for suffix in ("GB", "MB", "KB", "B", "G", "M", "K"):
        if t.endswith(suffix):
            try:
                return int(float(t[: -len(suffix)]) * units[suffix])
            except ValueError:
                break
    try:
        return int(float(t))
    except ValueError:
        raise argparse.ArgumentTypeError(f"看不懂的大小：{text}")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="dupfinder",
        description="找出内容完全相同的文件。只出报告，不删除任何文件。",
        epilog="例子：dupfinder D:/照片 D:/备份 --min-size 1M",
    )
    p.add_argument("paths", nargs="+", help="要扫描的目录或文件")
    p.add_argument("-m", "--min-size", type=parse_size, default=1,
                   help="只看大于这个大小的文件，如 1M（默认全部）")
    p.add_argument("--no-recursive", action="store_true", help="不递归子目录")
    p.add_argument("--skip-hidden", action="store_true", help="跳过点开头的文件")
    p.add_argument("-j", "--json", metavar="FILE", help="把结果写成 JSON（- 表示输出到标准输出）")
    p.add_argument("-q", "--quiet", action="store_true", help="只输出汇总，不列文件")
    p.add_argument("-V", "--version", action="version", version=f"dupfinder {__version__}")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    started = time.time()

    def progress(stage: str, done: int, total: int) -> None:
        if not sys.stderr.isatty():
            return
        if total:
            sys.stderr.write(f"\r  {stage} {done}/{total}")
        else:
            sys.stderr.write(f"\r  {stage} {done} 个文件")
        sys.stderr.flush()

    groups, count, total_bytes = core.find_duplicates(
        args.paths,
        recursive=not args.no_recursive,
        min_size=args.min_size,
        skip_hidden=args.skip_hidden,
        progress=progress,
    )
    if sys.stderr.isatty():
        sys.stderr.write("\r" + " " * 40 + "\r")
    elapsed = time.time() - started

    wasted = sum(g.wasted for g in groups)
    files_in_groups = sum(len(g.files) for g in groups)

    if args.json:
        payload = {
            "scanned_files": count,
            "scanned_bytes": total_bytes,
            "groups": [
                {
                    "size": g.size,
                    "wasted": g.wasted,
                    "files": [str(f.path) for f in g.files],
                }
                for g in groups
            ],
            "total_wasted": wasted,
            "elapsed": round(elapsed, 2),
        }
        text = json.dumps(payload, ensure_ascii=False, indent=2)
        if args.json == "-":
            print(text)
        else:
            Path(args.json).write_text(text + "\n", encoding="utf-8")
            print(f"报告已写入 {args.json}")

    if not args.quiet:
        for i, g in enumerate(groups, 1):
            print(f"\n重复组 {i}（{len(g.files)} 个文件，每个 {core.human_size(g.size)}）")
            for f in g.files:
                print(f"  {core.human_size(f.size):>9}  {f.path}")
            print(f"  → 留 1 个可省 {core.human_size(g.wasted)}")

    print()
    print(f"扫描 {count} 个文件（{core.human_size(total_bytes)}），用时 {elapsed:.1f}s")
    if groups:
        print(f"发现 {len(groups)} 组重复，涉及 {files_in_groups} 个文件，"
              f"最多可省 {core.human_size(wasted)}")
        print("提示：本工具不会删任何文件，请自行确认后处理。")
    else:
        print("没有发现重复文件。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
