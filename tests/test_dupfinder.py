"""dupfinder 测试：全部在临时目录里造数据，不碰真实文件。"""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dupfinder import cli, core  # noqa: E402


def write(p: Path, data: bytes) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    return p


class TestFindDuplicates(unittest.TestCase):
    def test_finds_exact_copies(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            payload = b"A" * 5000
            write(d / "a.bin", payload)
            write(d / "sub" / "b.bin", payload)
            write(d / "c.bin", b"B" * 5000)  # 同大小不同内容，不能算重复

            groups, count, _ = core.find_duplicates([td])
            self.assertEqual(count, 3)
            self.assertEqual(len(groups), 1)
            self.assertEqual(len(groups[0].files), 2)
            self.assertEqual(groups[0].wasted, 5000)

    def test_same_size_different_content_not_grouped(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            write(d / "a.bin", b"x" * 10000)
            write(d / "b.bin", b"y" * 10000)
            groups, _, _ = core.find_duplicates([td])
            self.assertEqual(groups, [])

    def test_same_head_different_tail_not_grouped(self):
        # 头部相同、尾部不同：必须靠全量哈希才能区分
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            head = b"H" * core.HEAD_BYTES
            write(d / "a.bin", head + b"tail-1")
            write(d / "b.bin", head + b"tail-2")
            groups, _, _ = core.find_duplicates([td])
            self.assertEqual(groups, [])

    def test_three_copies_wasted_is_two(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            for i in range(3):
                write(d / f"copy{i}.bin", b"same" * 100)
            groups, _, _ = core.find_duplicates([td])
            self.assertEqual(len(groups), 1)
            self.assertEqual(len(groups[0].files), 3)
            self.assertEqual(groups[0].wasted, 800)  # 400 字节 × 两条多余

    def test_min_size_filters_small_files(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            write(d / "small1.txt", b"hi")
            write(d / "small2.txt", b"hi")
            write(d / "big1.bin", b"z" * 2048)
            write(d / "big2.bin", b"z" * 2048)

            groups, _, _ = core.find_duplicates([td], min_size=1024)
            self.assertEqual(len(groups), 1)
            self.assertEqual(groups[0].size, 2048)

    def test_skips_git_and_node_modules(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            write(d / ".git" / "obj.bin", b"q" * 3000)
            write(d / "node_modules" / "pkg.bin", b"q" * 3000)
            groups, count, _ = core.find_duplicates([td])
            self.assertEqual(count, 0)
            self.assertEqual(groups, [])

    def test_single_file_path(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            f = write(d / "only.bin", b"1234")
            groups, count, _ = core.find_duplicates([str(f)])
            self.assertEqual(count, 1)
            self.assertEqual(groups, [])

    def test_groups_sorted_by_wasted(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            write(d / "small-a", b"s" * 100)
            write(d / "small-b", b"s" * 100)
            write(d / "big-a", b"b" * 9000)
            write(d / "big-b", b"b" * 9000)
            groups, _, _ = core.find_duplicates([td])
            self.assertEqual(len(groups), 2)
            self.assertEqual(groups[0].size, 9000)  # 大的排前面

    def test_empty_files_are_ignored_by_default(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            write(d / "e1.txt", b"")
            write(d / "e2.txt", b"")
            groups, _, _ = core.find_duplicates([td], min_size=1)
            self.assertEqual(groups, [])


class TestNoDeletion(unittest.TestCase):
    def test_scan_never_removes_files(self):
        """这个工具最重要的保证：跑完之后文件一个都不能少。"""
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            for i in range(4):
                write(d / f"f{i}.bin", b"dup" * 500)
            before = sorted(p.name for p in d.iterdir())

            core.find_duplicates([td])

            after = sorted(p.name for p in d.iterdir())
            self.assertEqual(before, after)


class TestCli(unittest.TestCase):
    def test_json_report(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            write(d / "a.bin", b"z" * 4096)
            write(d / "b.bin", b"z" * 4096)
            out = d / "report.json"
            self.assertEqual(cli.main([str(d), "-j", str(out), "-q"]), 0)
            import json
            data = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(data["groups"][0]["size"], 4096)
            self.assertEqual(data["total_wasted"], 4096)
            self.assertEqual(len(data["groups"][0]["files"]), 2)

    def test_human_size(self):
        self.assertEqual(core.human_size(512), "512 B")
        self.assertEqual(core.human_size(2048), "2.0 KB")


if __name__ == "__main__":
    unittest.main()
