# 本地验收记录

日期：2026-10-21。环境：macOS arm64、Python 3.14.7、Flask 3.1.3、Playwright 1.64.0、Chromium。只记录已实际运行的检查；不代表公网验收或用户视觉确认。

## 已实现与修改范围

- 文档：`RPD.md`、`Design.md`、`Task.md`、`README.md`、`QUICKSTART.md`、`DEPLOYMENT.md`、`PROVIDERS.md`、本文件。
- 服务：`app.py`、`main.py`、`ai_providers.py`；新增 `safe_http.py`、`metrics.py`。请求独立厂商/Key/模型配置、五家国内固定端点与两协议、实时/预置模型列表、图片校验、隔离渲染、内存 PNG/ZIP、同源和资源限制、汇总统计。
- 页面：`templates/base.html`、`templates/index.html`、`templates/app.html`，以及 `static/site.css`、`static/common.js`、`static/home.js`、`static/app.js`、标记、字体和真实样例。
- 模板：13 款既有模板和 33 个 `template_ppt_*.html`，均为独立 HTML 与内嵌 CSS；保留主题 MIT 和字体 OFL。补充自托管中文字体回退，修复长文带图时的溢出与遮挡。
- 交付与验证：`.gitignore`、`.dockerignore`、`Dockerfile`、`compose.yaml`、`deploy/nginx.conf`、`requirements.txt`、`start.sh`、`start.bat`、`scripts/generate_samples.py`、`scripts/verify_rendering.py`、`scripts/verify_browser.py`、`tests/test_public_tool.py`。旧 `test_gemini.py` 入口改为说明，不再导入旧 Key、打印凭据或调用被移除的 SDK。
- 未提交 Git commit。开始时已有未提交和未跟踪文件；未回滚无关改动。旧配置和旧 output 保留，未使用历史 Key；开发服务的统计在 `/tmp/tuka-browser-metrics.sqlite3`，仅有本地访问次数。

## 工程验证

| 已运行命令 / 检查 | 实际结果 |
| --- | --- |
| `.venv/bin/python -m unittest discover -s tests -v` | 38 项通过。模型格式纠正、共享时限与两协议兼容；五家固定端点与鉴权负载、两协议与鉴权、超时、截断、空响应、非法 JSON；实时列表的去重/过滤/非法响应/鉴权/超时、预置目录不探测 Key、拒绝自定义地址和海外厂商、刷新不制造生成次数；配置和正文并发隔离；SSRF、混合 DNS、TLS 对端、重定向、长度和超时；注入和图片校验；上传大于 500 KiB 仍使用 BytesIO；失败/取消关闭 context/browser；ZIP 原字节；统计并发与保留期。 |
| `.venv/bin/python scripts/generate_samples.py` | 46 款、138 张 WebP（封面缩图、封面大图、内容页），只使用自有示例内容；manifest 保存内容及渲染指纹。 |
| `.venv/bin/python scripts/verify_rendering.py` | 46/46 独立渲染，原始 PNG 1242×1660；样例指纹精确匹配。24 字标题、80 字副标题、5 个各 10 字标签、5 条各 50 字要点并带配图：无越界、文字与图重叠或隐藏容器裁切；外部请求 0。 |
| `.venv/bin/python scripts/verify_browser.py` | 完整真实浏览器流程通过，JavaScript 错误 0；模型传输使用离线替身，未调用外部模型。 |
| `node --check static/app.js`、`node --check static/home.js`、`node --check static/common.js` | 均通过。 |
| `.venv/bin/python -m compileall -q app.py main.py ai_providers.py safe_http.py metrics.py scripts tests`、`bash -n start.sh`、`git diff --check` | 均通过。 |
| `.venv/bin/gunicorn --check-config app:app`，及本机 127.0.0.1:5002 启动真实单 worker/8 线程请求后停止 | 配置检查通过；`GET /app?style=apple` 返回 200 和 no-store；只用临时统计数据库。 |
| `.venv/bin/python metrics.py --db /tmp/tuka-browser-metrics.sqlite3` | 只读显示逐日和七天次数、成功率、热门模板；无用户身份字段。单元测试另外验证数据库字节未改写。 |
| `.venv/bin/python test_gemini.py` | 只输出迁移与离线测试说明，无网络请求。 |

模板 PNG 与指纹检查来自上一轮本地验收；本轮未改动模板、样例或渲染逻辑，因此未重复生成 46 款截图。

浏览器覆盖：五家厂商下拉、实时与预置列表说明、列表加载/错误、换厂商清 Key、改 Key 清模型、旧列表不覆盖新厂商、MiniMax Anthropic 生成；首批 12 款、展开 46 款、放大/Escape/焦点恢复、样式深链、折叠配置、就地错误、文案生成、删除后添加要点、单页重生成、上传位图、渲染、单 PNG 与 ZIP（字节一致）、换样式重新渲染、错误保留、过期响应不覆盖新编辑、取消、页面刷新清空配置和正文、独立浏览器上下文不共享状态。刷新只增加访问次数，不增加生成成功或下载点击。

仅 SQLite 汇总持久化。截图结果、临时 HTML、ZIP 与上传文件在应用内存中处理。测试核对 output 无新增用户产物；运行时 Chromium profile 的实际磁盘与 swap 行为仍需 Linux 内存盘验收，不能把应用级检查解释为整台机器永不落盘。

## 视觉验证

- 首页、工作台和展开配置均在 375、768、1024、1440px 截图；无横向溢出。1024/1440px 初始工作台主按钮完整位于 900px 高度首屏内；小屏顺序布局可滚动操作。
- 34 组截图状态（含编辑、加载、输入错误、模型错误、下载和样例弹窗）检查可见界面文本，最低对比度 5.20:1。此数值针对网页 UI，不含位图内部或模板装饰文字。
- 主要表单与生成控件实测宽高均 ≥44px；键盘 Enter 展开配置、焦点外框、弹窗 Escape 与焦点恢复、减少动态效果检查通过。
- 人工查看首页、工作台和状态图，以及 46 款长文配图联系表。拍立得采用旋转纸张，布局测量先去除装饰旋转以避免轴对齐矩形误报，实际截图保留旋转。
- 视觉修复包括：长要点不再被 flex 压缩容器遮挡；胶囊配图不越界；拍立得无效 CSS 和长文裁切修复；长副标题/标签带图时调整间距和字号。下载状态无操作遮挡。

证据（本地生成，不提交用户产物）：

- [浏览器报告](output/playwright/browser-report.json)、[46 模板报告](output/playwright/render-report.json)
- [桌面首页](output/playwright/home-1440.png)、[手机首页](output/playwright/home-375.png)、[桌面工作台](output/playwright/app-1440.png)、[手机工作台](output/playwright/app-375.png)
- [实时模型](output/playwright/provider-deepseek.png)、[MiniMax 预置目录](output/playwright/provider-minimax.png)、[智谱目录](output/playwright/provider-zhipu.png)、[豆包目录](output/playwright/provider-doubao.png)、[刷新错误](output/playwright/models-error.png)、[刷新中](output/playwright/models-loading.png)
- [配置](output/playwright/config-1440.png)、[编辑](output/playwright/editor-1440.png)、[加载](output/playwright/loading.png)、[模型错误](output/playwright/upstream-error.png)、[下载就绪](output/playwright/download-ready-1440.png)
- [模板长文配图联系表](output/playwright/template-contact-sheet.jpg)。完整分辨率截图为同目录 `edge-<style>.png`。

## 未验证事项与剩余风险

1. 没有提供专用测试 Key，未做五家厂商的真实模型调用或带 Key 列表请求；目前的成功结论是离线协议/流程验证。预置目录不是账户可用列表，Key、余额和权限在生成时由厂商验证；来源和日期见 `PROVIDERS.md`。OpenAI 使用 model/messages，DeepSeek 另启用官方 JSON 输出模式；采用服务商默认输出长度；Anthropic max_tokens 为 4096。截断会提示错误。取消/传输超时不保证上游立即停止或停止计费。
2. 当前机器无 Docker、nginx，未构建 Linux 镜像、执行 `nginx -t`、验证生产 tmpfs/代理缓冲/日志/CDN/WAF/主机 swap 或生产资源上限；也未做真实主机负载与渗透测试。Windows 启动脚本仅审阅，未在 Windows 执行。
3. 未执行生产部署、证书、DNS、外部通知或旧数据删除；不能声称 tuka.guage.chat 已上线。
4. 原有 13 款模板的历史 README 声称 MIT，但未附原始许可；需维护者确认授权。33 款主题 MIT 与字体 OFL 已保留；中文子集不含全部罕见字，系统回退和跨系统字体差异仍需目标 Linux 机器复核，样例应在目标环境重新生成并验收。
5. 本地截图复核不替代用户视觉验收；未在 Safari/Firefox 或真实触屏设备测试。匿名统计可重复访问与点击，受网络中断、取消和主动伪报影响，不代表独立用户、留存、严格漏斗或已保存文件；低流量无新写入时过期行在下一次事件写入才物理清理。

本轮修改另包括 `deploy/nginx.conf` 的模型列表接口限频；未修改其他生产资源。厂商文档核对包括官方模型目录、协议地址、Kimi 列表 Markdown 文档和豆包列表 AK 鉴权说明，没有使用历史 Key。

## 本轮国产配置修改文件与预览

- 运行代码：`ai_providers.py`、`app.py`、`safe_http.py`。
- 页面与交互：`templates/app.html`、`templates/index.html`、`static/app.js`、`static/site.css`。
- 验证与配置：`tests/test_public_tool.py`、`scripts/verify_browser.py`、`deploy/nginx.conf`、`test_gemini.py`。
- 文档：新增 `PROVIDERS.md`，同步 `RPD.md`、`Design.md`、`Task.md`、`README.md`、`QUICKSTART.md`、`DEPLOYMENT.md`、本文件。
- 本轮再次运行：26 项 unittest、浏览器完整流程、JS 语法、Python compileall、Gunicorn 配置、git diff --check，均通过；模板和样例未改动，不重复 46 款 PNG 验收。真实列表/生成均未使用专用 Key，不能据此宣称厂商线上调用通过。
- 已重启仅绑定 127.0.0.1:5001 的本地预览；Playwright CLI 实际打开、展开配置并截图，确认五家厂商下拉框、Key、刷新按钮与模型选择，旧协议/地址字段不再出现。没有部署或 DNS 操作。
- [实际预览配置截图](output/playwright/provider-config-preview.png)。仅有空配置，无真实 Key；CLI 浏览器检查后关闭，本地开发服务保留供预览。

## 本轮 DeepSeek 通用报错修正

- 只读匿名汇总中观察到生成阶段的 bad_request；该计数不包含 Key、正文、URL 或用户身份，因此不能把它当作原请求的完整诊断。
- 用自有文章与被拒绝的图片链接复现：图片 403 时返回“输入或模型配置不正确”，且模型调用次数为 0；损坏位图与超过 8 张图片同样存在误归因。先补回归测试，原代码出现 6 个失败断言，再修复并通过 28 项测试。
- 新分类 image_fetch_failed / too_many_images 保留原有图片验证、SSRF 和限额，失败仍中止并保留正文，不静默丢图。前端将错误标记在正文旁，图片数量先行校验，长度按 Unicode 字符与服务端保持一致。
- 按 DeepSeek 官方错误码将 402 映射为 insufficient_balance、400/422 映射为 provider_rejected；与鉴权错误分开，始终只返回固定中文提示，不输出原始上游错误。官方依据：[DeepSeek 错误码](https://api-docs.deepseek.com/quick_start/error_codes/)。
- 修改文件：`main.py`、`ai_providers.py`、`safe_http.py`、`app.py`、`static/app.js`、`tests/test_public_tool.py`、`scripts/verify_browser.py`；同步 `README.md`、`RPD.md`、`Design.md`、`Task.md`、本文件。
- 实际运行：`python -m unittest discover -s tests -v`（28 项通过）、`python scripts/verify_browser.py`（31 组状态，JS 错误 0，完整生成下载通过）、`node --check static/app.js`、Python compileall、`git diff --check` 均通过。浏览器涵盖配图失败标记正文、超过 8 张不发送请求、移除失败配图后继续生成、余额错误保留编辑与隐藏上游原始信息。
- 证据：[配图错误](output/playwright/image-fetch-error.png)、[配图超量](output/playwright/image-limit-error.png)、[余额错误](output/playwright/balance-error.png)、[浏览器报告](output/playwright/browser-report.json)。
- 未验证：用户原文和模型名称尚未提供，不能确证这次具体失败就是配图问题；未读取其 Key 或正文，未调用真实模型。没有改动模板、重新生成样例、部署生产或操作 DNS。

## 多候选配图与最多九张图卡（当前策略，替代此前输入八图限制）

用户明确要求按输出图卡数限制，允许输入多图并丢弃多余图片。原先的八图拦截与“选中图失败即中止”已移除；此前错误复现记录作为历史保留，不再代表当前交互。

- 提取唯一 HTTPS 候选 URL，使用稳定图号和图片说明替换 Markdown 原位置，保留与正文的相邻关系。模型根据说明、前后文和卡片主题选择，最多一封面加八内容页，每卡最多一图。不会按原文图片数量增加图卡，也不会简单取前八张。
- 模型结果先验证页数、图号类型与范围，再获取选中的 URL。未选图不下载，重复只取一次；选中内网/重定向/过大/无效/超时图片仍按原有规则拒绝获取，但置空并在成功状态中汇总跳过数量，文案保留，用户可补图。最多下载九个不同 URL，沿用单图 10 秒、合计 30 秒、2 MiB 和 1200 万像素限制。
- `/preview` 独立返回 `image_summary`（candidates/selected/used/failed），不混入可编辑的 `slides_data`，不保存 URL 或原始用户数据，不增加模型调用次数。
- 修改文件：`main.py`、`app.py`、`safe_http.py`、`static/app.js`、`templates/app.html`、`tests/test_public_tool.py`、`scripts/verify_browser.py`；同步 `README.md`、`RPD.md`、`Design.md`、`Task.md`、`PROVIDERS.md`、本文件。
- `.venv/bin/python -m unittest discover -s tests -v`：33 项通过。覆盖 20 图非顺序选择第 18/3 图、图号与上下文传递、去重、不下载未选图、坏图跳过、内网不连接、最多九卡、重复选图只获取一次、非法模型图号和十卡输出在下载前拒绝、摘要与卡片数据分离。新策略测试在旧实现下失败，修复后通过。
- `.venv/bin/python scripts/verify_browser.py`：32 组状态，JS 错误 0，最低 UI 文本对比度 5.2:1；20 候选只获取九张选中图，生成九卡、真实 Chromium 渲染、ZIP 含九张 1242×1660 PNG；坏图跳过提示、单页编辑/重生成、三卡及九卡下载、五厂商配置和异步保护均通过。
- `node --check static/app.js`、Python compileall、`git diff --check` 通过。未改动模板和样例，未重复全部 46 款样例渲染；此次已真实渲染并下载九卡。
- 证据：[多图选择](output/playwright/many-images-nine-cards.png)、[九卡下载](output/playwright/nine-cards-download.png)、[坏图跳过](output/playwright/image-skipped.png)、[浏览器报告](output/playwright/browser-report.json)。
- 限制：当前依据图片说明、位置与正文上下文匹配，不做像素识别，不能宣称识别了图中视觉细节。仍受正文 50–20000 字和请求资源上限约束，不新增输入图数门槛。模型语义匹配质量未用真实 Key 验证；本地离线模型仅验证流程和图号映射正确。未读取用户 Key、未调用真实模型、未上线或改 DNS。


## 模型格式错误兼容（当前策略，2026-10-21）

用户再次遇到“模型返回的内容格式不正确”。未读取其 Key、正文或模型原文，因此不能确认这次具体是 JSON、字段或长度中的哪一种；不能把离线复现当作用户请求的确诊。代码检查确认原实现未开启 DeepSeek JSON 模式，且将所有卡片校验失败混为 bad_response；用自有超长标题、非法 JSON、缺省字段和数字字符串图号复现失败，再修复。

- `ai_providers.py`：DeepSeek 按官方 JSON Output 文档开启 response_format=json_object；完整 JSON 围栏大小写兼容。上游响应信封错误仍为 bad_response；模型 JSON 非对象/不合法为 invalid_json，不把内容带入日志或错误。
- `main.py`：整理和单页重生成共用最多一次格式纠正，JSON/卡片字段不合规才重新生成，两次共享 60 秒截止时间。保留字数和最多九卡等校验，不直接截断文本、不放松用户编辑/图片/渲染边界。兼容缺省/空值副标题和标签、数字字符串图号；非法或越界图号忽略，只能获取用户候选 URL，不触发额外图片请求。
- `safe_http.py`：新增 invalid_json / invalid_card_data 固定中文错误；失败保留输入，最终分类不含用户数据。统计直接复用已有受控错误枚举，纠正过程不重复记生成开始/失败/成功。
- 修改文件：`ai_providers.py`、`main.py`、`safe_http.py`、`tests/test_public_tool.py`、`scripts/verify_browser.py`、`RPD.md`、`Design.md`、`Task.md`、`README.md`、`PROVIDERS.md`、`VERIFICATION.md`。未改 UI、模板、生产配置或读取旧配置；既有无关脏改未回滚。
- `.venv/bin/python -m unittest discover -s tests -v`：38 项通过。覆盖 OpenAI/Anthropic 两协议非法 JSON/超长字段纠正；缺省可选字段和字符串图号；无效引用不下载；第二次仍错就停止；不重试鉴权；60 秒共享时限到期不再调用；单页纠正保留其他卡片、图片和调用方数据。
- `.venv/bin/python scripts/verify_browser.py`：34 组状态通过，JavaScript 错误 0，最低 UI 文本对比度 5.20:1。真实浏览器验证 JSON 第一次失败、第二次恢复；两次仍失败时保留正文和三张已有编辑卡；统计只记一次最终结果；超长标题加十卡返回经一次纠正变为九卡，兼容大写 JSON 围栏、空可选字段、字符串图号，仅取九图并真实渲染/ZIP 下载九张 1242×1660 PNG；其余五厂商和编辑下载回归通过。
- `.venv/bin/python -m compileall -q app.py main.py ai_providers.py safe_http.py metrics.py scripts tests`、`node --check static/app.js`、`git diff --check` 均通过。未改动模板，未重复 46 款渲染；本轮已真实渲染九卡与三卡。
- 视觉证据：[格式失败保留编辑](output/playwright/format-error.png)、[自动恢复](output/playwright/format-recovered.png)、[九卡下载](output/playwright/nine-cards-download.png)、[浏览器报告](output/playwright/browser-report.json)。已人工查看格式错误和九卡下载截图。
- 未验证与风险：所有模型响应仍是离线替身，未使用真实 Key；语义提炼和选图质量未验证，格式修正不保证所有模型都成功。自动纠正可能多产生一次模型费用，但不扩大总时限、不回退厂商；取消/超时不保证上游停止计费。没有生产部署或 DNS 操作。

### 后续失败的根因复核

用户在“JSON 模式 + 一次格式纠正”版本仍收到 `invalid_card_data`。本机只读汇总表新增了该受控错误计数；这证明 API 返回已能解析为 JSON，失败发生在卡片 schema 校验，不是 Key、网络或 JSON 解析。表中不存具体字段、正文或响应，不能逆向还原本次是哪条限制触发。

回看改动前 `HEAD:xiaohongshu-generator/main.py`：模型结果基本只补 `cover_image`、内容页缺失图片、空标题和非列表 content；没有对标题/要点字符数、标签数量、每页要点数设硬限制，也没有拒绝超过八页的模型输出。改版新增严格 `validate_slides_data`（标题24字、要点50字、标签5个、每页1–5要点、内容页最多8页），并把所有违反统一映射为 `invalid_card_data`。新加的一次纠正只追加通用约束，未指出具体不合规项，因此模型很可能重复相同问题。这解释了“原来能返回，改版后报错”以及纠正后仍失败。

已改 `main.py`：保持九卡、文字/渲染边界，在模型输出校验时识别并报告静态规则，例如“第3页有空要点或要点超过50字”；纠正提示附上同一条具体规则，不包含/记录模型原文。编辑输入仍经过原有严格校验。修复已写入文件；**本次根因修复尚未重跑测试、浏览器或真实模型**，也未读取 Key/正文/模型原文。
