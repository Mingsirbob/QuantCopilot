---
name: "financial_data_fetch"
version: "1.0.0"
description: "金融数据抓取与字段规范标准操作规程，涵盖A股标的代码消歧、日期时间对齐及错误码容错"
references:
  - "references/data_dictionary.md"
---

# 金融数据抓取专业 SOP (Standard Operating Procedure)

## 1. 标的代码命名规则
- 上海证券交易所股票：以 `.SH` 结尾，如 `600519.SH`
- 深圳证券交易所股票：以 `.SZ` 结尾，如 `000001.SZ`, `300750.SZ`
- 北京证券交易所股票：以 `.BJ` 结尾，如 `835185.BJ`
- 优先通过 `get_meta_tickers_search` 确认 `asset_type == "a-share"` 的结果项。

## 2. 日期与时间传参规范
- 日期格式通常使用 `YYYY-MM-DD`（如 `2024-01-01`）或 `YYYYMMDD`。
- 如果用户未指定时间范围且查询历史日K，默认查询最近一个自然月的数据。
- 遇非交易日（周末、法定节假日）获取行情时，最新行情取最近一个有效交易日的收盘数据。

## 3. 错误码与容错处理
- `code=0`：请求成功，业务数据位于 `data.item`。
- `code=2001` / `code=2003`：鉴权失败或权限受限，提醒检查 `Financial-API-KEY`。
- `code=4001` 或 HTTP 429：触发限流，提示用户请求过于频繁，建议稍后重试。
- 若单只股票未返回数据，请先核对代码与交易所后缀是否正确。
