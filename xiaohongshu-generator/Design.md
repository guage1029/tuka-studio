# tuka.guage.chat 实现方案

更新：2026-10-21。Flask + 原生 JavaScript + Jinja2 + Playwright，不引入前端框架。

## 代码边界
`app.py`：请求校验、资源门限、路由；`ai_providers.py`：五家国产厂商固定路由、模型列表和两协议；`main.py`：Markdown、卡片结构、转义模板、内存截图；`safe_http.py`：受限 HTTPS；`metrics.py`：独立 SQLite 汇总和只读报告。页面/样式/脚本在 `templates/`、`static/`。沿用敏感词库，只作编辑提示、不承诺合规。

## 安全与资源
- 模型目标固定为 `PROVIDERS.md` 列出的五家国内 HTTPS 接口，前端只传 provider/api_key/model，拒绝地址或协议覆盖。OpenAI/Anthropic 仅指兼容格式，不调用海外原厂服务。检查全部 DNS 地址，阻断非公网和映射地址；连接锁定已验证 IP，TLS 用原主机名校验证书，核对 socket 对端。不跟重定向、不读环境代理、无网络重试或厂商回退。OpenAI 使用 model/messages，DeepSeek 另启用 response_format=json_object，长度由服务商默认值决定；Anthropic 带必需的 max_tokens=4096，两协议均不发送采样参数。
- 配置不读写 `config.py`、`ai_config.json`。不打印模型响应/异常细节/正文，不回传上游原始错误，仅固定分类与提示。候选配图不限制为 8 张；选中图获取失败跳过并提示采用/失败数量，避免误报模型配置；HTTP 402 区分余额不足，400/422 区分厂商参数拒绝。
- 请求体 32 MiB、正文 50–20000 字、最多 9 张卡（1 封面 + 1–8 内容页）、每页最多 5 要点；标题/标签/要点有限长。位图输入 ≤2 MiB、≤1200 万像素，仅 PNG/JPEG/WebP，解码重编码剔除元数据/动画。Markdown 提取唯一 HTTPS URL 并以稳定编号、说明保留在正文原位置。模型先按说明和上下文为最多 9 张卡选择图号；兼容数字字符串，非法或越界图号置空，仅下载校验后的所选图片并转 data URL；同 URL 只获取一次。多余不下载，选中图下载/验证失败置空并汇总提示，不阻断文案。模型不能引入新 URL。当前为文本上下文匹配，不识别像素，也不额外发起视觉模型请求。
- 模型响应只接受 JSON 对象或完整 JSON 代码围栏，不 eval、不修补非法 JSON、不直接截断文案。缺省/空值副标题与标签可为空；必需字段、字数、页数仍严格校验。文案整理和单页重生成共用最多一次格式纠正：只针对 invalid_json / invalid_card_data，追加明确约束后重新生成，两次调用合计不超过原 60 秒，可能增加一次模型费用。鉴权、余额、网络、空响应、截断不自动重试。最终提示区分 JSON 与卡片字段问题，只存受控错误分类；一次用户动作只统计一次生成结果。
- 模型列表实时请求 15 秒；`POST /api/models` 受同源/请求大小/重请求并发/限频门限保护，只返回模型 ID 与来源。DeepSeek/Kimi 实时查询，其余读取有日期的官方预置目录，不假装验证 Key；不做推理探测，不计生成统计。
- 模型总时限 60 秒、单图获取 10 秒、整次图片处理 30 秒、截图 45 秒。进程内最多 2 个重请求、1 个截图，拒绝排队；限频使用短期内存摘要，不保存 IP/身份。生产单 worker 多线程，Nginx 边缘限频。取消不保证上游立刻终止，但受硬超时约束且不落盘。
- 每次截图独立 browser/context，禁脚本、service worker、外部请求；只内嵌受信字体/位图。multipart 上传覆盖 Werkzeug 默认文件流，全程 BytesIO，禁止超过 500 KiB 后自动落盘。无临时 HTML、共享输出和截图文件；生产 Chromium profile 在内存 `/tmp`，finally 关闭 context/browser，超时亦清理。
- 页面/API no-store，同源写入、CSP、防嗅探、禁止嵌入。反代关闭请求/响应缓冲及访问日志；容器只读根目录、内存临时盘、禁 core dump、资源限制；HTTPS 证书在反代配置。

## 交互一致性
配置/正文/编辑/成图仅在页面内存。选择厂商、填写 Key、刷新后显式选择模型。切厂商清 Key 和列表，改 Key 清列表；独立 AbortController 和请求身份校验防止旧列表覆盖新厂商，原有文案保留。编辑或样式变化使成图失效；版本号与请求取消防止过期响应覆盖。重生成期间允许编辑，版本变化丢弃响应。要点从数组重建 DOM，以索引绑定，不生成可重复的持久 ID。用户数据只经 textContent/value/受校验 img.src 使用，不插入 HTML。

生成接口把候选数、选中数、采用数、失败数作为独立 `image_summary` 返回，前端显示采用/跳过说明，不进入可编辑卡片数据或统计数据库。

单张下载使用浏览器数据；ZIP 将当前成图发送至内存打包接口。旧共享下载与全局配置接口移除；失败不清空工作数据。

## 统计
`counts(day,event,style,error,count)` 复合主键原子 UPSERT；固定事件/模板/错误枚举，拒绝额外字段。写入时清除 90 天外记录。生成开始/结果仅服务端记录，前端只上报样例/选样式/下载；访问由页面 GET 记录。统计故障只记固定告警，不影响生成。CLI 用 `mode=ro`，展示逐日与七天次数、成功率、下载点击和热门模板，无 Web 查询。

## 视觉
按 ui-ux-pro-max minimal/gallery、表单、响应式与键盘指导：浅灰白画布、近黑正文、低饱和红色强调；大标题与实图组合，不嵌套多层卡片。自托管 Inter/Noto Sans SC；正文 ≥16px，次级正文对比度 ≥4.5:1，焦点外框，控件 ≥44px。首页首批 12 款，其余按需创建图片；工作台宽屏双栏，≤900px 顺序布局。

## 查证来源
国产厂商协议、端点、模型清单和官方来源集中记录在 [PROVIDERS.md](PROVIDERS.md)。以下 OpenAI/Anthropic 链接仅作为格式参考。
- https://developers.openai.com/api/reference/resources/chat
- https://platform.claude.com/docs/en/api/messages
- https://playwright.dev/python/docs/api/class-browser
- https://github.com/lewislulu/html-ppt-skill （主题来源，MIT）
- https://github.com/google/fonts （字体与 OFL 许可）
