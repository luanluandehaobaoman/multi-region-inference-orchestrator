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

#### 高吞吐量测试

```bash
# 使用 --rate 参数：每秒发送 100 条消息
python producer.py \
  --queue-url <MASTER_QUEUE_URL> \
  --rate 100 \
  --count 6000

# 等价于 --interval 0.01（但更直观）
python producer.py \
  --queue-url <MASTER_QUEUE_URL> \
  --rate 50 \
  --count 3000
```

#### 参数说明

- `--queue-url`: 主队列 URL（必需）
- `--count`: 发送消息数量（默认: 10）
- `--interval`: 发送间隔秒数（与 `--rate` 互斥）
- `--rate`: 每秒发送消息数（与 `--interval` 互斥，优先级高）
- `--batch-size`: 批量大小 1-10（默认: 1）
- `--model`: 模型名称（默认: gpt-l-7b）
- `--profile`: AWS profile（默认: default）
- `--duplicate`: 发送重复消息（配合 --request-id 使用）
- `--request-id`: 自定义 request_id

**注意**: `--rate` 和 `--interval` 不能同时使用。如果都不指定，默认速率为 2 条/秒（间隔 0.5秒）。

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

#### 高吞吐量测试（速率控制）

```bash
# 使用 --rate 参数：每秒消费 100 条消息
python consumer.py \
  --queue-us-east-1 <US_EAST_1_QUEUE_URL> \
  --queue-us-west-2 <US_WEST_2_QUEUE_URL> \
  --queue-us-west-1 <US_WEST_1_QUEUE_URL> \
  --continuous \
  --rate 100 \
  --duration 60

# 每秒消费 50 条，持续 120 秒
python consumer.py \
  --queue-us-east-1 <US_EAST_1_QUEUE_URL> \
  --queue-us-west-2 <US_WEST_2_QUEUE_URL> \
  --queue-us-west-1 <US_WEST_1_QUEUE_URL> \
  --continuous \
  --rate 50 \
  --duration 120
```

#### 参数说明

- `--queue-us-east-1`: US East 1 队列 URL（必需）
- `--queue-us-west-2`: US West 2 队列 URL（必需）
- `--queue-us-west-1`: US West 1 队列 URL（必需）
- `--max-messages`: 每个队列最多接收消息数（默认: 10）
- `--wait-time`: 长轮询等待时间秒数（默认: 5）
- `--continuous`: 持续消费模式
- `--duration`: 持续消费时长秒数（默认: 60）
- `--rate`: 目标消费速率（条/秒），仅在 `--continuous` 模式下有效
- `--no-delete`: 不自动删除消息
- `--profile`: AWS profile（默认: default）
- `--export`: 导出消息到 JSON 文件

**注意**: `--rate` 参数仅在 `--continuous` 模式下有效，用于控制消费速率以模拟真实负载场景。

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

### 场景 4: 高吞吐量负载均衡测试

测试系统在高吞吐量场景下的负载均衡表现。

1. 启动高速生产者（100 条/秒）：

```bash
python producer.py \
  --queue-url <MASTER_QUEUE_URL> \
  --rate 100 \
  --count 6000
```

2. 同时启动速率控制的消费者（100 条/秒）：

```bash
python consumer.py \
  --queue-us-east-1 <US_EAST_1_QUEUE_URL> \
  --queue-us-west-2 <US_WEST_2_QUEUE_URL> \
  --queue-us-west-1 <US_WEST_1_QUEUE_URL> \
  --continuous \
  --rate 100 \
  --duration 60
```

3. 观察测试结果：
   - Consumer 显示的实际消费速率
   - 各 Region 的消息分发比例
   - 队列堆积情况

4. 检查队列深度：

```bash
# 检查 us-east-1 队列深度
aws sqs get-queue-attributes \
  --queue-url <US_EAST_1_QUEUE_URL> \
  --attribute-names ApproximateNumberOfMessages \
  --profile default

# 检查 us-west-2 队列深度
aws sqs get-queue-attributes \
  --queue-url <US_WEST_2_QUEUE_URL> \
  --attribute-names ApproximateNumberOfMessages \
  --profile default \
  --region us-west-2

# 检查 us-west-1 队列深度
aws sqs get-queue-attributes \
  --queue-url <US_WEST_1_QUEUE_URL> \
  --attribute-names ApproximateNumberOfMessages \
  --profile default \
  --region us-west-1
```

**预期结果**:
- 消费速率应接近目标 100 条/秒
- 各 Region 分发比例应相对均衡
- 队列堆积应保持在合理范围内（< 500 条）

**注意**: Lambda 的 `CACHE_TTL` 配置会影响负载均衡效果。建议设置为 10 秒以获得更好的均衡性。

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
