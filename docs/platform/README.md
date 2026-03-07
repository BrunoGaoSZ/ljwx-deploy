# Platform Blueprint

本目录用于沉淀 `ljwx-deploy` 作为平台集成仓时的装配规则、边界和执行方式。

原则：

1. `ljwx-deploy` 仍然是唯一部署真相源。
2. `apps/`、`argocd-apps/`、`cluster/` 负责实际交付对象。
3. `platform/` 负责平台级配置、契约、路由、知识治理和环境矩阵。
4. 运行时行为必须能回溯到 Git 中的版本、策略、知识和能力契约。

建议阅读顺序：

1. `architecture-overview.md`
2. `component-responsibilities.md`
3. `platform-repo-design.md`
4. `routing-strategy.md`
5. `knowledge-pipeline.md`
6. `capability-gateway.md`
7. `observability-contract.md`
8. `deployment-environments.md`
9. `bootstrap-and-migration.md`
10. `engineering-execution-guide.md`
11. `github-project-plan.md`
