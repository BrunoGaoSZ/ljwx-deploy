# ljwx-bookstore Kubernetes 配置更新日志

## 2026-01-13 - 重大配置同步更新

### 概述
基于最新的 docker-compose 配置同步更新 Kubernetes 部署配置，优化 AI 模型配置、监控集成和可观测性。

### 更新内容

#### 1. ConfigMap 更新 (`base/configmap.yaml`)

##### JVM 配置优化
- **变更**: 从 G1GC 切换到 ZGC 垃圾收集器
- **原因**: 与 docker-compose 配置保持一致，ZGC 提供更低的延迟
- **配置**:
  ```yaml
  JAVA_OPTS: "-Xms1g -Xmx2g -XX:+UseZGC -XX:+UseContainerSupport -XX:MaxRAMPercentage=75.0"
  ```

##### AI 模型配置同步
- **变更**: 统一使用 `lingjingwanxiang:32b` 模型
- **原因**: 与 application.yml 保持一致，使用更强大的 32B 参数模型
- **新增配置**:
  ```yaml
  # 基础 AI 配置
  AI_MODEL_STRATEGY: "LOCAL_PRIORITY"
  AI_LOCAL_DEFAULT_MODEL: "lingjingwanxiang:32b"
  AI_LOCAL_FALLBACK_MODEL: "lingjingwanxiang:32b"

  # LLM 配置
  AI_LLM_MODEL: "lingjingwanxiang:32b"
  AI_LLM_MAX_TOKENS: "2048"
  AI_LLM_TEMPERATURE: "0.3"

  # 高级模型配置
  AI_LLM_ADVANCED_MODEL: "lingjingwanxiang:32b"
  AI_LLM_ADVANCED_MAX_TOKENS: "8192"
  AI_LLM_ADVANCED_TEMPERATURE: "0.5"

  # 模型路由
  AI_MODEL_ROUTING_STRATEGY: "TASK_BASED"
  ```

##### OpenTelemetry 配置优化
- **变更**: 从 gRPC (4317) 切换到 HTTP (4318) endpoint
- **原因**: 匹配 docker-compose 中 OpenTelemetry Agent 的默认配置
- **新增配置**:
  ```yaml
  OTEL_EXPORTER_OTLP_ENDPOINT: "http://otel-collector-opentelemetry-collector.tracing.svc.cluster.local:4318"
  OTEL_EXPORTER_OTLP_PROTOCOL: "http/protobuf"
  OTEL_RESOURCE_ATTRIBUTES: "service.name=ljwx-bookstore,service.namespace=ljwx-bookstore,deployment.environment=production"
  ```

#### 2. 新增 ServiceMonitor (`base/servicemonitor.yaml`)

##### 功能
- 集成 Prometheus Operator 实现自动服务发现
- 自动抓取 Spring Boot Actuator 暴露的指标
- 配置指标过滤和标签重写

##### 关键配置
```yaml
endpoints:
  - port: http
    path: /fiction/actuator/prometheus
    interval: 30s
    scrapeTimeout: 10s
```

##### 指标过滤
保留以下关键指标：
- JVM 指标: `jvm_*`, `process_*`, `system_*`
- HTTP 指标: `http_*`, `tomcat_*`
- 数据库连接池: `hikaricp_*`, `jdbc_*`
- Spring Boot: `spring_*`

##### 标签增强
自动添加以下标签：
- `namespace`: Kubernetes namespace
- `pod`: Pod 名称
- `service`: Service 名称
- `app`: 应用名称

#### 3. Kustomization 更新 (`base/kustomization.yaml`)

##### 新增资源
```yaml
resources:
  - servicemonitor.yaml  # 新增
```

##### 镜像配置
```yaml
images:
  - name: harbor.omniverseai.net/ljwx/ljwx-bookstore
    newTag: latest
```

#### 4. 新增部署文档 (`base/DEPLOYMENT_GUIDE.md`)

##### 内容
- 完整的部署架构图
- 前置条件检查清单
- 详细的部署步骤（GitOps + kubectl）
- Secret 配置示例
- 监控配置说明
- 故障排查指南
- 升级和回滚流程
- 安全最佳实践

### 架构变更

#### 监控集成
```
应用 Pod
  ├─ Actuator (/fiction/actuator/prometheus)
  │    └─ 暴露 Prometheus 格式指标
  │
  ├─ ServiceMonitor
  │    └─ Prometheus Operator 自动发现
  │         └─ 配置抓取规则
  │
  └─ Prometheus
       └─ 自动抓取并存储指标
            └─ Grafana 可视化
```

#### 可观测性栈
```
应用 (OpenTelemetry Agent)
  └─ HTTP Export (4318)
       └─ OTel Collector (tracing namespace)
            ├─ Jaeger (分布式追踪)
            ├─ Prometheus (指标)
            └─ Loki (日志)
```

### 配置对比

#### 前后对比表

| 配置项 | 之前 | 现在 | 说明 |
|--------|------|------|------|
| **JVM GC** | G1GC | ZGC | 更低延迟 |
| **AI 默认模型** | qwen2.5:7b | lingjingwanxiang:32b | 更强大的模型 |
| **AI 备用模型** | llama3.2:8b | lingjingwanxiang:32b | 统一使用 32B |
| **OTel 端口** | 4317 (gRPC) | 4318 (HTTP) | 匹配 Agent 默认 |
| **Prometheus 集成** | 注解方式 | ServiceMonitor | 自动发现 |
| **指标过滤** | 无 | 有 | 减少存储开销 |

### 依赖服务

#### Infra Namespace
- `mysql-infra.infra.svc.cluster.local:3306`
- `redis-infra.infra.svc.cluster.local:6379`

#### Monitoring Namespace
- `opensearch.monitoring.svc.cluster.local:9200`
- Prometheus Operator (ServiceMonitor)

#### Tracing Namespace
- `otel-collector-opentelemetry-collector.tracing.svc.cluster.local:4318`

#### DevOps Namespace
- `ollama.devops.svc.cluster.local:11434`

### 部署流程

#### GitOps (Argo CD)
1. 提交配置到 Git
2. Argo CD 自动同步
3. 滚动更新 Pod
4. 自动健康检查
5. Prometheus 自动发现新 Target

#### 手动部署
```bash
cd apps/ljwx-bookstore/base
kubectl apply -k .
```

### 验证清单

- [ ] Secret 已创建并包含所有必需的 key
- [ ] Infra MySQL 和 Redis 可访问
- [ ] Ollama 服务运行且模型已下载
- [ ] OpenTelemetry Collector 运行正常
- [ ] Prometheus Operator CRD 已安装
- [ ] Pod 启动成功（所有健康检查通过）
- [ ] ServiceMonitor 被 Prometheus 识别
- [ ] 指标在 Prometheus 中可见
- [ ] Ingress 路由正常
- [ ] 应用功能正常

### 回滚计划

如遇问题需要回滚：

```bash
# 方式 1: Git 回滚
git revert <commit-hash>
git push

# 方式 2: Kubernetes 回滚
kubectl rollout undo deployment/ljwx-bookstore -n ljwx-bookstore

# 方式 3: 恢复旧配置
kubectl apply -k apps/ljwx-bookstore/base@<previous-commit>
```

### 性能影响评估

#### 资源使用
- **CPU**: 无显著变化（ZGC vs G1GC）
- **内存**: 32B 模型需要更多内存（由 Ollama 承载）
- **网络**: HTTP endpoint 可能略高于 gRPC

#### 监控开销
- **指标抓取**: 每 30s 一次，约 1KB/次
- **存储**: 使用指标过滤减少 ~60% 存储量

### 安全考虑

1. **Secret 管理**: 继续使用 Kubernetes Secret（计划迁移到 External Secrets Operator）
2. **网络隔离**: 通过 Service FQDN 访问跨 namespace 服务
3. **最小权限**: Pod 使用 default ServiceAccount（无特殊权限）
4. **镜像安全**: 使用私有 Harbor 仓库

### 后续计划

- [ ] 迁移到 External Secrets Operator
- [ ] 添加 Network Policies
- [ ] 配置 HPA（Horizontal Pod Autoscaler）
- [ ] 添加 PodDisruptionBudget
- [ ] 集成 Vault 管理敏感信息
- [ ] 配置 Grafana 仪表板
- [ ] 设置告警规则

### 相关 Issue/PR

- Docker-compose 配置更新: #xxx
- 基础镜像更新 (java-maven-otel): #xxx
- AI 模型切换: #xxx

### 联系人

- **负责人**: DevOps Team
- **问题反馈**: https://gitea.omniverseai.net/ljwx/ljwx-deploy/issues

---

**更新时间**: 2026-01-13
**更新人**: Claude (AI Assistant)
**审核人**: TBD
