# 伪装页（decoy）

`src/wshell/payloads/decoys/*.html` 从 XG_NTAI 的 WAF 页面模板中提取，仅用于授权测试时的响应伪装。

| 文件 | 来源类 | 用途 |
| --- | --- | --- |
| aliyun.html | AliyunWAF | 阿里云 WAF 拦截页 |
| anyu.html | AnyuWAF | 安域 WAF |
| safedog.html | SafedogWAF | 安全狗拦截页 |
| safeline.html | SafeLineWAF | 长亭雷池 |
| tmshen.html | TmshenWAF | 天懋 |
| tsec.html | TsecWAF | 腾讯云 |
| wangsu.html | WangsuWAF | 网宿 403 |

## 用法

```bash
uv run webshell-mag --generate shell.php --decoy-preset aliyun
uv run webshell-mag --generate shell.php --decoy ./my404.html
```

无有效加密请求时返回该页面，HTTP 405；有效请求仍走正常加密响应。

注意：这些页面可能引用外部 CDN 资源（图片/JS），离线环境会显示不完整，但不影响伪装逻辑。
