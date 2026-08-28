# Signal Prospector

## The Gold Pan

你是否为被淹没在互联网大份里而不知所措？观点、文章、争论、新闻和推荐不断涌来，像一整条河流把泥沙冲到你面前。

淘金客不会把整条河带回家。他只需要一只盘子。

Signal Prospector 是一只信息淘金盘。把大份放进盘中。让泥沙流走。只看留下来的金粒。

长期主义者不留下所有互联网大份，恰恰相反，他只看什么值得被时间留下。值得留下的，可能是一条改变判断的洞见，一种可以反复验证的观点，一段能够在未来产生复利的知识，总之，我们不能被淹没在答辩中。

## How It Works

### Bring the Stream to the Pan

从日常浏览的信息流中抓取推荐卡片。

### Wash Away the Silt

让 LLM 从大份中打分并筛选，留下可以真正阅读的正文。

### Keep the Gold

留下来的内容进入 Inbox，成为个人阅读、研究和长期积累的一部分。

## Getting Started

需要 Python 3.11 或更高版本，以及本机 Chrome/Chromium。

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e .
cp config.example.toml config.toml
```

在本地配置模型服务和浏览器路径，并通过环境变量提供 API key。评分偏好请放在本地 `prompts/score.md`。

启动浏览器连接：

```bash
prospect browser
```

完成登录后，运行一次淘洗：

```bash
prospect wash zhihu
```

整理留下的内容：

```bash
prospect organize
```

## Local by Default

浏览器登录态、个人数据、Markdown inbox、评分 prompt 和运行状态都保留在本地。