# ljwx-bookstore DNS 配置指南

## 域名信息

- **生产域名**: `bookstore.lingjingwanxiang.cn`
- **入口控制器**: Traefik
- **SSL证书**: Let's Encrypt (自动通过 cert-manager 获取)

## DNS记录配置

### 步骤1: 配置域名解析

将 `bookstore.lingjingwanxiang.cn` 解析到 k3s 对外入口 IP。

### 步骤2: 添加 A 记录

需要添加以下DNS记录：

| 类型 | 名称 | 内容 | 代理状态 | TTL |
|------|------|------|----------|-----|
| A | bookstore | `<INGRESS_IP>` | 仅DNS | Auto |

**获取 Ingress IP**:
```bash
kubectl get ingress ljwx-bookstore -n ljwx-bookstore \
  -o jsonpath='{.status.loadBalancer.ingress[0].ip}'
```

**当前 Ingress IP**:
```bash
# 从集群中获取
192.168.194.177  # 示例，请使用实际IP
```

### 步骤3: HTTPS 配置建议

#### SSL/TLS 设置
1. 进入 `SSL/TLS` → `概述`
2. 加密模式选择: **完全（严格）** 或 **完全**
3. 推荐: **完全（严格）** - 确保端到端加密

#### 其他推荐配置
- DNS 记录生效前不要切换业务入口
- 保证 `bookstore.lingjingwanxiang.cn` 已解析到 Traefik 对外 IP
- 配置 **最小TLS版本**: TLS 1.2

## 验证步骤

### 1. DNS解析验证

```bash
# 检查DNS记录
dig bookstore.lingjingwanxiang.cn +short

# 或使用nslookup
nslookup bookstore.lingjingwanxiang.cn
```

**期望输出**: 应该返回Ingress Controller的IP地址

### 2. SSL证书验证

等待2-5分钟，cert-manager会自动申请证书：

```bash
# 检查Certificate资源
kubectl get certificate -n ljwx-bookstore

# 查看证书详情
kubectl describe certificate bookstore-lingjingwanxiang-cn-tls -n ljwx-bookstore

# 检查证书Secret
kubectl get secret bookstore-lingjingwanxiang-cn-tls -n ljwx-bookstore
```

**期望状态**: `READY=True`

### 3. 访问测试

```bash
# HTTP 自动重定向到 HTTPS
curl -I http://bookstore.lingjingwanxiang.cn

# HTTPS 访问
curl -I https://bookstore.lingjingwanxiang.cn

# 浏览器访问
open https://bookstore.lingjingwanxiang.cn/fiction/index
```

### 4. SSL证书检查

```bash
# 使用 openssl 检查证书
echo | openssl s_client -servername bookstore.lingjingwanxiang.cn \
  -connect bookstore.lingjingwanxiang.cn:443 2>/dev/null | \
  openssl x509 -noout -dates -subject

# 在线检查
# 访问 https://www.ssllabs.com/ssltest/
# 输入: bookstore.lingjingwanxiang.cn
```

## 故障排查

### DNS未解析

```bash
# 检查 DNS 设置
# 1. 确认A记录存在
# 2. 确认IP地址正确
# 3. 清除本地DNS缓存: sudo dscacheutil -flushcache (macOS)
```

### 证书未自动生成

```bash
# 检查 cert-manager 日志
kubectl logs -n cert-manager -l app=cert-manager --tail=50

# 检查 Certificate Events
kubectl describe certificate bookstore-lingjingwanxiang-cn-tls -n ljwx-bookstore

# 检查 CertificateRequest
kubectl get certificaterequest -n ljwx-bookstore
kubectl describe certificaterequest -n ljwx-bookstore

# 常见问题:
# 1. DNS记录配置错误
# 2. ClusterIssuer配置问题
# 3. Traefik 未接住 HTTP01 challenge
```

### HTTPS访问失败

```bash
# 检查 Ingress 状态
kubectl get ingress ljwx-bookstore -n ljwx-bookstore
kubectl describe ingress ljwx-bookstore -n ljwx-bookstore

# 检查 Traefik 日志
kubectl logs -n kube-system -l app.kubernetes.io/name=traefik --tail=50
```

## 生产环境清单

部署到生产环境前，确认以下事项：

- [ ] DNS A记录已添加并解析正确
- [ ] SSL证书自动获取成功（`kubectl get certificate -n ljwx-bookstore`）
- [ ] HTTPS强制重定向已启用
- [ ] 健康检查正常工作
- [ ] 应用可通过 https://bookstore.lingjingwanxiang.cn 访问
- [ ] SSL证书A级评分（ssllabs.com测试）
- [ ] 监控和告警已设置（可选）

## 相关资源

- Ingress配置: `ingress.yaml`
- cert-manager文档: https://cert-manager.io/docs/
- Let's Encrypt文档: https://letsencrypt.org/docs/

## 更新历史

- 2026-03-06: 切换到 bookstore.lingjingwanxiang.cn，并统一到 Traefik + cert-manager 基线
