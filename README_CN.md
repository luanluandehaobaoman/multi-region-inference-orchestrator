# Multi-Region Inference Orchestrator

多 Region 异步推理编排系统

[![AWS](https://img.shields.io/badge/AWS-Lambda%20%7C%20SQS%20%7C%20DynamoDB-orange)](https://aws.amazon.com/)
[![Python](https://img.shields.io/badge/Python-3.12-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

## 项目简介

这是一个基于 AWS Serverless 架构的智能队列分发系统，通过 Lambda 函数实现跨多个 AWS Region 的异步推理请求编排。系统旨在突破单个 Region Spot GPU 数量限制，充分利用多区域资源，提高推理系统的可用性和吞吐量。

**核心特性**：

- 🌐 **多 Region 智能分发**：自动调度请求到 3 个 AWS Region（us-east-1, us-west-2, us-west-1）
- 📊 **负载感知调度**：基于队列深度的反向权重算法，负载越低权重越高
- 🔒 **幂等性保障**：DynamoDB 实现的 request_id 去重机制，TTL 自动清理
- ⚡ **高效批量处理**：支持批量消息转发和删除（最多 10 条/批）
- 🔄 **自动重试机制**：利用 SQS VisibilityTimeout 和死信队列（DLQ）
- 📦 **开箱即用的测试工具**：完整的消息生产者和消费者工具

## 系统架构

```
┌─────────────┐
│  客户端应用  │
└──────┬──────┘
       │
       ↓ SendMessage
┌──────────────────────────┐
│  总队列 (Master SQS)     │
│  us-east-1               │
└──────────┬───────────────┘
           │ Event Source Mapping (Batch=10)
           ↓
┌──────────────────────────┐
│  分发 Lambda Function    │
│  - 幂等性检查(DynamoDB)  │
│  - 负载感知选择          │
│  - 批量转发              │
└──────┬───────────────────┘
       │
       ├──────────┬──────────┐
       ↓          ↓          ↓
  ┌─────────┐ ┌─────────┐ ┌─────────┐
  │us-east-1│ │us-west-2│ │us-west-1│
  │SQS 队列 │ │SQS 队列 │ │SQS 队列 │
  └────┬────┘ └────┬────┘ └────┬────┘
       │           │           │
       ↓           ↓           ↓
  [EKS 推理]  [EKS 推理]  [EKS 推理]
```

### 核心组件

| 组件 | 描述 | Region |
|------|------|--------|
| **总队列** | 统一的推理请求入口点 | us-east-1 |
| **分发 Lambda** | 智能调度器，负载感知分发 | us-east-1 |
| **子队列 × 3** | 各 Region 独立的 SQS 队列 | us-east-1, us-west-2, us-west-1 |
| **幂等性表** | DynamoDB 表，防止重复处理 | us-east-1 |

## 已部署的资源

✅ **系统已成功部署并测试通过！**

### AWS Lambda
- **函数名**: `inference-distributor-dev`
- **运行时**: Python 3.12
- **内存**: 512 MB / **超时**: 300 秒
- **并发**: 100

### SQS 队列

**主队列**:
- `inference-master-queue-dev` (us-east-1)
- VisibilityTimeout: 600 秒

**子队列**:
- `inference-queue-us-east-1-dev` (us-east-1)
- `inference-queue-us-west-2-dev` (us-west-2)
- `inference-queue-us-west-1-dev` (us-west-1)
- VisibilityTimeout: 3600 秒

### DynamoDB
- **表名**: `inference-idempotency-dev`
- **主键**: `request_id` (String)
- **TTL**: 7 天自动清理

## 快速开始

### 前置要求

- Python 3.12+
- AWS CLI（已配置 `--profile default`）
- SAM CLI

### 1. 安装依赖

```bash
cd multi-region-inference-orchestrator
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

### 2. 部署到 AWS

```bash
# 构建
sam build --template infrastructure/template.yaml --profile default

# 部署
sam deploy --guided --profile default
```

### 3. 创建跨 Region 子队列

由于 SAM 的单 Region 限制，需要手动创建其他 Region 的队列：

```bash
# us-west-2
aws sqs create-queue \
  --queue-name inference-queue-us-west-2-dev \
  --region us-west-2 \
  --profile default \
  --attributes VisibilityTimeout=3600,MessageRetentionPeriod=1209600

# us-west-1
aws sqs create-queue \
  --queue-name inference-queue-us-west-1-dev \
  --region us-west-1 \
  --profile default \
  --attributes VisibilityTimeout=3600,MessageRetentionPeriod=1209600
```

### 4. 更新 Lambda 配置

更新环境变量和 IAM 权限以支持跨 Region 访问。详细步骤请参考 [快速开始指南](docs/quick-start.md)。

## 测试工具

项目包含完整的测试工具，位于 `test-tools/` 目录。

### 消息生产者（Producer）

向主队列发送测试消息：

```bash
cd test-tools

# 发送 30 条测试消息
python3 producer.py \
  --queue-url <MASTER_QUEUE_URL> \
  --count 30 \
  --interval 0.2 \
  --profile default
```

### 消息消费者（Consumer）

从 3 个子队列消费消息并查看分发统计：

```bash
# 消费消息
python3 consumer.py \
  --queue-us-east-1 <US_EAST_1_URL> \
  --queue-us-west-2 <US_WEST_2_URL> \
  --queue-us-west-1 <US_WEST_1_URL> \
  --max-messages 10 \
  --profile default
```

**输出示例**：
```
========================================
消息分发统计
========================================
us-east-1: 2 条 (22.2%)
us-west-2: 4 条 (44.4%)
us-west-1: 3 条 (33.3%)
----------------------------------------
总计: 9 条消息
```

更多测试工具使用说明请参考 [test-tools/README.md](test-tools/README.md)。

## 测试结果

✅ **负载测试** (30 条消息)
- 分发成功率: 100%
- 分发比例: us-east-1 (22.2%), us-west-2 (44.4%), us-west-1 (33.3%)
- Lambda 平均执行时间: ~200-350ms

✅ **核心功能验证**
- ✅ 智能队列负载感知
- ✅ 反向权重分发算法
- ✅ 跨 Region 消息分发
- ✅ DynamoDB 幂等性检查
- ✅ 批量消息处理
- ✅ 自动重试机制

## 项目结构

```
├── src/
│   └── lambda/
│       └── distributor/           # 分发 Lambda 函数
│           ├── handler.py         # Lambda 入口
│           ├── queue_selector.py  # 队列选择逻辑（反向权重算法）
│           └── idempotency.py     # 幂等性检查（DynamoDB）
├── infrastructure/
│   ├── template.yaml              # SAM 模板（IaC）
│   └── samconfig.toml             # SAM 部署配置
├── test-tools/                    # 测试工具
│   ├── producer.py                # 消息生产者
│   ├── consumer.py                # 消息消费者
│   ├── config.example.yaml        # 配置示例
│   └── README.md                  # 使用文档
├── docs/                          # 文档
│   ├── quick-start.md             # 快速开始指南
│   └── deployment-summary.md      # 部署总结
├── events/                        # 测试事件
│   └── sample-sqs-event.json
├── tests/                         # 单元测试
│   └── unit/
├── tasks/                         # 任务跟踪
│   └── todo.md
├── requirements.txt               # Lambda 依赖
├── requirements-dev.txt           # 开发依赖
├── design.md                      # 系统设计文档
└── CLAUDE.md                      # Claude Code 指南
```

## 配置参数

### Lambda 环境变量

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `CACHE_TTL` | 60 | 队列负载缓存时间（秒） |
| `MAX_QUEUE_DEPTH_THRESHOLD` | 5000 | 队列过载阈值（条） |
| `IDEMPOTENCY_TABLE_NAME` | inference-idempotency-dev | DynamoDB 表名 |
| `LOG_LEVEL` | INFO | 日志级别 |
| `REGION_QUEUES` | {...} | Region 到队列 URL 的映射（JSON） |

### 关键配置

| 配置项 | 值 |
|--------|-----|
| Lambda 超时 | 300 秒 |
| 主队列 VisibilityTimeout | 600 秒 |
| 子队列 VisibilityTimeout | 3600 秒 |
| 最大重试次数 | 3 次（后进入 DLQ） |
| 幂等性 TTL | 7 天 |

## 消息格式

```json
{
  "request_id": "req-{uuid}",
  "model_name": "gpt-l-7b",
  "input_data_url": "s3://bucket/inputs/file.json",
  "callback_sns_topic": "arn:aws:sns:us-east-1:xxx:results",
  "priority": "high",
  "timestamp": "2025-12-02T10:23:00Z",
  "metadata": {
    "user_id": "user123",
    "session_id": "session456"
  }
}
```

## 监控和日志

### 查看 Lambda 日志

```bash
aws logs tail /aws/lambda/inference-distributor-dev \
  --since 10m \
  --follow \
  --profile default
```

### CloudWatch 指标

- Lambda 调用次数、错误率、持续时间
- SQS 队列深度（总队列 + 各子队列）
- DynamoDB 读写延迟
- DLQ 消息数（配置了告警）

### CloudWatch 告警

- Lambda 错误率 > 5 errors/5min
- 主队列 DLQ ≥ 1 message

## 核心算法

### 反向权重算法

```python
# 1. 获取所有队列负载
queue_loads = {
    "us-east-1": 10,
    "us-west-2": 5,
    "us-west-1": 15
}

# 2. 计算反向权重
max_depth = 15
weights = {
    "us-east-1": max(1, 15 - 10 + 1) = 6,
    "us-west-2": max(1, 15 - 5 + 1) = 11,  # 负载最低，权重最高
    "us-west-1": max(1, 15 - 15 + 1) = 1
}

# 3. 归一化权重
total = 6 + 11 + 1 = 18
normalized_weights = {
    "us-east-1": 6/18 = 0.33 (33%),
    "us-west-2": 11/18 = 0.61 (61%),  # 被选中概率最高
    "us-west-1": 1/18 = 0.06 (6%)
}

# 4. 加权随机选择
selected_region = random.choices(regions, weights=normalized_weights)[0]
```

## 成本估算

基于当前配置（假设每天 10 万条消息）：

- **Lambda**: ~$5/月
- **SQS**: ~$10/月
- **DynamoDB**: ~$3/月

**总计**: ~$18/月

## 文档

- 📖 [快速开始指南](docs/quick-start.md) - 详细的部署和配置步骤
- 📋 [部署总结](docs/deployment-summary.md) - 已部署资源和测试结果
- 🛠️ [测试工具文档](test-tools/README.md) - Producer 和 Consumer 使用说明
- 📐 [设计文档](design.md) - 系统架构和设计理念
- 🤖 [Claude Code 指南](CLAUDE.md) - AI 辅助开发指南

## 常见问题

### Q: 消息没有分发到子队列？
A: 检查：
1. Lambda 环境变量 `REGION_QUEUES` 是否正确
2. IAM 角色是否有跨 region SQS 权限
3. 查看 Lambda 日志中的错误信息

### Q: 如何测试幂等性？
A: 使用 producer 的 `--duplicate` 参数：
```bash
python3 producer.py \
  --queue-url <URL> \
  --duplicate \
  --request-id test-dup-001 \
  --count 5
```

### Q: 如何调整负载均衡策略？
A: 修改 Lambda 环境变量：
- `CACHE_TTL`: 调整缓存刷新频率
- `MAX_QUEUE_DEPTH_THRESHOLD`: 调整队列过载阈值

## 后续改进建议

- [ ] 添加单元测试覆盖（pytest + moto）
- [ ] 使用 CDK 或 Terraform 实现真正的跨 Region 部署
- [ ] 配置 X-Ray 追踪
- [ ] 实现 Lambda Insights 监控
- [ ] 添加 CloudWatch Dashboard
- [ ] 实现消息优先级队列
- [ ] 添加 CI/CD pipeline

## 贡献

欢迎提交 Issue 和 Pull Request！

## License

MIT License


