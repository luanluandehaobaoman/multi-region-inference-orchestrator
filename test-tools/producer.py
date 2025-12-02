#!/usr/bin/env python3
"""
消息生产者工具

向主队列发送测试消息，用于测试整个分发系统。
"""
import argparse
import json
import uuid
import time
from datetime import datetime
from typing import Dict, List
import boto3
from botocore.exceptions import ClientError


class MessageProducer:
    """消息生产者类"""

    def __init__(self, queue_url: str, profile: str = "default"):
        """
        初始化生产者

        Args:
            queue_url: 主队列 URL
            profile: AWS profile 名称
        """
        session = boto3.Session(profile_name=profile)
        self.sqs = session.client("sqs")
        self.queue_url = queue_url
        self.stats = {"sent": 0, "failed": 0}

    def generate_message(
        self,
        model_name: str = "gpt-l-7b",
        priority: str = "normal",
        custom_request_id: str = None
    ) -> Dict:
        """
        生成测试消息

        Args:
            model_name: 模型名称
            priority: 优先级
            custom_request_id: 自定义 request_id（用于测试幂等性）

        Returns:
            Dict: 消息字典
        """
        request_id = custom_request_id or f"req-{uuid.uuid4()}"

        message = {
            "request_id": request_id,
            "model_name": model_name,
            "input_data_url": f"s3://test-bucket/inputs/{request_id}.json",
            "callback_sns_topic": "arn:aws:sns:us-east-1:123456789012:inference-results",
            "priority": priority,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "metadata": {
                "user_id": f"user-{uuid.uuid4().hex[:8]}",
                "session_id": f"session-{uuid.uuid4().hex[:8]}",
                "test_source": "producer.py"
            }
        }

        return message

    def send_message(self, message: Dict) -> bool:
        """
        发送单条消息

        Args:
            message: 消息字典

        Returns:
            bool: 是否发送成功
        """
        try:
            response = self.sqs.send_message(
                QueueUrl=self.queue_url,
                MessageBody=json.dumps(message)
            )

            print(f"✓ 发送成功: {message['request_id']} (MessageId: {response['MessageId']})")
            self.stats["sent"] += 1
            return True

        except ClientError as e:
            print(f"✗ 发送失败: {message['request_id']} - {e}")
            self.stats["failed"] += 1
            return False

    def send_batch(self, messages: List[Dict]) -> Dict:
        """
        批量发送消息（最多 10 条）

        Args:
            messages: 消息列表

        Returns:
            Dict: 发送结果统计
        """
        if len(messages) > 10:
            raise ValueError("批量发送最多支持 10 条消息")

        entries = [
            {
                "Id": msg["request_id"],
                "MessageBody": json.dumps(msg)
            }
            for msg in messages
        ]

        try:
            response = self.sqs.send_message_batch(
                QueueUrl=self.queue_url,
                Entries=entries
            )

            # 处理成功的消息
            for success in response.get("Successful", []):
                print(f"✓ 批量发送成功: {success['Id']}")
                self.stats["sent"] += 1

            # 处理失败的消息
            for failed in response.get("Failed", []):
                print(f"✗ 批量发送失败: {failed['Id']} - {failed.get('Message')}")
                self.stats["failed"] += 1

        except ClientError as e:
            print(f"✗ 批量发送异常: {e}")
            self.stats["failed"] += len(messages)

        return self.stats

    def run_continuous(
        self,
        count: int,
        interval: float = 0.5,
        batch_size: int = 1,
        model_name: str = "gpt-l-7b"
    ) -> None:
        """
        持续发送消息

        Args:
            count: 发送消息总数
            interval: 发送间隔（秒）
            batch_size: 批量大小（1-10）
            model_name: 模型名称
        """
        print(f"\n开始发送消息...")
        print(f"总数: {count}, 间隔: {interval}s, 批量大小: {batch_size}\n")

        sent = 0
        while sent < count:
            remaining = count - sent
            current_batch_size = min(batch_size, remaining, 10)

            if current_batch_size == 1:
                # 单条发送
                message = self.generate_message(model_name=model_name)
                self.send_message(message)
                sent += 1
            else:
                # 批量发送
                messages = [
                    self.generate_message(model_name=model_name)
                    for _ in range(current_batch_size)
                ]
                self.send_batch(messages)
                sent += current_batch_size

            if sent < count:
                time.sleep(interval)

        print(f"\n✅ 发送完成！")
        print(f"成功: {self.stats['sent']}, 失败: {self.stats['failed']}")


def main():
    parser = argparse.ArgumentParser(
        description="消息生产者 - 向主队列发送测试消息"
    )

    parser.add_argument(
        "--queue-url",
        required=True,
        help="主队列 URL"
    )

    parser.add_argument(
        "--count",
        type=int,
        default=10,
        help="发送消息数量（默认: 10）"
    )

    parser.add_argument(
        "--interval",
        type=float,
        default=0.5,
        help="发送间隔秒数（默认: 0.5）"
    )

    parser.add_argument(
        "--batch-size",
        type=int,
        default=1,
        choices=range(1, 11),
        help="批量大小 1-10（默认: 1）"
    )

    parser.add_argument(
        "--model",
        default="gpt-l-7b",
        help="模型名称（默认: gpt-l-7b）"
    )

    parser.add_argument(
        "--profile",
        default="default",
        help="AWS profile 名称（默认: default）"
    )

    parser.add_argument(
        "--duplicate",
        action="store_true",
        help="发送重复消息（测试幂等性）"
    )

    parser.add_argument(
        "--request-id",
        help="自定义 request_id（用于测试幂等性）"
    )

    args = parser.parse_args()

    producer = MessageProducer(args.queue_url, args.profile)

    if args.duplicate and args.request_id:
        # 测试幂等性：发送多条相同 request_id 的消息
        print(f"\n🔄 幂等性测试模式：发送 {args.count} 条相同的消息")
        print(f"Request ID: {args.request_id}\n")

        for i in range(args.count):
            message = producer.generate_message(
                model_name=args.model,
                custom_request_id=args.request_id
            )
            producer.send_message(message)
            if i < args.count - 1:
                time.sleep(args.interval)
    else:
        # 正常模式
        producer.run_continuous(
            count=args.count,
            interval=args.interval,
            batch_size=args.batch_size,
            model_name=args.model
        )


if __name__ == "__main__":
    main()
