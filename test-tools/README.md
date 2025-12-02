# 测试工具使用指南

本目录包含用于测试多 Region 队列分发系统的工具。

## 工具说明

### 1. producer.py - 消息生产者

向主队列发送测试消息。

#### 基本用法

```bash
# 发送 10 条消息（默认）
python producer.py --queue-url <MASTER_QUEUE_URL>

# 发送 100 条消息，间隔 0.5 秒
python producer.py \
  --queue-url <MASTER_QUEUE_URL> \
  --count 100 \
  --interval 0.5

# 批量发送（每次 10 条）
python producer.py \
  --queue-url <MASTER_QUEUE_URL> \
  --count 100 \
  --batch-size 10 \
  --interval 1

# 指定模型名称
python producer.py \
  --queue-url <MASTER_QUEUE_URL> \
  --count 50 \
  --model llama-70b
```

#### 测试幂等性

```bash
# 发送 5 条相同 request_id 的消息（测试去重）
python producer.py \
  --queue-url <MASTER_QUEUE_URL> \
  --duplicate \
  --request-id test-idempotency-001 \
  --count 5 \
  --interval 1
```

#### 参数说明

- `--queue-url`: 主队列 URL（必需）
- `--count`: 发送消息数量（默认: 10）
- `--interval`: 发送间隔秒数（默认: 0.5）
- `--batch-size`: 批量大小 1-10（默认: 1）
- `--model`: 模型名称（默认: gpt-l-7b）
- `--profile`: AWS profile（默认: default）
- `--duplicate`: 发送重复消息（配合 --request-id 使用）
- `--request-id`: 自定义 request_id

### 2. consumer.py - 消息消费者

从 3 个子队列消费消息，查看分发效果。

#### 基本用法

```bash
# 从所有队列消费一次
python consumer.py \
  --queue-us-east-1 <US_EAST_1_QUEUE_URL> \
  --queue-us-west-2 <US_WEST_2_QUEUE_URL> \
  --queue-us-west-1 <US_WEST_1_QUEUE_URL>

# 持续消费 60 秒
python consumer.py \
  --queue-us-east-1 <US_EAST_1_QUEUE_URL> \
  --queue-us-west-2 <US_WEST_2_QUEUE_URL> \
  --queue-us-west-1 <US_WEST_1_QUEUE_URL> \
  --continuous \
  --duration 60

# 每次最多接收 10 条消息
python consumer.py \
  --queue-us-east-1 <US_EAST_1_QUEUE_URL> \
  --queue-us-west-2 <US_WEST_2_QUEUE_URL> \
  --queue-us-west-1 <US_WEST_1_QUEUE_URL> \
  --max-messages 10 \
  --wait-time 20

# 只查看不删除（用于观察）
python consumer.py \
  --queue-us-east-1 <US_EAST_1_QUEUE_URL> \
  --queue-us-west-2 <US_WEST_2_QUEUE_URL> \
  --queue-us-west-1 <US_WEST_1_QUEUE_URL> \
  --no-delete

# 导出消费的消息到 JSON
python consumer.py \
  --queue-us-east-1 <US_EAST_1_QUEUE_URL> \
  --queue-us-west-2 <US_WEST_2_QUEUE_URL> \
  --queue-us-west-1 <US_WEST_1_QUEUE_URL> \
  --export messages.json
```

#### 参数说明

- `--queue-us-east-1`: US East 1 队列 URL（必需）
- `--queue-us-west-2`: US West 2 队列 URL（必需）
- `--queue-us-west-1`: US West 1 队列 URL（必需）
- `--max-messages`: 每个队列最多接收消息数（默认: 10）
- `--wait-time`: 长轮询等待时间秒数（默认: 5）
- `--continuous`: 持续消费模式
- `--duration`: 持续消费时长秒数（默认: 60）
- `--no-delete`: 不自动删除消息
- `--profile`: AWS profile（默认: default）
- `--export`: 导出消息到 JSON 文件

## 测试场景

### 场景 1: 基本功能测试

1. 发送 30 条消息到主队列：

```bash
python producer.py \
  --queue-url <MASTER_QUEUE_URL> \
  --count 30 \
  --interval 0.5
```

2. 等待 Lambda 处理（约 5-10 秒）

3. 从子队列消费：

```bash
python consumer.py \
  --queue-us-east-1 <US_EAST_1_QUEUE_URL> \
  --queue-us-west-2 <US_WEST_2_QUEUE_URL> \
  --queue-us-west-1 <US_WEST_1_QUEUE_URL> \
  --max-messages 10
```

4. 查看分发比例统计

### 场景 2: 负载均衡测试

1. 发送大量消息（1000 条）：

```bash
python producer.py \
  --queue-url <MASTER_QUEUE_URL> \
  --count 1000 \
  --batch-size 10 \
  --interval 0.1
```

2. 持续消费并观察分发：

```bash
python consumer.py \
  --queue-us-east-1 <US_EAST_1_QUEUE_URL> \
  --queue-us-west-2 <US_WEST_2_QUEUE_URL> \
  --queue-us-west-1 <US_WEST_1_QUEUE_URL> \
  --continuous \
  --duration 300 \
  --max-messages 10
```

3. 观察各 Region 分发比例是否均衡

### 场景 3: 幂等性测试

1. 发送重复消息：

```bash
python producer.py \
  --queue-url <MASTER_QUEUE_URL> \
  --duplicate \
  --request-id test-dup-001 \
  --count 5 \
  --interval 2
```

2. 检查 DynamoDB 表：

```bash
aws dynamodb get-item \
  --table-name inference-idempotency-dev \
  --key '{"request_id": {"S": "test-dup-001"}}' \
  --profile default
```

3. 验证子队列中只有 1 条消息（不是 5 条）

## 获取队列 URL

部署完成后，使用以下命令获取队列 URL：

```bash
# 主队列 URL
aws cloudformation describe-stacks \
  --stack-name inference-orchestrator \
  --query 'Stacks[0].Outputs[?OutputKey==`MasterQueueUrl`].OutputValue' \
  --output text \
  --profile default

# US East 1 队列 URL
aws cloudformation describe-stacks \
  --stack-name inference-orchestrator \
  --query 'Stacks[0].Outputs[?OutputKey==`RegionQueueUsEast1Url`].OutputValue' \
  --output text \
  --profile default

# US West 2 队列 URL
aws cloudformation describe-stacks \
  --stack-name inference-orchestrator \
  --query 'Stacks[0].Outputs[?OutputKey==`RegionQueueUsWest2Url`].OutputValue' \
  --output text \
  --profile default

# US West 1 队列 URL
aws cloudformation describe-stacks \
  --stack-name inference-orchestrator \
  --query 'Stacks[0].Outputs[?OutputKey==`RegionQueueUsWest1Url`].OutputValue' \
  --output text \
  --profile default
```

## 创建便捷脚本

为了简化使用，可以创建环境变量文件：

```bash
# test-env.sh
export MASTER_QUEUE_URL="https://sqs.us-east-1.amazonaws.com/xxx/inference-master-queue-dev"
export QUEUE_US_EAST_1="https://sqs.us-east-1.amazonaws.com/xxx/inference-queue-us-east-1-dev"
export QUEUE_US_WEST_2="https://sqs.us-west-2.amazonaws.com/xxx/inference-queue-us-west-2-dev"
export QUEUE_US_WEST_1="https://sqs.us-west-1.amazonaws.com/xxx/inference-queue-us-west-1-dev"
```

然后使用：

```bash
source test-env.sh

# 生产消息
python producer.py --queue-url $MASTER_QUEUE_URL --count 50

# 消费消息
python consumer.py \
  --queue-us-east-1 $QUEUE_US_EAST_1 \
  --queue-us-west-2 $QUEUE_US_WEST_2 \
  --queue-us-west-1 $QUEUE_US_WEST_1
```

## 注意事项

1. 确保 AWS CLI 已配置好 credentials（使用 `--profile default`）
2. 确保有相应队列的 SQS 权限
3. consumer 工具会自动删除消息，使用 `--no-delete` 可以只查看
4. 长时间运行 consumer 时注意 AWS 成本
5. 测试完成后检查 DLQ 中是否有失败消息
