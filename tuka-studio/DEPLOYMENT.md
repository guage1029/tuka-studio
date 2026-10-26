# 生产部署

当前生产站点：<https://tuka.guage.chat>。当前 release 为 `tuka-preview-hint-20261025-r1`（基于 `tuka-render-performance-20261025-r1`），采用 Ubuntu 主机直接部署，不使用容器。

## 主机布局

- 应用发布目录：`/var/www/tuka/releases/<release>`；`/var/www/tuka/current` 指向当前版本。
- 持久数据：`/var/www/tuka/shared/metrics.sqlite3`；虚拟环境和 Playwright 浏览器也位于 `shared/`。
- ACME HTTP-01 webroot：`/var/www/tuka/acme`。
- 专用系统用户：`tuka`；Gunicorn 仅监听 `127.0.0.1:5001`。
- systemd unit：`/etc/systemd/system/tuka.service`。
- Nginx vhost：`/etc/nginx/sites-available/tuka`，启用链接在 `sites-enabled/`；限速 zone 在 `/etc/nginx/conf.d/tuka-limits.conf`。
- `/dev/shm/tuka-body` 与 `/dev/shm/tuka-proxy` 由 `/etc/tmpfiles.d/tuka.conf` 在启动时创建。

服务使用 Python 3.12、Gunicorn 单 worker/8 线程；systemd 将服务 MemoryHigh 设为 infinity、MemoryMax 设为 640 MiB，禁用 swap，并限制 CPU 和进程数。不要增加 worker：并发与限频状态按进程隔离。统计 SQLite 是应用唯一的持久写入；用户正文、Key 和渲染图片不保存到磁盘。

统计库中的 90 天事件明细会滚动清理；`lifetime` 汇总和匿名浏览器摘要不设过期时间。备份或迁移时必须整体保留 `shared/metrics.sqlite3`，否则永久累计和去重记录会丢失。

## TLS 与续签

证书由 Certbot 使用 HTTP-01 webroot 签发，证书位于 `/etc/letsencrypt/live/tuka.guage.chat/`。`certbot.timer` 负责自动续签；专用 deploy hook `/etc/letsencrypt/renewal-hooks/deploy/tuka-reload-nginx` 仅在该证书续签时先运行 `nginx -t` 再 graceful reload。模拟续签及 hook 已验证通过。

## 发布与回滚

发布时创建新的不可变 release，先在其中创建/复用 Python 3.12 虚拟环境并安装锁定依赖、准备 Playwright headless shell，然后更新 `current` symlink，执行 `systemctl restart tuka` 并验证本机健康与公网 HTTPS。Nginx 配置变更前备份对应文件，运行 `nginx -t` 后只用 `systemctl reload nginx`。

回滚时将 `current` 指回上一 release，再 `systemctl restart tuka`。不要回滚或覆盖 `shared/metrics.sqlite3`。变更 systemd、Nginx 或证书后分别验证 `systemctl status tuka`, `nginx -t`, `certbot renew --dry-run --run-deploy-hooks --no-random-sleep-on-renew --cert-name tuka.guage.chat`。

部署时未重启其他 Web 应用或 MongoDB；仅对 Nginx 做 graceful reload。部署记录和当次验证见 [VERIFICATION.md](VERIFICATION.md)。

## 安全与限制

应用仅信任指定 Host，通过本机 Nginx 反代接收流量。Nginx 关闭站点访问日志、缓存与请求/响应磁盘缓冲，临时请求体和代理文件目录位于 `/dev/shm`。页面读取与写操作保留边缘限速；`/static/` 使用独立并发上限，避免展开样式图库时图片请求被页面读取限速拒绝。

上线前已通过本地 45 项单元测试、Playwright headless shell 截图 smoke test、2 张及 8 张卡片的真实渲染和部署后 HTTPS 检查。未使用专用真实厂商 API Key 执行付费模型调用；部署成功不代表每家厂商出口或账户权限均已验证。真实生产模型调用仍受 Key、余额、厂商账户权限和服务状态影响。

模型出口清单和调用差异见 [PROVIDERS.md](PROVIDERS.md)。


## 带图截图资源与响应压缩（2026-10-25，已发布）

- 当前release：`/var/www/tuka/releases/tuka-render-performance-20261025-r1`，上一版本`/var/www/tuka/releases/tuka-style-gallery-20261025-r2`保留可回滚。
- 仅增量更新`app.py`，并新增独立systemd drop-in `/etc/systemd/system/tuka.service.d/50-render-memory.conf`。无依赖变化、数据库变更或全量上传。
- 当前限制：`MemoryHigh=infinity`、`MemoryMax=640M`、`MemorySwapMax=0`、`CPUQuota=100%`、`TasksMax=128`。硬上限比原值增加128 MiB；其他应用和Nginx/MongoDB均未重启。
- 响应gzip只作用于支持压缩且响应变小的成功渲染JSON，PNG内容和接口字段不变；不支持gzip或`q=0`仍按原格式返回。
- 回滚：将`/var/www/tuka/current`原子切回`/var/www/tuka/releases/tuka-style-gallery-20261025-r2`；确认drop-in内容仍为本次配置后删除`50-render-memory.conf`，执行`systemctl daemon-reload`并仅重启tuka。不要覆盖`shared/metrics.sqlite3`或其他drop-in。
- 实测：生产本机用合成配图各渲染8张`ppt-glassmorphism`及`ppt-blueprint`，返回200且图片数正确，分别6.94秒与3.45秒；响应均为gzip且可正常解压。公网`/render`合成2卡返回200、gzip可解压、1.14 MB传输，6.17秒；公网`/app`返回200。
- systemd当前`NRestarts=0`，本次截图后服务峰值610861056字节（约582.5 MiB），当前可用内存约1050 MiB，`memory.events`中high/max/oom均为0。改动没有提高云实例或其他应用额度。
- 本次首次切换尝试因只创建了新目录而未复制完整release，Gunicorn报`No module named 'ai_providers'`；已自动回切并恢复旧资源配置。随后按完整release复制流程重新部署，生产健康检查通过；服务目前运行在新release。
- 测试内容是合成文字/图片，不含用户正文、Key或配图。8张复杂大图通过gzip后的响应仍约4.2 MiB；公网带宽仍会影响等待，不能保证复杂8卡在2–3秒内完成。真实用户素材和高并发峰值未验证。
