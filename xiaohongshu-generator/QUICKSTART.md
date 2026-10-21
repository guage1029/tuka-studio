# 快速启动

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m playwright install chromium
.venv/bin/python app.py
```

打开 http://127.0.0.1:5001/app

选择国产厂商、填入自己的开放平台 API Key，点击“刷新模型列表”并从下拉框选择模型，再粘贴至少 50 字内容。生成文案后编辑确认，再渲染下载。配置仅当前页面内存有效，刷新清空。旧 `config.py`、`ai_config.json` 不再使用。公网部署必须先阅读 [DEPLOYMENT.md](DEPLOYMENT.md)。

DeepSeek/Kimi 实时查询；MiniMax/智谱/豆包使用注明日期的官方预置目录，Key 和权限在生成时校验。无需填写协议或地址。范围见 [PROVIDERS.md](PROVIDERS.md)。
