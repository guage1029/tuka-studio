# 图卡工作台 TUKA Studio

把长文章整理成可编辑、可下载的小红书图卡。服务在本机运行，使用时在网页中填写你自己的模型 API Key。

## 快速启动

需要 Python 3.11 或更新版本。下载 GitHub 源码 ZIP 并解压后，打开终端进入 `tuka-studio` 目录，运行：

```bash
./start.sh
```

脚本会创建虚拟环境、安装 Python 依赖和 Chromium，然后启动服务。首次安装需要网络连接。Windows 用户运行 `start.bat`。

启动后打开 <http://127.0.0.1:5001/>，进入工作台，选择模型服务商并填写自己的 API Key 即可开始使用。无需创建配置文件或把 Key 写进代码。

也可以手动启动：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m playwright install chromium
.venv/bin/python app.py
```

公网部署前请阅读 [`DEPLOYMENT.md`](tuka-studio/DEPLOYMENT.md)；模型服务支持范围见 [`PROVIDERS.md`](tuka-studio/PROVIDERS.md)。
