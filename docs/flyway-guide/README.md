# Flyway 数据库版本化规范

## 📋 概述

Flyway 是数据库迁移管理工具，用于：
- 版本化数据库 Schema
- 自动化数据库升级
- 跟踪迁移历史
- 支持回滚（通过向后兼容设计）

**核心原则：**
- ✅ 所有 Schema 变更必须通过 Flyway
- ✅ 迁移必须向后兼容（支持新旧代码共存）
- ✅ 禁止直接修改数据库
- ✅ 每个迁移都有明确的版本号

---

## 📁 标准目录结构

### 项目中的位置

```
youngth-guard/
└── backend-fastapi/
    └── migrations/           # Flyway 迁移目录
        ├── V1__initial_schema.sql
        ├── V2__add_users_table.sql
        ├── V3__add_email_column.sql
        ├── V4__add_email_index.sql
        └── V5__remove_deprecated_column.sql
```

### 多模块项目

```
project-root/
├── service-a/
│   └── migrations/
│       ├── V1__service_a_init.sql
│       └── V2__service_a_update.sql
└── service-b/
    └── migrations/
        ├── V1__service_b_init.sql
        └── V2__service_b_update.sql
```

**注意：** 每个服务使用独立的数据库，因此版本号独立管理。

---

## 🏷️ 命名规范

### 文件命名格式

```
V{version}__{description}.sql
```

**规则：**

1. **V（大写）** - 固定前缀，表示 Versioned migration
2. **{version}** - 版本号，格式：
   - 单数字：`V1`, `V2`, `V3` ...
   - 点分版本：`V1.1`, `V1.2`, `V2.1` ...
   - 时间戳：`V20251218101500` (不推荐，难以理解)
3. **__（双下划线）** - 分隔符
4. **{description}** - 描述，使用下划线分隔单词
5. **.sql** - 文件扩展名

### 正确示例

```
✅ V1__initial_schema.sql
✅ V2__add_users_table.sql
✅ V3__add_email_column.sql
✅ V4__migrate_old_data.sql
✅ V5__add_index_on_email.sql
✅ V6__remove_deprecated_field.sql
✅ V1.1__hotfix_user_constraint.sql
```

### 错误示例

```
❌ v1__initial.sql                  # 小写 v
❌ V1_initial_schema.sql            # 单下划线
❌ 1__initial_schema.sql            # 缺少 V
❌ V1-initial-schema.sql            # 使用连字符
❌ V1__Initial Schema.sql           # 包含空格
❌ V1__添加用户表.sql                # 非 ASCII 字符
```

---

## 📝 迁移内容规范

### 每个迁移文件应该

- ✅ 完成一个独立的功能
- ✅ 包含清晰的注释
- ✅ 幂等（使用 `IF NOT EXISTS` / `IF EXISTS`）
- ✅ 可逆（通过后续迁移回滚）
- ✅ 测试过（在本地和测试环境）

### 迁移文件模板

```sql
-- ============================================
-- Migration: V{version}__{description}
-- Author: {your-name}
-- Date: {date}
-- Description:
--   {详细描述这个迁移做什么}
--   {为什么需要这个变更}
-- ============================================

-- 开始事务（可选，Flyway 默认会包裹在事务中）
BEGIN;

-- 你的 SQL 语句
-- ...

-- 提交
COMMIT;
```

---

## 🔄 Expand/Contract 模式

**Expand/Contract** 是实现零停机升级的关键模式。

### 模式说明

1. **Expand（扩展）** - 添加新结构，保留旧结构
2. **Deploy（部署）** - 部署新代码，同时支持新旧结构
3. **Contract（收缩）** - 删除旧结构

### 示例：添加新列并重命名

**场景：** 将 `users.name` 列重命名为 `users.full_name`

#### ❌ 错误做法（会导致停机）

```sql
-- V2__rename_column.sql
ALTER TABLE users RENAME COLUMN name TO full_name;
```

**问题：** 旧代码仍在使用 `name` 列，会立即报错。

#### ✅ 正确做法（Expand/Contract）

**Step 1: Expand - 添加新列**

```sql
-- V2__add_full_name_column.sql
-- Expand: 添加新列，保留旧列
ALTER TABLE users ADD COLUMN IF NOT EXISTS full_name VARCHAR(255);

-- 复制数据到新列
UPDATE users SET full_name = name WHERE full_name IS NULL;

-- 创建触发器保持同步（可选）
CREATE OR REPLACE FUNCTION sync_user_name()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.name IS DISTINCT FROM OLD.name THEN
        NEW.full_name := NEW.name;
    END IF;
    IF NEW.full_name IS DISTINCT FROM OLD.full_name THEN
        NEW.name := NEW.full_name;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER sync_user_name_trigger
BEFORE UPDATE ON users
FOR EACH ROW
EXECUTE FUNCTION sync_user_name();
```

**Step 2: Deploy - 部署新代码**

应用代码更新为使用 `full_name`，但数据库同时支持两列。

**Step 3: Contract - 删除旧列**

```sql
-- V3__remove_name_column.sql
-- Contract: 删除旧列（确认新代码已稳定运行）

-- 删除触发器
DROP TRIGGER IF EXISTS sync_user_name_trigger ON users;
DROP FUNCTION IF EXISTS sync_user_name();

-- 删除旧列
ALTER TABLE users DROP COLUMN IF EXISTS name;
```

---

## 🚫 禁止使用的 SQL

以下 SQL 操作**禁止**直接在 Flyway 迁移中使用：

### 1. 破坏性操作（生产环境）

```sql
-- ❌ 禁止：直接删除表
DROP TABLE users;

-- ✅ 推荐：重命名表为 _deprecated，稍后删除
ALTER TABLE users RENAME TO users_deprecated_20251218;
-- 在后续迁移中删除：
-- DROP TABLE IF EXISTS users_deprecated_20251218;
```

### 2. 直接删除列（无过渡期）

```sql
-- ❌ 禁止：直接删除列
ALTER TABLE users DROP COLUMN email;

-- ✅ 推荐：使用 Expand/Contract
-- V2: 标记为废弃（添加注释）
-- V3: 应用不再使用
-- V4: 删除列
```

### 3. 修改列类型（无向后兼容）

```sql
-- ❌ 禁止：直接修改类型
ALTER TABLE users ALTER COLUMN age TYPE INTEGER;

-- ✅ 推荐：
-- V2: 添加新列 age_int
-- V3: 迁移数据
-- V4: 应用使用新列
-- V5: 删除旧列
```

### 4. 添加 NOT NULL 约束（无默认值）

```sql
-- ❌ 禁止：直接添加 NOT NULL
ALTER TABLE users ALTER COLUMN email SET NOT NULL;

-- ✅ 推荐：
-- V2: 添加列（允许 NULL）
-- V3: 填充数据
-- V4: 添加 NOT NULL 约束
```

### 5. 删除索引（无影响评估）

```sql
-- ❌ 禁止：直接删除索引
DROP INDEX idx_users_email;

-- ✅ 推荐：
-- 1. 评估性能影响
-- 2. 在低峰期执行
-- 3. 监控查询性能
-- 4. 准备回滚计划
```

### 6. 大规模数据更新

```sql
-- ❌ 禁止：一次性更新所有数据
UPDATE users SET status = 'active';

-- ✅ 推荐：批量更新
DO $$
DECLARE
    batch_size INT := 1000;
    total_rows INT;
BEGIN
    LOOP
        UPDATE users
        SET status = 'active'
        WHERE id IN (
            SELECT id FROM users
            WHERE status IS NULL
            LIMIT batch_size
        );

        GET DIAGNOSTICS total_rows = ROW_COUNT;
        EXIT WHEN total_rows = 0;

        PERFORM pg_sleep(0.1); -- 避免长时间锁表
    END LOOP;
END $$;
```

---

## 📚 迁移示例

### 示例 1：初始化 Schema

```sql
-- V1__initial_schema.sql
-- ============================================
-- 初始化数据库 Schema
-- ============================================

-- 用户表
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) NOT NULL UNIQUE,
    email VARCHAR(255) NOT NULL UNIQUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_created_at ON users(created_at);

-- 评估记录表
CREATE TABLE IF NOT EXISTS assessments (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    score INTEGER NOT NULL CHECK (score >= 0 AND score <= 100),
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_assessments_user_id ON assessments(user_id);
CREATE INDEX IF NOT EXISTS idx_assessments_status ON assessments(status);
CREATE INDEX IF NOT EXISTS idx_assessments_created_at ON assessments(created_at);

-- 审计日志表
CREATE TABLE IF NOT EXISTS audit_logs (
    id BIGSERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    action VARCHAR(50) NOT NULL,
    entity_type VARCHAR(50) NOT NULL,
    entity_id INTEGER,
    changes JSONB,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_audit_logs_user_id ON audit_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_created_at ON audit_logs(created_at);
CREATE INDEX IF NOT EXISTS idx_audit_logs_entity ON audit_logs(entity_type, entity_id);

COMMENT ON TABLE users IS '用户表';
COMMENT ON TABLE assessments IS '心理评估记录表';
COMMENT ON TABLE audit_logs IS '审计日志表';
```

### 示例 2：添加新列（Expand）

```sql
-- V2__add_phone_column.sql
-- ============================================
-- 添加手机号列
-- 使用 Expand 模式，保证向后兼容
-- ============================================

-- 添加列（允许 NULL）
ALTER TABLE users ADD COLUMN IF NOT EXISTS phone VARCHAR(20);

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_users_phone ON users(phone) WHERE phone IS NOT NULL;

-- 添加注释
COMMENT ON COLUMN users.phone IS '用户手机号（可选）';
```

### 示例 3：数据迁移（Expand/Contract - Part 1）

```sql
-- V3__add_profile_data_column.sql
-- ============================================
-- 添加 profile_data JSON 列
-- 准备将结构化数据迁移到 JSON
-- ============================================

-- Expand: 添加新列
ALTER TABLE users ADD COLUMN IF NOT EXISTS profile_data JSONB DEFAULT '{}'::jsonb;

-- 迁移现有数据
UPDATE users
SET profile_data = jsonb_build_object(
    'email', email,
    'phone', COALESCE(phone, ''),
    'created_at', created_at::text
)
WHERE profile_data = '{}'::jsonb;

-- 创建 GIN 索引支持 JSON 查询
CREATE INDEX IF NOT EXISTS idx_users_profile_data ON users USING GIN (profile_data);

-- 注意：此时 email 和 phone 列仍然存在
-- 应用代码需要逐步迁移到使用 profile_data
```

### 示例 4：删除旧列（Expand/Contract - Part 2）

```sql
-- V4__remove_old_profile_columns.sql
-- ============================================
-- 删除已迁移到 JSON 的旧列
-- 前提：应用代码已完全切换到 profile_data
-- ============================================

-- Contract: 删除旧列
-- 注意：执行前确认应用已不再使用这些列

-- 先删除依赖的索引
DROP INDEX IF EXISTS idx_users_email;
DROP INDEX IF EXISTS idx_users_phone;

-- 删除列
-- ALTER TABLE users DROP COLUMN IF EXISTS email;    -- 保留 email 作为主要联系方式
ALTER TABLE users DROP COLUMN IF EXISTS phone;

COMMENT ON COLUMN users.profile_data IS '用户扩展信息（JSON 格式）';
```

### 示例 5：添加约束

```sql
-- V5__add_user_status_constraint.sql
-- ============================================
-- 添加用户状态列和约束
-- ============================================

-- 添加状态列
ALTER TABLE users ADD COLUMN IF NOT EXISTS status VARCHAR(20) DEFAULT 'active';

-- 填充现有数据
UPDATE users SET status = 'active' WHERE status IS NULL;

-- 添加 CHECK 约束
ALTER TABLE users ADD CONSTRAINT check_user_status
    CHECK (status IN ('active', 'inactive', 'suspended', 'deleted'));

-- 添加索引
CREATE INDEX IF NOT EXISTS idx_users_status ON users(status);

COMMENT ON COLUMN users.status IS '用户状态：active|inactive|suspended|deleted';
```

---

## ✅ 最佳实践 Checklist

### 编写迁移前

- [ ] 确认变更的业务需求
- [ ] 设计向后兼容的方案
- [ ] 评估对现有代码的影响
- [ ] 考虑回滚策略
- [ ] 评估性能影响（特别是大表操作）

### 编写迁移时

- [ ] 使用正确的命名格式
- [ ] 添加清晰的注释
- [ ] 使用 `IF EXISTS` / `IF NOT EXISTS`
- [ ] 遵循 Expand/Contract 模式
- [ ] 避免大规模数据更新（或使用批量处理）
- [ ] 添加适当的索引

### 测试迁移

- [ ] 在本地数据库测试
- [ ] 在测试环境验证
- [ ] 验证旧代码仍能运行
- [ ] 验证新代码正常工作
- [ ] 检查性能影响
- [ ] 准备回滚迁移

### 部署迁移

- [ ] 在低峰期执行
- [ ] 备份数据库
- [ ] 监控执行进度
- [ ] 验证应用功能
- [ ] 准备紧急回滚

---

## 🔍 故障排查

### 问题 1：迁移失败

```bash
# 查看 Flyway 历史
SELECT * FROM flyway_schema_history ORDER BY installed_rank DESC LIMIT 10;

# 查看失败的迁移
SELECT * FROM flyway_schema_history WHERE success = false;
```

**解决方案：**
1. 检查错误日志
2. 手动修复数据库状态
3. 标记迁移为已解决：
   ```sql
   UPDATE flyway_schema_history
   SET success = true
   WHERE version = 'X' AND success = false;
   ```

### 问题 2：需要跳过某个迁移

**不推荐！** 但紧急情况下：

```sql
-- 手动标记迁移为已执行
INSERT INTO flyway_schema_history (
    installed_rank, version, description, type, script, checksum,
    installed_by, installed_on, execution_time, success
) VALUES (
    (SELECT COALESCE(MAX(installed_rank), 0) + 1 FROM flyway_schema_history),
    '5', 'skip_this_migration', 'SQL', 'V5__skip_this.sql', NULL,
    'admin', NOW(), 0, true
);
```

### 问题 3：迁移顺序错误

**原因：** 版本号不连续或重复

**解决：**
- 使用点分版本：`V2.1`, `V2.2`
- 或重命名文件（未执行的迁移）

---

## 📖 相关文档

- Flyway 官方文档：https://flywaydb.org/documentation/
- 本平台相关：
  - `docs/architecture-overview.md` - 平台架构
  - `docs/db-isolation-spec.md` - 数据库隔离规范
  - `infra/postgres/README.md` - Postgres 部署
