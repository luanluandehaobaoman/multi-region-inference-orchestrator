"""
配置管理模块

负责从环境变量读取配置参数，并提供默认值。
"""
import os
import json
from typing import Dict


class Config:
    """配置类，管理所有可配置参数"""

    def __init__(self):
        # 缓存配置
        self.cache_ttl = int(os.environ.get("CACHE_TTL", "60"))  # 秒

        # 队列配置
        self.max_queue_depth_threshold = int(
            os.environ.get("MAX_QUEUE_DEPTH_THRESHOLD", "5000")
        )

        # DynamoDB 配置
        self.idempotency_table_name = os.environ.get(
            "IDEMPOTENCY_TABLE_NAME", "inference-idempotency"
        )

        # TTL 配置 (7 天)
        self.idempotency_ttl_days = int(
            os.environ.get("IDEMPOTENCY_TTL_DAYS", "7")
        )

        # Region 队列映射
        # 格式: {"us-east-1": "https://sqs.us-east-1.amazonaws.com/xxx/queue"}
        region_queues_str = os.environ.get("REGION_QUEUES", "{}")
        self.region_queues = json.loads(region_queues_str)

        # 日志级别
        self.log_level = os.environ.get("LOG_LEVEL", "INFO")

    def validate(self) -> None:
        """验证配置参数的有效性"""
        if not self.region_queues:
            raise ValueError("REGION_QUEUES 环境变量未配置或为空")

        if self.cache_ttl <= 0:
            raise ValueError(f"CACHE_TTL 必须大于 0，当前值: {self.cache_ttl}")

        if self.max_queue_depth_threshold <= 0:
            raise ValueError(
                f"MAX_QUEUE_DEPTH_THRESHOLD 必须大于 0，当前值: {self.max_queue_depth_threshold}"
            )

        if not self.idempotency_table_name:
            raise ValueError("IDEMPOTENCY_TABLE_NAME 不能为空")

    def __repr__(self) -> str:
        """返回配置的字符串表示（隐藏敏感信息）"""
        return (
            f"Config("
            f"cache_ttl={self.cache_ttl}, "
            f"max_queue_depth_threshold={self.max_queue_depth_threshold}, "
            f"idempotency_table_name={self.idempotency_table_name}, "
            f"region_queues_count={len(self.region_queues)}, "
            f"log_level={self.log_level}"
            f")"
        )


# 全局配置实例（Lambda 容器复用时保持）
config = Config()
