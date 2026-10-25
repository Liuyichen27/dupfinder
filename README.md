# DupFinder · 重复文件查找

[![Python](https://img.shields.io/badge/python-3.8%2B-3776AB)](https://www.python.org)
[![License](https://img.shields.io/badge/license-MIT-12B76A)](LICENSE)
[![Dependencies](https://img.shields.io/badge/dependencies-0-12B76A)](#)

把重复的文件揪出来，告诉你删掉能省多少空间。

**它不会删任何文件。** 一句都不删，只出报告。

```bash
dupfinder D:/照片 D:/备份 --min-size 1M
```

## 为什么不直接用现成的

清理软件普遍有个问题：**你不敢点那个按钮**。它给你一堆看不懂的列表，然后问「是否删除」，你怕删错，最后关掉不用。

DupFinder 的定位是「先看清楚」：

- 只负责找，删不删你决定，工具连 `--delete` 参数都没有
- 按「能省多少空间」排序，值得处理的排前面
- 保留完整路径，可以直接复制去别处处理
- 支持导出 JSON，想写脚本再加工自己来

## 安装

```bash
pip install git+https://github.com/Liuyichen27/dupfinder.git
```

零依赖，纯标准库。

## 用法

```bash
dupfinder ./下载                      # 扫一个目录
dupfinder D:/照片 D:/备份 -m 1M       # 扫多个目录，只看大于 1 MB 的
dupfinder ./项目 --json report.json   # 导出 JSON
dupfinder . --no-recursive            # 不递归子目录
```

输出长这样：

```
重复组 1（3 个文件，每个 12.4 MB）
  12.4 MB  D:/照片/2024/IMG_0231.jpg
  12.4 MB  D:/备份/2024/IMG_0231.jpg
  12.4 MB  D:/照片/旧/IMG_0231 - 副本.jpg
  → 留 1 个可省 24.8 MB

扫描 18432 个文件（62.1 GB），用时 8.3s
发现 7 组重复，涉及 19 个文件，最多可省 412.6 MB
提示：本工具不会删任何文件，请自行确认后处理。
```

## 参数

| 参数 | 说明 |
| --- | --- |
| `-m, --min-size` | 只处理大于这个体积的文件，支持 `1M` / `500K` |
| `--no-recursive` | 只看当前层 |
| `--skip-hidden` | 跳过 `.` 开头的文件 |
| `-j, --json FILE` | 导出 JSON，`-` 输出到标准输出 |
| `-q, --quiet` | 只给汇总，不列具体文件 |

## 怎么做到几秒钟扫完 6 万文件

三级筛选，逐级缩小范围：

1. **按大小分桶** —— 大小不同的文件内容必然不同，直接排除。真实磁盘上这一步就筛掉 90% 以上
2. **头部 64 KB 取样哈希**（BLAKE2b）—— 大小相同的再比开头，通常又筛掉一大半
3. **全文件 SHA-256** —— 只剩「大小相同 + 开头相同」的极少数，这时候才算全文

如果一上来就对所有文件算 SHA-256，6 万个文件要跑十几分钟；三级筛选通常 5~10 秒。

## 自动跳过的目录

`.git`、`node_modules`、`__pycache__`、`.venv`、`$RECYCLE.BIN`、`System Volume Information`、`.gradle`、`.idea`、`.cache`

这些目录里的重复没有清理价值，扫进去只会拖慢速度、报一堆噪音。

**没有权限的目录**会静默跳过（比如 `C:\Windows` 里的系统目录），不会中断整个扫描。

## 安全边界

- 只读：整个工具里没有 `unlink` / `rmtree` / `os.remove`
- 测试里有一条 `test_scan_never_removes_files`，跑完断言目录内容一个不少
- 传入单个文件也安全，只是不会有结果（找不到副本）

## 作为库调用

```python
from dupfinder import core

groups, count, total_bytes = core.find_duplicates(["D:/照片"], min_size=1024)
for g in groups:
    print(f"省 {core.human_size(g.wasted)}：{len(g.files)} 个副本")
    for f in g.files:
        print("  ", f.path)
```

## 测试

```bash
python -m unittest discover -s tests -v
```

12 个用例，覆盖：同大小不同内容、同头不同尾、三副本计算、大小过滤、跳过构建目录、单文件路径、排序、空文件，以及「扫完不删文件」这条硬约束。

## 许可

MIT License，详见 [LICENSE](LICENSE)。

---

<sub>English: DupFinder finds byte-identical files and tells you how much space you could reclaim. It never deletes anything — there is no `--delete` flag by design. Scans in three stages (size bucketing → 64 KB head hash → full SHA-256), which makes a 60k-file scan finish in seconds instead of minutes. Exports JSON for further processing.</sub>
