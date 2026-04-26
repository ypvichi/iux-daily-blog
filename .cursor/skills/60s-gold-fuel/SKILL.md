---
name: 60s-gold-fuel
description: >-
  通过 60s 公共 API 查询**今日国内参考金价**与**汽柴油零售限价（元/升）**。
  在用户询问**金价、黄金价格、今日金价、油价、汽油、柴油、92#、95#、98# 油价**时**必须**读此 skill 并调用文内端点，**禁止**编造价格。
  输出须合并为文内规定的 JSON 对象。上游：[60s API 文档](https://docs.60s-api.viki.moe/)、仓库 [vikiboss/60s](https://github.com/vikiboss/60s)；实例 `https://60s.viki.moe` 主域名在部分地区可能需换公共实例或自建。
---

# 今日金价与油价（60s API）

## API 与 Base URL

- **Base**：`https://60s.viki.moe`（可替换为 [公共实例列表](https://docs.60s-api.viki.moe/7306811m0) 中可访问的地址）
- 响应：顶层 `code`（**200 为成功**）、`message`（可能含部署迁移等提示，可略读）、**业务在 `data` 中**。

### 1. 黄金价格

- **方法**：`GET /v2/gold-price`
- **可选 query**：`encoding`（`json` / `text` / `markdown`；默认 JSON）
- **数据说明**（见 [黄金价格 OpenAPI 文档](https://docs.60s-api.viki.moe/378562614e0)）：`data.date` 为数据日期；`data.metals` 为各品种，其中 **`name` 为 `今日金价`** 的条目为当日国内参考价（`today_price` + `unit`）。

### 2. 汽柴油价格（「汽油价格」/油价）

- **方法**：`GET /v2/fuel-price`
- **query**：`region`（**可选**）— 使用**中文**省/直辖市/自治区等名称，如 `北京`、`上海`、`浙江`、`广东`。**不传时默认**为接口返回的默认地区（与公开服务配置一致，历史上多为北上等；**若用户点省/市名，必须带 `region`**）。

`data` 中常用字段：

- `region`：本次油价所属地区
- `items`：数组，元素含 `name`（如 `92#汽油`、`95#汽油`、`98#汽油`、`0#柴油`）、`price`（元/升，数字）、`price_desc`

## 必守输出格式

用户需要**可解析 JSON** 时，须输出**一个**对象，结构如下（键名固定；`油价` 内键与接口 `items[].name` 一致，通常含 `92#汽油`、`95#汽油`、`98#汽油`、`0#柴油` 等；以实际返回为准）：

```json
{
  "金价": "今日金价条目的展示字符串，如 1037 元/克",
  "油价": {
    "92#汽油": 8.46,
    "95#汽油": 9.01,
    "98#汽油": 10.51,
    "0#柴油": 8.2
  }
}
```

### 填充规则

1. **金价**（字符串）：在 `data.metals` 中取 **`name === "今日金价"`** 的项；**金价** = `"{today_price} {unit}"`（去多余空格）。若无该条，再退而取 `name === "黄金价格"` 的项；仍无则说明接口未提供「今日金价」主档并据实转述 `message` / 原始字段。
2. **油价**（对象）：`GET` 油价接口后，对 `data.items` 中每一项：`油价[item.name] = item.price`（**数字**类型，与接口一致）。**不得**为未在 `items` 中出现的品名编造键。

若用户**只要油价且指定了地区**：

- 请求：`GET /v2/fuel-price?region=浙江`（把 `浙江` 换成用户说的省/市/区在接口中可用的名称；不确定时先按**省级**重试。）

## 调用示例

```bash
curl "https://60s.viki.moe/v2/gold-price"
curl "https://60s.viki.moe/v2/fuel-price"
curl "https://60s.viki.moe/v2/fuel-price?region=上海"
```

```powershell
Invoke-RestMethod "https://60s.viki.moe/v2/gold-price"
Invoke-RestMethod "https://60s.viki.moe/v2/fuel-price?region=北京"
```

## 仓库脚本（可选）

已提供合并输出为本格式 JSON 的脚本：

```bash
node .cursor/skills/60s-gold-fuel/scripts/fetch.mjs
node .cursor/skills/60s-gold-fuel/scripts/fetch.mjs --region 浙江
```

## 助手行为要求

1. 回答金价/油价前**应实际请求上述端点**（或运行 `fetch.mjs`），**禁止**臆造任何数值。
2. `code !== 200` 或 `data` 为空时，说明原因并可建议用户更换公共实例、稍后重试或查本地加油站公示。
3. 金价来源说明见 [黄金价格](https://docs.60s-api.viki.moe/378562614e0) 页面描述；油价数据与 `data.link` 所示来源一致，**仅供参考，以加油站当日标价为准**。
