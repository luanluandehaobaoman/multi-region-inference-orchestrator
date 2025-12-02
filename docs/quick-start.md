# 快速开始指南

## 前提条件

- AWS CLI 已配置（使用 `--profile default`）
- Python 3.12+
- SAM CLI（用于部署）

## 1. 克隆并设置项目

```bash
cd multi-region-inference-orchestrator
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

## 2. 部署到 AWS

```bash
# 构建
sam build --template infrastructure/template.yaml --profile default

# 部署
sam deploy --guided --profile default

# 或使用现有配置
sam deploy --profile default
```

## 3. 创建跨 Region 子队列

SAM 只能在单个 region 部署资源。需要手动在其他 region 创建子队列：

```bash
# 在 us-west-2 创建队列
aws sqs create-queue \
  --queue-name inference-queue-us-west-2-dev \
  --region us-west-2 \
  --profile default \
  --attributes VisibilityTimeout=3600,MessageRetentionPeriod=1209600,ReceiveMessageWaitTimeSeconds=20

# 在 us-west-1 创建队列
aws sqs create-queue \
  --queue-name inference-queue-us-west-1-dev \
  --region us-west-1 \
  --profile default \
  --attributes VisibilityTimeout=3600,MessageRetentionPeriod=1209600,ReceiveMessageWaitTimeSeconds=20
```

## 4. 更新 Lambda 环境变量

```bash
aws lambda update-function-configuration \
  --function-name inference-distributor-dev \
  --environment Variables="{
    CACHE_TTL=60,
    MAX_QUEUE_DEPTH_THRESHOLD=5000,
    IDEMPOTENCY_TABLE_NAME=inference-idempotency-dev,
    LOG_LEVEL=INFO,
    REGION_QUEUES='{\"us-east-1\":\"https://sqs.us-east-1.amazonaws.com/YOUR_ACCOUNT/inference-queue-us-east-1-dev\",\"us-west-2\":\"https://sqs.us-west-2.amazonaws.com/YOUR_ACCOUNT/inference-queue-us-west-2-dev\",\"us-west-1\":\"https://sqs.us-west-1.amazonaws.com/YOUR_ACCOUNT/inference-queue-us-west-1-dev\"}'
  }" \
  --region us-east-1 \
  --profile default
```

⚠️ 替换 `YOUR_ACCOUNT` 为你的 AWS Account ID

## 5. 更新 IAM 权限

创建策略文件：

```bash
cat > cross-region-policy.json <<'EOF'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "sqs:SendMessage",
        "sqs:SendMessageBatch",
        "sqs:GetQueueAttributes"
      ],
      "Resource": [
        "arn:aws:sqs:us-west-2:YOUR_ACCOUNT:inference-queue-us-west-2-dev",
        "arn:aws:sqs:us-west-1:YOUR_ACCOUNT:inference-queue-us-west-1-dev"
      ]
    }
  ]
}
EOF
```

附加策略到 Lambda 角色：

```bash
# 获取 Lambda 角色名
ROLE_NAME=$(aws lambda get-function \
  --function-name inference-distributor-dev \
  --profile default \
  --query 'Configuration.Role' \
  --output text | awk -F'/' '{print $NF}')

# 附加策略
aws iam put-role-policy \
  --role-name $ROLE_NAME \
  --policy-name CrossRegionSQSAccess \
  --policy-document file://cross-region-policy.json \
  --profile default
```

## 6. 测试系统

### 获取队列 URL

```bash
# 主队列
MASTER_QUEUE=$(aws cloudformation describe-stacks \
  --stack-name inference-orchestrator \
  --profile default \
  --query 'Stacks[0].Outputs[?OutputKey==`MasterQueueUrl`].OutputValue' \
  --output text)

# 子队列
QUEUE_US_EAST_1=$(aws cloudformation describe-stacks \
  --stack-name inference-orchestrator \
  --profile default \
  --query 'Stacks[0].Outputs[?OutputKey==`RegionQueueUsEast1Url`].OutputValue' \
  --output text)

QUEUE_US_WEST_2=$(aws sqs get-queue-url \
  --queue-name inference-queue-us-west-2-dev \
  --region us-west-2 \
  --profile default \
  --query 'QueueUrl' \
  --output text)

QUEUE_US_WEST_1=$(aws sqs get-queue-url \
  --queue-name inference-queue-us-west-1-dev \
  --region us-west-1 \
  --profile default \
  --query 'QueueUrl' \
  --output text)
```

### 发送测试消息

```bash
cd test-tools

# 发送 30 条测试消息
python3 producer.py \
  --queue-url $MASTER_QUEUE \
  --count 30 \
  --interval 0.2 \
  --profile default
```

### 消费消息并查看分发结果

```bash
# 等待 Lambda 处理（约 10-20 秒）
sleep 15

# 消费消息
python3 consumer.py \
  --queue-us-east-1 $QUEUE_US_EAST_1 \
  --queue-us-west-2 $QUEUE_US_WEST_2 \
  --queue-us-west-1 $QUEUE_US_WEST_1 \
  --max-messages 10 \
  --profile default
```

## 7. 查看日志

```bash
# 实时查看 Lambda 日志
aws logs tail /aws/lambda/inference-distributor-dev \
  --since 5m \
  --follow \
  --profile default
```

## 8. 监控队列状态

```bash
# 主队列深度
aws sqs get-queue-attributes \
  --queue-url $MASTER_QUEUE \
  --attribute-names ApproximateNumberOfMessages \
  --profile default

# 子队列深度
aws sqs get-queue-attributes \
  --queue-url $QUEUE_US_WEST_2 \
  --region us-west-2 \
  --attribute-names ApproximateNumberOfMessages \
  --profile default
```

## 9. 清理资源

```bash
# 删除 CloudFormation Stack
sam delete --profile default

# 删除手动创建的队列
aws sqs delete-queue --queue-url $QUEUE_US_WEST_2 --region us-west-2 --profile default
aws sqs delete-queue --queue-url $QUEUE_US_WEST_1 --region us-west-1 --profile default
```

## 常见问题

### Q: Lambda 出现 "module 'config' has no attribute" 错误？
A: 确保使用最新的代码，已经移除了对 config 模块的依赖，直接使用环境变量。

### Q: 消息没有分发到子队列？
A: 检查：
1. Lambda 环境变量 REGION_QUEUES 是否正确配置
2. IAM 角色是否有跨 region SQS 权限
3. 查看 Lambda 日志中的错误信息

### Q: 如何测试幂等性？
A: 使用 producer 的 `--duplicate` 参数：
```bash
python3 producer.py \
  --queue-url $MASTER_QUEUE \
  --duplicate \
  --request-id test-dup-001 \
  --count 5 \
  --profile default
```

查看 DynamoDB：
```bash
aws dynamodb get-item \
  --table-name inference-idempotency-dev \
  --key '{"request_id": {"S": "test-dup-001"}}' \
  --profile default
```

### Q: 如何调整负载均衡策略？
A: 修改 Lambda 环境变量：
- `CACHE_TTL`: 调整缓存刷新周期（默认 60 秒）
- `MAX_QUEUE_DEPTH_THRESHOLD`: 调整队列过载阈值（默认 5000）

## 更多文档

- [部署总结](deployment-summary.md)
- [设计文档](../design.md)
- [开发指南](../CLAUDE.md)
- [测试工具文档](../test-tools/README.md)
