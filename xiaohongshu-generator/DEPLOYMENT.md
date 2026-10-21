# 公网部署配置（待生产验证）

此仓库只准备配置，不执行生产发布、证书、DNS 或旧数据清理。服务目标域名：tuka.guage.chat。

## 推荐隔离环境

`Dockerfile` 使用单 Gunicorn worker、8 线程；进程内最多 2 个重请求、1 个截图。不要直接增加 worker，否则进程内限频/并发会按进程倍增。Compose 仅将后端绑定到主机 127.0.0.1:5001，应用不应直接暴露公网。

`compose.yaml` 配置只读根目录、非 root 用户、内存 `/tmp`（512 MiB）、禁 core dump、移除 capability、2 GiB 内存/2 CPU/256 PID 上限。Chromium profile 位于临时盘，成功/异常均关闭上下文；用户 HTML、截图均不写文件。统计是唯一可写持久卷 `/data`。内存数据仍可能受主机 swap、休眠、崩溃转储和基础设施观测影响，部署主机需关闭 swap/core dump、禁用请求体采集/APM/录屏。资源限额需在真实 Linux 机器压测后校准。

准备部署时的命令（本任务未执行）：

```bash
docker compose build
docker compose up -d
docker compose exec tuka python metrics.py --db /data/metrics.sqlite3
```

构建上下文白名单排除旧 Key、日志、输入、output、开发工具痕迹。不要把整个项目根目录挂成静态目录；应用无全局配置接口、无磁盘产物下载接口。

## HTTPS 反向代理

`deploy/nginx.conf` 为 nginx `http {}` 内的配置片段。证书应由维护者预先提供，路径为 `/etc/letsencrypt/live/tuka.guage.chat/`，本任务不签发证书或改 DNS。

代理关闭访问日志、内容缓存、请求/响应缓冲与临时响应文件；备用请求临时目录指向 Linux `/dev/shm`。需预先创建 `/dev/shm/tuka-body`、`/dev/shm/tuka-proxy` 并赋 nginx 用户写权限，重启后重建。检查前置 CDN/WAF/负载均衡器同样不记录正文或 Key、不缓存页面/API、不缓冲至磁盘。

代理覆盖 X-Forwarded-For/Proto；容器以 `TRUST_LOCAL_PROXY=1` 信任这一层。必须阻止绕过代理的外部请求，否则可伪造转发地址绕过进程内限频。边缘限频不持久保存 IP，仅用 nginx 内存 zone；后端只用随机盐摘要、约 60 秒保留，统计无 IP/身份字段。

外部模型/图片请求只允许公网 HTTPS 443，解析全部地址，拒绝内网/元数据/映射地址，实际 socket 固定到校验 IP，TLS 校验原主机名，不用环境代理、不跟重定向。生产还应通过网络策略阻断内网和元数据出口，作为容器外的防线；不承诺抵御服务器自身被攻破。

## 上线前门禁

1. 工程测试和浏览器检查完成；专用测试 Key 验证两协议真实调用，不使用历史 Key。
2. Linux 镜像构建、Chromium、内存临时盘、并发/超时清理、磁盘无用户残留、限频和反代配置通过验证。
3. 确认字体/主题与原有模板许可，确认统计说明和数据边界。
4. 获得生产发布授权后再配置证书、DNS 和上线；验证 HTTPS、日志、缓存与实际访问。

当前证据与未验证项见 [VERIFICATION.md](VERIFICATION.md)。统计默认保留 90 天，写入时清理过期数据；无新事件时本地只读报告仍只展示最近 90 天，但物理记录将在下一次写入时清除。

## 国产厂商出口

第一期只向五家固定国内接口发送模型凭据：`api.deepseek.com`、`api.minimax.cn`、`api.moonshot.cn`、`open.bigmodel.cn`、`ark.cn-beijing.volces.com`，均为 HTTPS 443。无需访问 OpenAI/Anthropic 海外 API；两者仅是兼容协议名称。`POST /api/models` 与生成接口采用相同写入限频。部署时应逐个验证本机 DNS、TLS、网络连通和专用 Key；不能据官方文档或本地离线测试声称生产网络已通。用户 Markdown 配图仍可能指向其他公网 HTTPS 服务，不携带模型 Key，受同样 SSRF 和超时限制。

模型清单、接口差异和标准按量 Key 范围见 [PROVIDERS.md](PROVIDERS.md)。
