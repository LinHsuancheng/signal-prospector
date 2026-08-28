# Public scoring prompt example

请根据文章的相关性、信息密度和可验证性进行评分。

对每篇文章返回：

- `pattern`: 命中的内容类型名称数组；可以使用本文未预先列出的明确类型
- `score`: 0 到 10 的数字
- `reason`: 简短的评分理由

没有命中类型时返回空数组 `[]`。只返回 JSON：

```json
{"items":[{"id":1,"pattern":["example-type"],"score":5,"reason":"short reason"}]}
```

Articles:

{articles}
