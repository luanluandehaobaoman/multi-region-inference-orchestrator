"""
Lambda 函数入口模块

负责处理来自主队列的消息，实现幂等性检查、队列选择和消息分发。
"""
import json
import logging
from typing import Dict, List, Any
import boto3

from idempotency import check_and_record_message
from queue_selector import get_target_queue_url, sqs_client

# 配置日志
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda 入口函数

    Args:
        event: SQS 事件，包含批量消息
        context: Lambda 运行时上下文

    Returns:
        Dict: 处理结果，包含成功和失败的消息数量
    """
    logger.info(f"收到 {len(event['Records'])} 条消息")

    # 统计信息
    stats = {
        "total": len(event["Records"]),
        "processed": 0,
        "duplicate": 0,
        "failed": 0,
        "success": 0,
    }

    # 批量处理消息
    messages_to_forward = []  # 待转发的消息
    messages_to_delete = []   # 待删除的消息（成功处理的）

    for record in event["Records"]:
        try:
            # 解析消息
            message_body = record["body"]
            receipt_handle = record["receiptHandle"]

            # 解析 JSON 消息体
            try:
                message_data = json.loads(message_body)
                request_id = message_data.get("request_id")

                if not request_id:
                    logger.error(f"消息缺少 request_id: {message_body}")
                    stats["failed"] += 1
                    continue

            except json.JSONDecodeError:
                logger.error(f"消息 JSON 解析失败: {message_body}")
                stats["failed"] += 1
                continue

            # 幂等性检查
            is_first_time = check_and_record_message(request_id, message_body)

            if not is_first_time:
                # 重复消息，标记为删除（避免重复处理）
                stats["duplicate"] += 1
                messages_to_delete.append(
                    {"Id": request_id, "ReceiptHandle": receipt_handle}
                )
                continue

            # 选择目标队列
            try:
                target_region, target_queue_url = get_target_queue_url()
                logger.info(
                    f"消息 {request_id} 将发送到 Region: {target_region}"
                )

                messages_to_forward.append({
                    "request_id": request_id,
                    "message_body": message_body,
                    "receipt_handle": receipt_handle,
                    "target_queue_url": target_queue_url,
                })
                stats["processed"] += 1

            except ValueError as e:
                logger.error(f"选择目标队列失败: {str(e)}")
                stats["failed"] += 1
                # 不删除消息，让 SQS 自动重试
                continue

        except Exception as e:
            logger.error(f"处理消息时发生未知错误: {str(e)}", exc_info=True)
            stats["failed"] += 1
            continue

    # 批量转发消息到子队列
    if messages_to_forward:
        forward_results = forward_messages_batch(messages_to_forward)
        stats["success"] = forward_results["success"]
        stats["failed"] += forward_results["failed"]

        # 将成功转发的消息加入删除列表
        messages_to_delete.extend(forward_results["to_delete"])

    # 批量删除成功处理的消息
    if messages_to_delete:
        delete_results = delete_messages_batch(messages_to_delete, event["Records"])
        logger.info(f"删除消息结果: {delete_results}")

    # 返回处理统计
    logger.info(f"处理完成: {stats}")
    return {
        "statusCode": 200,
        "body": json.dumps(stats)
    }


def forward_messages_batch(messages: List[Dict]) -> Dict[str, Any]:
    """
    批量转发消息到子队列

    Args:
        messages: 待转发的消息列表

    Returns:
        Dict: 包含成功、失败数量和待删除消息列表
    """
    results = {"success": 0, "failed": 0, "to_delete": []}

    # 按目标队列分组
    queue_groups = {}
    for msg in messages:
        target_url = msg["target_queue_url"]
        if target_url not in queue_groups:
            queue_groups[target_url] = []
        queue_groups[target_url].append(msg)

    # 对每个目标队列批量发送
    for target_url, msgs in queue_groups.items():
        # SQS SendMessageBatch 最多支持 10 条消息
        for i in range(0, len(msgs), 10):
            batch = msgs[i:i+10]
            entries = [
                {
                    "Id": msg["request_id"],
                    "MessageBody": msg["message_body"]
                }
                for msg in batch
            ]

            try:
                response = sqs_client.send_message_batch(
                    QueueUrl=target_url,
                    Entries=entries
                )

                # 处理成功的消息
                for success_msg in response.get("Successful", []):
                    msg_id = success_msg["Id"]
                    results["success"] += 1

                    # 找到对应的消息，加入删除列表
                    for msg in batch:
                        if msg["request_id"] == msg_id:
                            results["to_delete"].append({
                                "Id": msg_id,
                                "ReceiptHandle": msg["receipt_handle"]
                            })
                            break

                # 处理失败的消息
                for failed_msg in response.get("Failed", []):
                    msg_id = failed_msg["Id"]
                    logger.error(
                        f"消息 {msg_id} 发送失败: "
                        f"{failed_msg.get('Code')} - {failed_msg.get('Message')}"
                    )
                    results["failed"] += 1

            except Exception as e:
                logger.error(
                    f"批量发送消息到 {target_url} 失败: {str(e)}",
                    exc_info=True
                )
                results["failed"] += len(batch)

    return results


def delete_messages_batch(
    messages_to_delete: List[Dict], original_records: List[Dict]
) -> Dict[str, int]:
    """
    批量删除主队列中已成功处理的消息

    Args:
        messages_to_delete: 待删除的消息列表
        original_records: 原始 SQS 记录（用于获取队列 URL）

    Returns:
        Dict: 包含成功和失败删除数量
    """
    results = {"success": 0, "failed": 0}

    if not messages_to_delete:
        return results

    # 从第一条记录获取主队列 URL
    queue_url = original_records[0]["eventSourceARN"].replace(
        "arn:aws:sqs:", "https://sqs."
    ).replace(":queue/", ".amazonaws.com/")

    # 实际上我们需要从 eventSourceARN 构建正确的 queue_url
    # 更简单的方法是通过环境变量传递，但这里我们使用 AWS SDK 方法
    # 从 eventSourceARN 提取
    event_source_arn = original_records[0]["eventSourceARN"]
    # ARN 格式: arn:aws:sqs:region:account-id:queue-name
    arn_parts = event_source_arn.split(":")
    region = arn_parts[3]
    account_id = arn_parts[4]
    queue_name = arn_parts[5]
    queue_url = f"https://sqs.{region}.amazonaws.com/{account_id}/{queue_name}"

    # SQS DeleteMessageBatch 最多支持 10 条消息
    for i in range(0, len(messages_to_delete), 10):
        batch = messages_to_delete[i:i+10]

        try:
            response = sqs_client.delete_message_batch(
                QueueUrl=queue_url,
                Entries=batch
            )

            results["success"] += len(response.get("Successful", []))

            for failed_msg in response.get("Failed", []):
                logger.error(
                    f"删除消息 {failed_msg['Id']} 失败: "
                    f"{failed_msg.get('Code')} - {failed_msg.get('Message')}"
                )
                results["failed"] += 1

        except Exception as e:
            logger.error(
                f"批量删除消息失败: {str(e)}",
                exc_info=True
            )
            results["failed"] += len(batch)

    return results
