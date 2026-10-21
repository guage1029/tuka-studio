# 本地验收记录

日期：2026-10-21。环境：macOS arm64、Python 3.14.7、Flask 3.1.3、Playwright 1.64.0、Chromium。只记录已实际运行的检查；不代表公网验收或用户视觉确认。

当前输出上限为八张含封面，以末尾“八卡编辑与原位成品”记录为准；此前九卡检查属于历史版本验证。

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

## 历史验证：多候选配图与最多九张图卡（现已收紧为八张）

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

## 国产模型接入扩展（2026-10-21）

- 目前接入 8 家：DeepSeek、MiniMax、Kimi、智谱、豆包、通义千问、文心 ERNIE、腾讯混元。百度千帆和腾讯 TokenHub 使用 Key 实时查目录并筛出支持当前 Chat Completions 调用的模型；千问使用真实 DashScope 北京 API，但模型目录采用注明日期的官方预置列表，因为百炼北京目录接口需要当前页面未收集的 Workspace ID。
- 新增调用契约测试：固定国内 HTTPS 端点、Bearer Key、OpenAI Chat Completions 请求与响应；列表过滤百度自有 ERNIE、对应 chat endpoint、文本输出，腾讯仅展示在线混元对话模型；千问目录项能通过生成请求到达其真实固定端点。
- `.venv/bin/python -m unittest discover -s tests -v`：40 项通过。
- `.venv/bin/python scripts/verify_browser.py`：通过，8 家厂商均可刷新/选择目录，JS 错误 0；375/768/1024/1440px 无横向溢出，最小文本对比度 4.86:1。上游全部使用离线替身。
- `.venv/bin/python -m py_compile ai_providers.py scripts/verify_browser.py tests/test_public_tool.py` 与 `git diff --check` 通过。
- 未验证：没有专用 Key，未对新增厂商做真实鉴权、模型发现或生成调用；实际可用性还受用户区域、Key 站点、模型权限、账户额度与服务状态影响。千问静态目录可能滞后，修改需同步更新 `ai_providers.PROVIDERS` 和 `CATALOG_DATE`。

## 样式精简（2026-10-22）

- 可选样式从 46 款调整为 40 款：移除 INS、纯白极简、编辑衬线、瑞士网格、小红书白、日式极简。未注册的模板源文件和样例图片保留在仓库，不会出现在界面或通过样式 ID 渲染。
- `.venv/bin/python -m unittest discover -s tests -v`：40 项通过；旧样式 ID 返回 400。
- `.venv/bin/python scripts/verify_browser.py`：通过；工作台显示 40 款、首页展开 40 款，375/768/1024/1440px 无横向溢出，JavaScript 错误 0。
- `.venv/bin/python scripts/verify_rendering.py`：40/40 可选模板独立渲染、样例指纹匹配、边界检查 0 问题、外部请求 0。

## 模型列表收起行为（2026-10-21）

- 刷新后模型选择框保持收起；点击展开全部选项，选中后自动收起，重复选择同一项也收起。键盘方向键可选择，Enter 确认，Escape 或离开选择框收起。
- `node --check static/app.js`、`git diff --check`、`.venv/bin/python scripts/verify_browser.py` 通过；浏览器实际点击验证收起/再次展开、30 个选项完整展示、键盘确认与 Escape，JavaScript 错误 0。
- 本地 5001 服务已返回更新后的脚本，工作台 HTTP 200。本次没有重启服务或刷新用户已有页面，避免清空页面内配置；重新加载页面后应用新交互。
- 未验证真实手机浏览器；模型请求使用离线上游替身，本次未使用真实 Key。

## 紧凑模型配置与保存（2026-10-21）

- 桌面配置宽 296px、控件 36px、输入文字 12–13px；375px 小屏控件至少 44px。修复后置输入 padding 覆盖 Key 图标留白的问题，改用两列网格将输入与眼睛按钮分开。
- 保存仅确认页面内配置：缺失 Key/模型时就地报错并保留弹层；有效时隐藏 Key、收起并恢复入口焦点，重新打开保留厂商/Key/模型；localStorage/sessionStorage 均无写入。刷新和生成期间禁用保存。
- `node --check static/app.js`、`git diff --check`、`.venv/bin/python scripts/verify_browser.py` 通过，JS 错误 0。覆盖 375/768/1024/1440px、243 字符 Key 显示/隐藏的图标分隔、保存成功/失败、展开/收起与原生成编辑渲染下载流程。
- 首次扩展验收因新增刷新场景触发测试服务 12 次/分钟限频而中断；已在独立测试场景间重置测试计数后通过，生产限频未变。
- 已检查 `output/playwright/config-saved-reopened.png`、`config-375.png` 的桌面/小屏截图。本地 Flask 已重启，重新加载页面后使用新模板与脚本；未修改用户已有标签页状态。
- 未使用真实模型 Key，未进行真实手机设备验收；未部署生产环境。

## 八卡编辑与原位成品（2026-10-21，当前策略）

- 统一最多 8 张含封面（1 封面 + 1–7 内容页）：模型提示、模型结果与编辑数据校验、截图数量、ZIP 接口和页面说明同步。第九张在生成校验中触发原有一次纠正；手工超量渲染/打包在进入浏览器/归档前拒绝，不截断正文或悄悄丢卡。
- 图库始终保留在工作区标题下、状态区和卡片上方，默认展开。生成/编辑/配图上传/重生成不改用户展开状态，草稿和成品之间图库文档坐标不变；没有新增悬浮遮挡区域。
- 草稿为白色中性卡片，文字直接编辑、配图可展开管理；桌面四列最多两行，平板两列、手机单列。长标题与每页五条 50 字要点在卡内滚动编辑，数据完整。生成按钮改为“生成卡片”，成品在同一区域原位切换，可返回编辑；修改后仍使旧图片失效。
- 渲染使用区域扫光与星光，成功逐张渐显；失败、取消与旧响应都会清理 is-rendering / aria-busy。减少动态效果模式隐藏魔法层并禁用成品渐显。整理状态改为“正在整理文案，通常需要几秒。”，原异步版本校验和超时未变。
- `node --check static/app.js`、`git diff --check`、`.venv/bin/python -m unittest tests.test_public_tool`（41 项）与 `.venv/bin/python scripts/verify_browser.py` 通过；45 组截图状态，JS 错误 0，最小文本对比度 4.86:1。
- 浏览器实际验证 20 张候选只取 8 张选中图、超页自动纠正、四列两行、长文案五要点、图库位置/收起状态、编辑/成品切换、上传/单页重生成/换样式、8 张 1242×1660 PNG 与 ZIP、单张字节一致、渲染失败和取消恢复、减少动态效果及刷新清空。上游均为离线替身。
- 初次取消验收的全部断言通过，但延迟测试路由尚未结束就关闭浏览器导致驱动 EPIPE 警告；现通过事件等待路由完成后清理，最终浏览器验收退出 0 且无该警告。单元测试仍有此前即存在的 unclosed-file ResourceWarning，不影响 41 项通过，本轮未追查该旧警告。
- 已查看截图：[八卡草稿](output/playwright/eight-draft-grid.png)、[八卡成品](output/playwright/eight-rendered-grid.png)、[长文案草稿](output/playwright/dense-draft-card.png)、[手机草稿](output/playwright/mobile-draft-card.png)、[动效加载](output/playwright/cards-magic-loading.png)。实际效果的最终用户确认待完成。
- 修改：`main.py`、`app.py`、`static/app.js`、`static/site.css`、`templates/app.html`、`tests/test_public_tool.py`、`scripts/verify_browser.py`、`RPD.md`、`Design.md`、`Task.md`、`README.md`、本记录。原有其他未提交文件未回滚或删除。
- 本地 Flask 已重启；未刷新用户当前标签页，避免清空正文/Key。未使用真实 Key，未验收真实手机设备、未重跑 40 款全量截图，未生产发布。

## 工作台一屏布局（2026-10-21）

- 工作台品牌移至左栏顶部，原文输入保持桌面 370px 宽（1000–1150px 窗口为 320px），高度填满可用空间；辅助控件和生成按钮随之下移。右栏顶部保留步骤、模型配置及默认展开的紧凑样式区，下方为编辑/成品区域；首页布局保留。
- 宽度至少 1000px 且高度至少 700px 时使用一屏布局，八卡四列两行，根据剩余高度保持卡片比例缩放。40 款 SVG 样式缩小并分浅/深两组排列，悬停大预览仍可用。长原文和卡片文案在各自区域内滚动；小屏或过矮窗口恢复文档滚动，避免隐藏内容。这里的一屏指卡片全貌和关键操作，不表示八张卡的全部长文同时可读。
- 有效整理请求开始时收起模型配置，避免弹层遮挡取消按钮；配置校验失败仍打开并聚焦错误。未修改模型协议、生成规则、渲染与下载接口。
- 浏览器验收中发现隐藏字段说明脱离卡片滚动容器导致页面被撑高，已在 `.card-copy` 建立定位容器修复；样式标签继承 margin 导致画廊偏高，已清零；取消操作被配置弹层拦截的问题也已修复。最终验证通过后未再修改实现。
- 修改文件：`templates/base.html`、`templates/app.html`、`static/site.css`、`static/app.js`、`scripts/verify_browser.py`、`RPD.md`、`Design.md`、`Task.md`、`README.md`、本记录。既有无关改动未回滚。
- `./.venv/bin/python -m unittest tests.test_public_tool`：41 项通过，仍有此前的 unclosed-file ResourceWarning，本轮未追查。
- `./.venv/bin/python scripts/verify_browser.py`：51 组截图状态通过，JavaScript 错误 0，最低 UI 文本对比度 4.86:1。桌面 1024×768、1280×720、1440×900、1920×1080 均无页面纵向滚动，八张草稿/成品和全部样式在视口内；375/768px 响应式通过。覆盖暖复古深色、玫瑰松、玻璃的悬停大预览，八卡编辑、上传、重生成、动画、错误/取消、PNG/ZIP 下载、配置保存、旧响应保护和页面内存清理。
- `node --check static/app.js`、`./.venv/bin/python -m py_compile scripts/verify_browser.py`、`git diff --check` 均通过。
- 已重启本地 Flask（127.0.0.1:5001，debug 关闭），隔离浏览器验证实际服务：1440×900 页面总高 900px、输入框宽 370px、高约 595px；1280×640 回退为可滚动布局。未刷新用户已有标签页，避免清空正文和 Key；独立验收浏览器已关闭。
- 已查看视觉证据：[实际服务工作台](output/playwright/workspace-live-1440.png)、[1440px 八卡草稿](output/playwright/eight-drafts-1440.png)、[1280px 八卡成品](output/playwright/eight-results-1280.png)、[1920px 八卡成品](output/playwright/eight-results-1920.png)、[紧凑样式悬停预览](output/playwright/compact-style-hover.png)。[浏览器报告](output/playwright/browser-report.json)。最终用户视觉确认待完成。
- 未验证及风险：模型接口使用离线替身，未使用真实 Key；未验收真实手机设备，未生产发布。低高度桌面上的成品缩略图较小，可点击放大；长内容仍需在输入框或卡片内部滚动。

## 工作台文案、字号与页头分区（2026-10-21）

- 完成六项界面调整：按钮“生成图卡文案”；桌面原文字号 14px/行高 1.8，小屏保持 16px；完整页头分割线与位于线下的①②③步骤；标签“请输入你的内容”及其下方输入说明；工作台移除署名；按用户指定文案将 Key 说明移至右上模型配置下方。首页署名保留。
- 步骤复用原有 step(number) 调用，仅增加当前/已完成样式和 aria-current，没有修改业务阶段跳转、请求、模型校验或下载逻辑。指定隐私短文案为界面替换，原有匿名汇总统计策略未改动。
- 修改：`templates/app.html`、`static/site.css`、`static/app.js`、`scripts/verify_browser.py`、`Design.md`、`Task.md`、本记录。其他既有修改未回滚。
- `./.venv/bin/python scripts/verify_browser.py`：通过，51 组截图状态、JavaScript 错误 0、最低文本对比度 4.86:1。新增文案、字号、说明位置、步骤在线下、工作台无署名断言；生成后第二步当前且第一步完成，渲染后第三步当前且前两步完成。原有八卡渲染/编辑/下载、错误/取消、配置保存和隐私回归均通过。
- `node --check static/app.js`、`./.venv/bin/python -m py_compile scripts/verify_browser.py`、`git diff --check`：通过。
- 已人工查看 1440px 八卡草稿与 375px 工作台截图。本地 Flask 已重启，独立 Playwright CLI 验证实际服务 1440×900：分割线底部 y=84，步骤顶部 y=104.5，输入 14px，页面总高 900px。截图：[当前本地工作台](output/playwright/workspace-refined-live-1440.png)。未刷新用户现有页面，独立验收浏览器已关闭。
- 未验证：本轮仅界面与步骤状态表现调整，未重跑后端单元测试、真实 Key、真实手机设备或生产环境；模型错误恢复策略保持原状。用户刷新前需自行保留正文，页面内 Key 和正文仍会在刷新后清空。

## 输入字号继续缩小（2026-10-21）

- 正文输入及占位文字由 14px 改为 12px；≤600px 保持 16px，避免手机聚焦放大。仅改 CSS 与对应验收断言，业务逻辑不变。同步 Design.md、Task.md。
- 修改文件：static/site.css、scripts/verify_browser.py、Design.md、Task.md、本记录。
- 独立 Playwright CLI 浏览器实际访问本地服务，1440×900 计算样式断言输入/占位文字均 12px，页面高 900px；375×900 输入仍 16px，无横向溢出。截图 output/playwright/input-font-12px.png，验收浏览器已关闭。静态 CSS 已实时生效，无需重启服务；未刷新用户现有标签页。
- git diff --check 与 Python 验收脚本语法检查通过。本次为单项字号调整，未重复全流程/模型调用/真实手机验收。

## 移除三步进度条（2026-10-21）

- 根据用户截图，从工作台删除“整理内容 / 编辑确认 / 渲染下载”条目；清理只用于该条的 JavaScript 状态更新和 CSS。右侧布局直接以样式图库开始。
- 修改：`templates/app.html`、`static/app.js`、`static/site.css`、`scripts/verify_browser.py`（移除旧步骤断言）、`Design.md`、`Task.md`、本记录。
- 本次按指示未运行测试或浏览器；此前的 51 组浏览器验收不包含本次删除后的最终状态。

## 工作台标题编号（2026-10-21）

- 四处标题分别加上①至④，字号统一 14px、字重 650；生成按钮移除右箭头。工作区标题在编辑和成品状态保持固定。
- 修改文件：`templates/app.html`、`static/site.css`、`static/app.js`、`Design.md`、`Task.md`、本记录。
- 按当前开发指示，本轮未运行测试或浏览器；`git diff --check` 通过。
- 未验证：浏览器视觉和完整生成流程；需用户刷新页面查看，刷新会清空正文和 API Key。

## Key 说明文案（2026-10-21）

- 模型配置下方替换为“本站不保存任何信息，刷新后清空。”，同步浏览器验收中的文案预期。未运行测试或浏览器。

## 样式标题颜色（2026-10-21）

- 将“③ 图卡样式”标题颜色设为正文色，与其他编号标题一致；样式计数和折叠箭头颜色保持原样。未运行浏览器或测试。

## 样式计数位置（2026-10-21）

- 将总数改为“③ 图卡样式（37 款图卡样式）”；浅色系与深色系计数分别放在名称后的括号中，并移除工作区初始显示的样式总数。进入编辑后工作区仍显示图卡数量。
- 修改文件：`templates/app.html`、`static/site.css`、`static/app.js`、`Task.md`、本记录。
- `git diff --check` 通过；未运行测试或浏览器，未验证页面视觉效果。重启了本地 Flask 服务（127.0.0.1:5001）以加载模板。

## 页脚品牌文字（2026-10-21）

- 移除页脚“图卡 TUKA”，保留来源署名。仅核对模板内容，未运行测试或浏览器；页面需刷新后查看。

## 公网安全审查与加固（2026-10-21）

- Flask Host 头由默认全接受改为白名单；生产容器仅接受生产域名，本地开发模式才接受 loopback 地址。multipart 请求限制为最多 4 个表单分段。
- 移除 Dockerfile/构建白名单中对已删除 `sensitive_words.py` 的引用；Nginx 关闭版本标识。部署文档同步 Host 白名单、域名维护方式和八个固定模型出口。
- 本地忽略的 `config.py`、`ai_config.json` 含凭据类配置，权限均为 0600；未输出或改写凭据值。Git 历史扫描未发现真实密钥模式，仅发现示例配置和 PRD 示例；Docker 忽略规则采用复制白名单，不会包含这些配置。
- `.venv/bin/python -m unittest discover -s tests -v`：43 项通过，覆盖 Host 头拒绝与 multipart 分段上限；另以 `TRUST_LOCAL_PROXY=1` 验证生产配置拒绝 `localhost`、接受生产域名。一次测试中 Werkzeug multipart 测试编码器报告临时文件 ResourceWarning，复跑定位为测试客户端编码器，不是应用上传落盘。
- `uvx --from pip-audit pip-audit -r requirements.txt`：未发现已知依赖漏洞；`uvx --from bandit bandit -q -r app.py main.py ai_providers.py safe_http.py metrics.py`：无发现。
- 扩展 Bandit 扫描运行脚本后只有 150 条低级 `assert_used`（均位于离线验证脚本），无中/高级发现。HTML/CSS 检查未发现活动卡片模板中的脚本、外部资源加载或 CSS 外链；独立 `family_photo_recitation.html` 属于仓库根目录草稿，Dockerfile 不复制，Flask 也不从根目录静态提供。
- Python 编译、前端 `node --check` 与 `git diff --check` 通过。
- 未执行 Docker 构建或 Nginx 配置检查（本机未安装相应工具）；未检查生产主机、DNS、TLS 证书、CDN/WAF、系统补丁与出站防火墙，不能据此宣称已达到生产上线验收。

## 样式图库排版（2026-10-21）

- 调整右栏样式标题顶边与左栏输入标题对齐；浅色/深色样式组改为上下排列，移除组名前的圆点。
- 修改文件：`templates/app.html`、`static/site.css`、`Design.md`、`Task.md`、本记录。
- 本轮未运行浏览器或测试；尚未进行页面视觉验收。

## 移除敏感词检查并修正按钮复制（2026-10-21）

- 删除工作台敏感词入口/说明、前端事件、`/check-sensitive` Flask 路由、词库 import 与 `sensitive_words.py` 模块；同步移除 Nginx 写接口匹配。
- 生成按钮文字和编号强制为白色，并限定选择复制范围；隐藏样式桥接 select 不再包含可复制的样式名称，避免“小红书”混入按钮文案。样式库原有可见模板名保留。
- 修改：`templates/app.html`、`static/app.js`、`static/site.css`、`app.py`、`deploy/nginx.conf`、删除 `sensitive_words.py`、`Design.md`、`Task.md`、本记录。
- 本轮未运行测试或浏览器；尚未验证复制文本和真实界面。

## 样式数量更新（2026-10-21）

- 从可选列表移除 `notion`（备忘录）和 `ppt-magazine-bold`（大胆杂志）；登记的模板数从 40 减至 38。旧模板源文件、manifest 项和缩略图沿用此前精简规则留在仓库，不再注册、展示或接受对应样式 ID。
- 选中态移除底部绿色 inset 横线，保留右上角勾选标记。首页说明与图库计数、工作台计数均由登记样式数量动态生成；README、RPD、Task 和现有验收断言改为 38。
- 修改：`main.py`、`app.py`、`static/site.css`、`tests/test_public_tool.py`、`scripts/verify_browser.py`、`README.md`、`RPD.md`、`Task.md`、本记录。
- `git diff --check` 通过。本轮未运行测试或浏览器；已更新但未执行 38 款的测试断言。

## 样式图标与模型纠错（2026-10-21）

- 删除模型弹层的预置目录解释；移除“千禧铬银”及模板、主题 CSS、样例缩略图和 manifest 条目，总数同步为 37。
- 样式 SVG 改为基于实际主题调色板的 4:3 卡片缩略图；1024px 视口压缩图库留白以维持一屏布局。
- 校验错误细化到页码、要点序号和字数；一次纠错携带上次 JSON 并要求只改违规字段。增加第 5 页超长要点回归用例。
- `.venv/bin/python -m unittest discover -s tests -v`：45 项通过；`scripts/verify_browser.py`：通过；`scripts/verify_rendering.py`：37 个模板通过；`git diff --check` 和 Python 编译通过。
- 未用真实厂商 API Key 验证模型是否遵循纠错提示；只验证了模拟响应与本地 UI。

## 工作台页脚隐私说明（2026-10-21）

- 移除页头下方的隐私说明，将原文放入工作台专属 footer 并右对齐。
- `.venv/bin/python -m unittest discover -s tests -v`：45 项通过；`scripts/verify_browser.py`：通过，覆盖 375、768、1024、1440px 视口和页脚位置。
- `git diff --check` 通过。

## 样式区边框与标题对齐（2026-10-21）

- `scripts/verify_browser.py`：通过，覆盖 1024×768、1280×720、1440×900、1920×1080 一屏布局及响应式回归。
- `git diff --check` 通过；浏览器截图确认样式分组边框与 ③/④ 标题对齐。

## 工作台缩放适配（2026-10-21）

- `scripts/verify_browser.py`：通过，模拟 640–1920px 横向缩放及 768×600 矮视口；桌面左右分区保持，卡片网格按空间调整，无横向溢出。
- 验证低高度下输入面板保持可视、页脚可滚动到达；页面脚本无异常，文本对比度检查通过。
- `git diff --check` 通过；未用实体显示器或真实浏览器缩放百分比测试。

## 工作台初始空状态（2026-10-21）

- 浏览器回归确认空状态默认可见、位于图卡工作区内，生成文案成功后隐藏；各测试视口无横向溢出。
- `scripts/verify_browser.py` 与 `git diff --check` 通过；1440×900 截图确认恢复效果。
