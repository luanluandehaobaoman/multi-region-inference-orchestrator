"""
队列选择模块

实现负载感知的队列选择算法，使用反向权重策略。
负载越低的队列，权重越高，被选中的概率越大。
"""
import time
import random
import logging
from typing import Dict, Tuple
import boto3

import os
import json as json_module

logger = logging.getLogger(__name__)

# 全局缓存变量（Lambda 容器复用时保持）
queue_load_cache: Dict[str, int] = {}
cache_timestamp: float = 0.0

# 全局 SQS 客户端
sqs_client = boto3.client("sqs")

# 从环境变量读取配置
CACHE_TTL = int(os.environ.get("CACHE_TTL", "60"))
MAX_QUEUE_DEPTH_THRESHOLD = int(os.environ.get("MAX_QUEUE_DEPTH_THRESHOLD", "5000"))
REGION_QUEUES = json_module.loads(os.environ.get("REGION_QUEUES", "{}"))


def get_queue_loads(force_refresh: bool = False) -> Dict[str, int]:
    """
    获取所有子队列的负载（带缓存）。

    Args:
        force_refresh: 是否强制刷新缓存

    Returns:
        Dict[str, int]: 队列 region 到消息数的映射
    """
    global queue_load_cache, cache_timestamp

    current_time = time.time()

    # 如果缓存未过期且不强制刷新，直接返回
    if not force_refresh and (current_time - cache_timestamp < CACHE_TTL):
        logger.debug(
            f"使用缓存的队列负载数据（缓存时间: {current_time - cache_timestamp:.2f}s）"
        )
        return queue_load_cache

    # 刷新缓存
    logger.info("刷新队列负载缓存...")
    queue_loads = {}

    for region, queue_url in REGION_QUEUES.items():
        try:
            response = sqs_client.get_queue_attributes(
                QueueUrl=queue_url,
                AttributeNames=["ApproximateNumberOfMessages"]
            )
            queue_depth = int(
                response["Attributes"]["ApproximateNumberOfMessages"]
            )
            queue_loads[region] = queue_depth
            logger.info(f"Region {region} 队列深度: {queue_depth}")

        except Exception as e:
            logger.error(
                f"获取 Region {region} 队列属性失败: {str(e)}",
                exc_info=True
            )
            # 发生错误时使用上次缓存值或默认值 0
            queue_loads[region] = queue_load_cache.get(region, 0)

    # 更新全局缓存
    queue_load_cache = queue_loads
    cache_timestamp = current_time

    return queue_loads


def calculate_weights(queue_loads: Dict[str, int]) -> Dict[str, float]:
    """
    计算反向权重：负载越低，权重越高。

    使用公式: weight = max(1, max_depth - current_depth + 1)
    然后归一化权重，使总和为 1。

    Args:
        queue_loads: 队列 region 到消息数的映射

    Returns:
        Dict[str, float]: 队列 region 到归一化权重的映射
    """
    if not queue_loads:
        logger.error("队列负载数据为空，无法计算权重")
        return {}

    # 过滤掉过载的队列
    available_queues = {
        region: depth
        for region, depth in queue_loads.items()
        if depth < MAX_QUEUE_DEPTH_THRESHOLD
    }

    if not available_queues:
        logger.error(
            f"所有队列都已过载（阈值: {MAX_QUEUE_DEPTH_THRESHOLD}）"
        )
        return {}

    # 计算反向权重
    max_depth = max(available_queues.values())

    weights = {}
    for region, depth in available_queues.items():
        # 避免所有队列深度都为 max_depth 的情况
        weight = max(1, max_depth - depth + 1)
        weights[region] = weight

    # 归一化权重
    total_weight = sum(weights.values())
    normalized_weights = {
        region: weight / total_weight
        for region, weight in weights.items()
    }

    logger.info(f"计算得到的归一化权重: {normalized_weights}")
    return normalized_weights


def select_target_queue(weights: Dict[str, float]) -> Tuple[str, str]:
    """
    根据权重随机选择目标队列。

    Args:
        weights: 队列 region 到归一化权重的映射

    Returns:
        Tuple[str, str]: (region, queue_url)

    Raises:
        ValueError: 如果所有队列都已过载
    """
    if not weights:
        raise ValueError("所有子队列都已过载，无法分发消息")

    regions = list(weights.keys())
    probabilities = list(weights.values())

    # 加权随机选择
    selected_region = random.choices(regions, weights=probabilities, k=1)[0]
    selected_queue_url = REGION_QUEUES[selected_region]

    logger.debug(f"选择目标队列: {selected_region}")
    return selected_region, selected_queue_url


def get_target_queue_url() -> Tuple[str, str]:
    """
    获取目标队列 URL（完整流程）。

    Returns:
        Tuple[str, str]: (region, queue_url)
    """
    # 1. 获取队列负载
    queue_loads = get_queue_loads()

    # 2. 计算权重
    weights = calculate_weights(queue_loads)

    # 3. 选择目标队列
    return select_target_queue(weights)
