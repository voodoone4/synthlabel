# synthlabel

**给合成数据标注它的生成方式与可信度。**

`synthlabel` —— 为每条合成数据记录生成方式、筛选依据与不确定度，随数据一起流转。

- 零依赖，Python 3.10+ 标准库即可运行
- 单文件，`synthlabel.py` 拷走就能用
- 不联网、不写文件

<!-- ipos:install -->
## 安装

零依赖，Python 3.10+ 即可：

```bash
pip install voodoone4-synthlabel
```

装完直接用命令名调用：

```bash
synthlabel --help
```

也可以不用安装，直接把 `synthlabel.py` 拷走用——它只依赖标准库。

## 为什么需要它

合成数据工具多只产数据；synthlabel 让每条数据自带来源与不确定度，能随数据集一起流转。

它遵守下面几条自己定的规矩：

1. **合成数据也得有出生证明**。标签跟着数据走，将来发现问题时能一路查回去。
2. **筛选依据必须记下来**。筛掉什么，等于决定了留下什么。
3. **不确定度不许伪装成确定**。机器标出来的置信度就是机器标出来的。

## 用法

```bash
python synthlabel.py --data synth.jsonl --label-out labeled.jsonl
python synthlabel.py --data synth.jsonl --audit
```

加 `--json` 可以拿到机器可读的结果，便于接到流水线里。

## 已知局限

- 只追溯生成记录与标签来源，不判断合成数据该不该用。
- 来源链靠调用方如实登记，登记错了它也看不出来。
- 不做质量过滤。

## 跑测试

```bash
python test_synthlabel.py
```

测试用独立的断言与临时数据，不污染工作目录。

## 来源与参考

- Python 标准库文档：<https://docs.python.org/3/>
- GitHub 仓库：<https://github.com/voodoone4/synthlabel>

---

## 关于作者

voodoone4 做合成数据的来源标注相关的问题。这个工具先替你回答一个具体问题，再谈别的。

- 个人主页：<https://voodoone4.github.io>
- 仓库：<https://github.com/voodoone4/synthlabel>

## 许可

MIT，见 [LICENSE](LICENSE)。
