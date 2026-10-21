# 第一期国产模型接入

核对日期：2026-10-21。以用户选择厂商为入口，前端只提交 `provider + api_key + model`，不接受地址或协议覆盖。不接入 OpenAI/Anthropic 海外服务；这两个名称仅指 API 数据格式。仅支持下列厂商的国内开放平台标准按量 API Key，不支持 Coding Plan 专用 Key、AK/SK 或第三方网关。

## 厂商、协议与模型

| 厂商 | 后端协议 | 模型发现方式 | 首期模型范围 |
| --- | --- | --- | --- |
| DeepSeek | OpenAI Chat Completions | 实时 API 列表 | 由 GET /models 实时返回的文本模型 |
| MiniMax | Anthropic Messages | 官方预置目录 | `MiniMax-M3`、`MiniMax-M3.1-Flash` |
| Kimi（月之暗面） | OpenAI Chat Completions | 实时 API 列表 | 由 GET /models 实时返回的文本模型 |
| 智谱 GLM | OpenAI Chat Completions | 官方预置目录 | `glm-5.3`、`glm-5.3-flash`、`glm-5.3-flashx`、`glm-5.2`、`glm-4.7-flash`、`glm-4.5-flash` |
| 豆包（火山方舟） | OpenAI Chat Completions | 官方预置目录 | `doubao-seed-2-1-lite-260915`、`doubao-seed-2-1-pro-260915`、`doubao-seed-2-1-turbo-260628`、`doubao-seed-2-0-mini-260428` |

DeepSeek 当前文档示例为 `deepseek-flash`、`deepseek-v4-pro`；Kimi 当前示例为 `kimi-k3`、`kimi-k2.6`、`kimi-k2.7-code` 等，实际选项以实时列表为准。不会把文档示例当作账户已开通结果。

## 固定国内接口

| 厂商 | 生成端点 | 模型列表 |
| --- | --- | --- |
| DeepSeek | `https://api.deepseek.com/chat/completions` | `GET https://api.deepseek.com/models` |
| MiniMax | `https://api.minimax.cn/anthropic/v1/messages` | 本站维护的官方预置目录 |
| Kimi | `https://api.moonshot.cn/v1/chat/completions` | `GET https://api.moonshot.cn/v1/models` |
| 智谱 GLM | `https://open.bigmodel.cn/api/paas/v4/chat/completions` | 本站维护的官方预置目录 |
| 豆包 | `https://ark.cn-beijing.volces.com/api/v3/chat/completions` | 本站维护的官方预置目录 |

五家均按官方 HTTP 文档使用 `Authorization: Bearer <Key>`，MiniMax 另带 Anthropic 版本头。请求和凭据只发向所选厂商的固定 HTTPS 地址；保留 DNS/实际连接 IP 校验与禁止重定向。不会向海外协议原厂请求或自动回退。

## 列表差异与使用边界

- DeepSeek/Kimi：用户点击刷新后，后端以当前 Key 实时 GET 查询；15 秒上限、1 MiB 响应上限、最多 500 个候选，校验 ID、去重、过滤不适用的音频/向量等模型。鉴权、空列表、超时和非法响应按固定分类提示，不伪造成功或偷偷切换预置列表。
- MiniMax/智谱：截至核对日期，在官方 API 文档索引中未找到公开的 API-Key-only 模型列表端点。因此刷新从本站读取明确标记的官方预置目录，**不校验 Key 有效性、账户余额或模型权限**；这些在生成时由厂商校验。目录是首期支持集合，不宣称覆盖厂商全部模型。
- 豆包：官方 ListFoundationModels 使用 Access Key 鉴权，API Key 不能直接替代；用户不必额外提供 AK/SK，因此同样采用官方预置目录。只列豆包文本生成模型，不把方舟上托管的其他厂商混作豆包模型，也不要求手填 Endpoint ID。
- 刷新不发送正文、不试生成、不产生本站的生成统计，也不会通过小额推理探测 Key。预置目录显示更新时间；厂商发布、停用或变更模型时维护 `ai_providers.PROVIDERS` 和日期并重新核对文档，不使用未文档化接口。
- 用户必须在刷新后显式选择一个模型。切换厂商清空 Key/列表/选择；修改 Key 清空列表/选择并取消旧刷新；过期结果不得写入新厂商配置。编辑内容和已生成图卡不因单独修改配置而丢失。所有配置仅当前页面内存有效。
- 列表返回不保证生成一定成功：仍受余额、权限、配额和模型状态影响。思考模型可能因默认思考较长而超时或用尽输出预算；DeepSeek 按官方文档启用 `response_format={"type":"json_object"}`，提示中给出 JSON 格式；其余沿用协议最小负载，MiniMax 输出上限 4096。JSON/卡片约束不合规最多纠正一次，共用原 60 秒总时限，可能额外计费；没有网络重试或厂商回退。不承诺各模型的真实成功率，暂未获得专用 Key 做真实调用。

配图匹配目前只向模型提供图片说明、正文位置与上下文，不发送全部原始图片进行视觉识别；因此文本模型也能使用。候选可超过 8 张，最终最多 9 卡、只下载所选图片，下载失败跳过并显示提示。

## 官方依据

- [DeepSeek 入门和国内 API 地址](https://api-docs.deepseek.com/)、[Lists Models](https://api-docs.deepseek.com/api/list-models/)、[JSON Output](https://api-docs.deepseek.com/guides/json_mode/)
- [Kimi 生成接口](https://platform.kimi.com/docs/get-api-key)、[列出模型](https://platform.kimi.com/docs/api/list-models.md)
- [MiniMax Anthropic 接口](https://platform.minimax.cn/docs/api-reference/text-chat-anthropic)、[模型目录](https://platform.minimax.cn/docs/faq/models)、[官方 API 文档索引](https://platform.minimax.cn/docs/llms.txt)
- [智谱 OpenAI 兼容接口](https://docs.bigmodel.cn/cn/guide/develop/openai/introduction)、[模型目录](https://docs.bigmodel.cn/cn/guide/start/model-overview)、[官方 API 文档索引](https://docs.bigmodel.cn/llms.txt)
- [豆包 Chat API 与鉴权](https://docs.volcengine.com/docs/ark/chat-api?lang=zh)、[模型目录](https://console.volcengine.com/ark/region:cn-beijing/docs/model-list)、[模型列表管理接口的 AK 要求](https://docs.volcengine.com/docs/ark/list-foundation-models-api?lang=zh)
