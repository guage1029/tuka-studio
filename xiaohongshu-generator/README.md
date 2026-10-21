# 图卡 · tuka.guage.chat

自带国产模型 Key，把长文整理为可编辑、可下载的图卡。Flask、原生 JavaScript、Jinja2、Playwright，46 款独立 HTML 模板；无需账号。

## 本地启动
需要 Python 3.11+。在项目目录执行：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m playwright install chromium
.venv/bin/python app.py
```

首页：http://127.0.0.1:5001/

工作台：http://127.0.0.1:5001/app

也可运行 `./start.sh`，Windows 用 `start.bat`。设置均在工作台填写，不需要 `config.py`。旧配置、旧输出不会被读取或自动删除，不要将它们放入公网目录。`main.py` 不再运行旧的落盘 CLI。

## 使用
1. 选择 DeepSeek、MiniMax、Kimi、智谱 GLM 或豆包，输入国内开放平台按量 API Key，点击“刷新模型列表”，再从下拉框选模型。地址和兼容协议由服务端配置，无需填写；不接入海外厂商、自定义 URL 或 Coding Plan 专用 Key。
2. 粘贴 50–20000 字正文或 Markdown，选样式，整理文案。模型费用由指定服务收取。
3. 编辑封面、标签、要点和配图，可单页重生成；确认后渲染。每组最多 9 张，PNG 为 1242 × 1660 px，可单张或 ZIP 下载。换样式只渲染，不调用模型。

DeepSeek/Kimi 从官方实时获取列表；MiniMax/智谱/豆包使用有更新日期的官方预置目录，Key 和模型权限在生成时校验。刷新不调用生成接口。模型、协议、固定端点及来源见 [PROVIDERS.md](PROVIDERS.md)。

底层 OpenAI 兼容协议使用 `model + messages`，DeepSeek 另启用 JSON 输出模式；不发送各模型支持不同的采样与长度选项，输出长度采用服务商默认值；Anthropic 使用必需的 `max_tokens=4096`。传输超时不等于上游停止计费，请选择适合短文案的模型。

配图仅 PNG/JPEG/WebP，输入 ≤2 MiB、≤1200 万像素，校验重编码后最长边 1600px。Markdown 可以含多张 HTTPS 候选配图，不以输入图数拦截。模型依据图片说明、位置和正文上下文，为最多 9 张图卡选取合适图片；只下载最终选中的图片，重复 URL 去重，多余不使用。选中图获取失败时跳过并提示，可在编辑区补图；不跟随重定向，不访问内网。当前不识别图片像素内容。

## 失败提示

- 模型 JSON 或卡片字段、字数、页数不合规时，最多自动纠正一次；两次调用共用 60 秒，可能增加一次模型费用。仍失败会区分 JSON 与卡片格式提示并保留输入；不直接裁切文案。缺省副标题/标签、数字字符串图号可兼容，非法图号忽略。鉴权、余额、网络、空响应和截断不自动重试。
- 正文候选配图可以超过 8 张；最终图卡仍最多 9 张（封面 + 1–8 内容页），每页最多一张配图。源站拒绝、超时、格式不支持或不安全的选中图会跳过，生成状态显示候选/采用/获取失败数量，文案和原始正文保留。可以在编辑区补充或替换图片。
- 厂商返回 401/403、402、400/422，分别提示鉴权失败、余额不足、请求参数被拒绝；不回传上游原始错误或内容。失败保留正文和当前编辑，修正后可重试。

## 数据与统计
Key、正文、配图、生成结果仅在请求和当前页面内存使用，不落盘、无历史、刷新后清空。服务器转发正文至用户所选国产厂商的国内模型接口，本站不承诺第三方保留策略。生产应使用内存临时盘、HTTPS 反代并关闭请求日志/缓存/缓冲，见 [DEPLOYMENT.md](DEPLOYMENT.md)。

唯一持久化数据是独立 SQLite 匿名汇总：日期（UTC+8）、事件、模板、错误分类、次数。保留 90 天，不保存原始事件、IP、Key、URL 或用户标识。访问/生成结果由服务端统计；浏览器只报告样例/样式选择/下载点击。生成包括文案整理和单页重生成，渲染不计生成事件。次数不等于人数或留存；下载点击不保证已保存。

只读本地查询（不提供公开统计接口）：

```bash
.venv/bin/python metrics.py
.venv/bin/python metrics.py --db /path/to/metrics.sqlite3
```

可通过 `METRICS_DB` 指定独立数据库位置。限频摘要仅在进程内存留存约 60 秒，不进入数据库。

## 验证与样例

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python scripts/verify_rendering.py
.venv/bin/python scripts/verify_browser.py
node --check static/app.js
.venv/bin/python scripts/generate_samples.py
```

浏览器验证启动自己的临时服务、使用离线模型替身，不访问第三方或历史 Key。详细结果和未验证事项见 [VERIFICATION.md](VERIFICATION.md)，任务清单见 [Task.md](Task.md)。样例脚本仅写自有样例，`static/samples/manifest.json` 含内容与渲染指纹，非用户产物。

## 来源许可
33 款主题来自 [lewislulu/html-ppt-skill](https://github.com/lewislulu/html-ppt-skill)，MIT 全文在 [licenses/html-ppt-MIT.txt](licenses/html-ppt-MIT.txt)。Inter / Noto Sans SC 来自 [Google Fonts](https://github.com/google/fonts)，OFL 在 `static/fonts/`。Noto Sans SC 自托管子集覆盖 GB2312 与常用标点，罕见汉字由系统字体回退。其余模板沿用本仓库现有作品，历史 README 曾提及 MIT 但无原始许可文件；发布前需由项目维护者确认原有作品的授权。
