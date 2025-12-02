"""
幂等性检查模块

使用 DynamoDB 实现基于 request_id 的消息去重机制。
"""
import time
import hashlib
import logging
from datetime import datetime
from typing import Optional
import boto3
from botocore.exceptions import ClientError

import os

logger = logging.getLogger(__name__)

# 全局 DynamoDB 资源（Lambda 容器复用时保持）
dynamodb = boto3.resource("dynamodb")
idempotency_table = None


def get_idempotency_table():
    """获取 DynamoDB 幂等性表（懒加载）"""
    global idempotency_table
    if idempotency_table is None:
        table_name = os.environ.get("IDEMPOTENCY_TABLE_NAME", "inference-idempotency")
        idempotency_table = dynamodb.Table(table_name)
    return idempotency_table


def check_and_record_message(request_id: str, message_body: str) -> bool:
    """
    检查消息是否已被处理，并记录到 DynamoDB。

    Args:
        request_id: 请求唯一 ID
        message_body: 消息体内容

    Returns:
        bool: True 表示首次处理（可以继续），False 表示重复消息（应跳过）
    """
    table = get_idempotency_table()

    # 计算消息体的 SHA256 哈希值
    message_hash = hashlib.sha256(message_body.encode("utf-8")).hexdigest()

    # 计算 TTL（7 天后过期）
    ttl_days = int(os.environ.get("IDEMPOTENCY_TTL_DAYS", "7"))
    ttl_seconds = ttl_days * 24 * 3600
    ttl_timestamp = int(time.time()) + ttl_seconds

    try:
        # 尝试写入 DynamoDB（使用条件表达式确保幂等性）
        table.put_item(
            Item={
                "request_id": request_id,
                "message_body_hash": message_hash,
                "processed_at": datetime.utcnow().isoformat(),
                "ttl": ttl_timestamp,
            },
            ConditionExpression="attribute_not_exists(request_id)",
        )

        logger.info(f"消息 {request_id} 首次处理，已记录到 DynamoDB")
        return True  # 首次处理

    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            # request_id 已存在，说明消息已被处理过
            logger.warning(f"消息 {request_id} 已被处理过，跳过")
            return False  # 重复消息
        else:
            # 其他 DynamoDB 错误
            logger.error(
                f"DynamoDB 写入失败: {e.response['Error']['Message']}",
                exc_info=True
            )
            raise


def get_processed_record(request_id: str) -> Optional[dict]:
    """
    查询 DynamoDB 中是否存在已处理的记录。

    Args:
        request_id: 请求唯一 ID

    Returns:
        dict: 已处理的记录，如果不存在则返回 None
    """
    table = get_idempotency_table()

    try:
        response = table.get_item(Key={"request_id": request_id})
        return response.get("Item")
    except ClientError as e:
        logger.error(
            f"DynamoDB 查询失败: {e.response['Error']['Message']}",
            exc_info=True
        )
        raise
