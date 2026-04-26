---
name: weather-query
description: >-
  通过 60s 公共天气 API 查询中国地区实时天气与预报；`query` 须为中文地名（如「杭州」「西湖区」）。
  在用户询问杭州/浙江天气、天气预报、气温、空气质量、是否下雨等时**必须**读本 skill 并按其中端点调用。
  上游包：vikiboss/60s-skills@weather-query（网络可用时可执行 npx skills add 同步）。
---

# 中国地区天气查询（含杭州）

## 何时使用

- 用户问某地**实时天气**、**未来几天预报**、**小时级趋势**、**空气质量**、生活指数、气象预警等。
- 明确提到 **杭州**、**浙江杭州**，或任意国内城市/区县的中文名。

## API 说明

- **Base**：`https://60s.viki.moe`
- **参数**：`query`（必填），使用**中文**，例如 `杭州`、`北京`、`浦东新区`。
- **响应**：JSON 顶层含 `code`（200 为成功）、`message`（可能含服务迁移提示，可忽略或简要告知用户）、**业务数据在 `data` 内**（勿按旧版文档假设扁平字段）。

### 1. 实时天气

`GET /v2/weather/realtime?query=<中文地名>`

`data` 中常用字段：

- `location`：`name`、`province`、`city`、`county`
- `weather`：`condition`（天气现象）、`temperature`（℃）、`humidity`（%）、`wind_direction`、`wind_power`、`updated`
- `air_quality`：`aqi`、`quality`（如 良）、`pm25` 等
- `sunrise` / `life_indices` / `alerts`：日出日落、生活指数、预警列表

### 2. 预报（逐日 + 逐小时）

`GET /v2/weather/forecast?query=<中文地名>`

`data` 中常用字段：

- `location`：同上
- `hourly_forecast`：数组，元素含 `datetime`、`temperature`、`condition`、`wind_direction`、`wind_power` 等
- `daily_forecast`：数组，元素含 `date`、`day_condition`、`night_condition`、`max_temperature`、`min_temperature`、`air_quality` 等

## 调用示例

**杭州实时天气**（请将 `curl` 换成本机可用的 HTTP 客户端；Windows PowerShell 可用 `Invoke-RestMethod`）：

```bash
curl "https://60s.viki.moe/v2/weather/realtime?query=杭州"
```

```powershell
Invoke-RestMethod -Uri "https://60s.viki.moe/v2/weather/realtime?query=杭州" -Method Get
```

**杭州预报**：

```bash
curl "https://60s.viki.moe/v2/weather/forecast?query=杭州"
```

## 助手行为要求

1. 需要天气数据时**实际请求上述 URL**（或等价工具），用返回的 `data` 回答，避免编造气温与天气现象。
2. 若 `code` 非 200 或 `data` 缺失，说明接口异常或地名无法识别；可建议用户改用上级市名（如区名失败时改用「杭州」）。
3. 公开服务可能变更；`message` 中若提及 Deno Deploy 迁移，仅需知悉长期可用性风险。详细文档见 [60s API 文档](https://docs.60s-api.viki.moe/)、仓库 [github.com/vikiboss/60s](https://github.com/vikiboss/60s)。

## 与官方 Skill 包的关系

本目录为**本仓库内置副本**，便于在无法访问 GitHub 时使用。官方安装命令（网络畅通时）：

```bash
npx skills add https://github.com/vikiboss/60s-skills --skill weather-query --agent cursor -y
```

索引页：[weather-query on skills.sh](https://skills.sh/vikiboss/60s-skills/weather-query)
