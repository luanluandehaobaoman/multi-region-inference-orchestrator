#!/usr/bin/env python3
"""
消息消费者工具

从 3 个子队列（us-east-1, us-west-2, us-west-1）消费消息，用于测试分发效果。
"""
import argparse
import json
import time
from datetime import datetime
from typing import Dict, List
from collections import defaultdict
import boto3
from botocore.exceptions import ClientError


class MessageConsumer:
    """消息消费者类"""

    def __init__(self, queue_urls: Dict[str, str], profile: str = "default"):
        """
        初始化消费者

        Args:
            queue_urls: Region 到队列 URL 的映射
            profile: AWS profile 名称
        """
        session = boto3.Session(profile_name=profile)
        self.sqs = session.client("sqs")
        self.queue_urls = queue_urls
        self.stats = defaultdict(lambda: {"received": 0, "deleted": 0, "failed": 0})
        self.all_messages = []

    def receive_messages(
        self,
        region: str,
        max_messages: int = 10,
        wait_time: int = 20
    ) -> List[Dict]:
        """
        从指定 Region 队列接收消息

        Args:
            region: Region 名称
            max_messages: 最多接收消息数（1-10）
            wait_time: 长轮询等待时间（秒）

        Returns:
            List[Dict]: 接收到的消息列表
        """
        queue_url = self.queue_urls.get(region)
        if not queue_url:
            print(f"✗ Region {region} 队列 URL 未配置")
            return []

        try:
            response = self.sqs.receive_message(
                QueueUrl=queue_url,
                MaxNumberOfMessages=max_messages,
                WaitTimeSeconds=wait_time,
                AttributeNames=["All"],
                MessageAttributeNames=["All"]
            )

            messages = response.get("Messages", [])
            self.stats[region]["received"] += len(messages)

            return messages

        except ClientError as e:
            print(f"✗ 从 {region} 接收消息失败: {e}")
            return []

    def delete_message(self, region: str, receipt_handle: str) -> bool:
        """
        删除已处理的消息

        Args:
            region: Region 名称
            receipt_handle: 消息的 receipt handle

        Returns:
            bool: 是否删除成功
        """
        queue_url = self.queue_urls.get(region)
        if not queue_url:
            return False

        try:
            self.sqs.delete_message(
                QueueUrl=queue_url,
                ReceiptHandle=receipt_handle
            )
            self.stats[region]["deleted"] += 1
            return True

        except ClientError as e:
            print(f"✗ 删除消息失败: {e}")
            self.stats[region]["failed"] += 1
            return False

    def process_message(self, region: str, message: Dict, auto_delete: bool = True) -> None:
        """
        处理单条消息

        Args:
            region: Region 名称
            message: SQS 消息
            auto_delete: 是否自动删除
        """
        try:
            body = json.loads(message["Body"])
            request_id = body.get("request_id", "unknown")
            model_name = body.get("model_name", "unknown")
            timestamp = body.get("timestamp", "unknown")

            print(f"\n📨 [{region}] 收到消息:")
            print(f"   Request ID: {request_id}")
            print(f"   Model: {model_name}")
            print(f"   Timestamp: {timestamp}")

            # 保存消息用于统计
            self.all_messages.append({
                "region": region,
                "request_id": request_id,
                "model_name": model_name,
                "timestamp": timestamp,
                "received_at": datetime.utcnow().isoformat()
            })

            # 自动删除消息
            if auto_delete:
                receipt_handle = message["ReceiptHandle"]
                if self.delete_message(region, receipt_handle):
                    print(f"   ✓ 已删除")
                else:
                    print(f"   ✗ 删除失败")

        except json.JSONDecodeError:
            print(f"✗ 消息 JSON 解析失败: {message.get('Body', '')}")
            self.stats[region]["failed"] += 1
        except Exception as e:
            print(f"✗ 处理消息时发生错误: {e}")
            self.stats[region]["failed"] += 1

    def consume_from_all_regions(
        self,
        max_messages_per_region: int = 10,
        wait_time: int = 5,
        auto_delete: bool = True
    ) -> None:
        """
        从所有 Region 队列消费消息（单次）

        Args:
            max_messages_per_region: 每个队列最多接收消息数
            wait_time: 长轮询等待时间（秒）
            auto_delete: 是否自动删除
        """
        print(f"\n🔍 开始从 {len(self.queue_urls)} 个 Region 队列消费消息...")
        print(f"最多接收: {max_messages_per_region} 条/队列, 等待时间: {wait_time}s\n")

        for region in self.queue_urls.keys():
            print(f"--- {region} ---")
            messages = self.receive_messages(region, max_messages_per_region, wait_time)

            if messages:
                print(f"✓ 接收到 {len(messages)} 条消息")
                for message in messages:
                    self.process_message(region, message, auto_delete)
            else:
                print(f"  (无消息)")

        self.print_stats()

    def consume_continuous(
        self,
        duration: int = 60,
        max_messages_per_region: int = 10,
        auto_delete: bool = True
    ) -> None:
        """
        持续从所有 Region 队列消费消息

        Args:
            duration: 持续时间（秒）
            max_messages_per_region: 每次每个队列最多接收消息数
            auto_delete: 是否自动删除
        """
        print(f"\n🔄 开始持续消费消息（持续 {duration} 秒）...")
        print(f"从 {len(self.queue_urls)} 个 Region 队列轮询\n")

        start_time = time.time()
        iteration = 0

        while time.time() - start_time < duration:
            iteration += 1
            print(f"\n=== 轮询 #{iteration} ===")

            for region in self.queue_urls.keys():
                messages = self.receive_messages(region, max_messages_per_region, wait_time=5)

                if messages:
                    print(f"[{region}] 接收到 {len(messages)} 条消息")
                    for message in messages:
                        self.process_message(region, message, auto_delete)

            # 短暂休息
            time.sleep(2)

        print(f"\n✅ 持续消费完成（运行了 {int(time.time() - start_time)} 秒）")
        self.print_stats()

    def print_stats(self) -> None:
        """打印统计信息"""
        print("\n" + "=" * 60)
        print("📊 消费统计")
        print("=" * 60)

        total_received = 0
        total_deleted = 0
        total_failed = 0

        for region, stats in sorted(self.stats.items()):
            print(f"\n{region}:")
            print(f"  接收: {stats['received']}")
            print(f"  删除: {stats['deleted']}")
            print(f"  失败: {stats['failed']}")

            total_received += stats['received']
            total_deleted += stats['deleted']
            total_failed += stats['failed']

        print(f"\n总计:")
        print(f"  接收: {total_received}")
        print(f"  删除: {total_deleted}")
        print(f"  失败: {total_failed}")

        # 分发比例
        if total_received > 0:
            print(f"\n📈 分发比例:")
            for region, stats in sorted(self.stats.items()):
                percentage = (stats['received'] / total_received) * 100
                print(f"  {region}: {percentage:.1f}%")

        print("=" * 60)

    def export_messages(self, filename: str = "consumed_messages.json") -> None:
        """导出所有消费的消息"""
        with open(filename, "w") as f:
            json.dump(self.all_messages, f, indent=2)
        print(f"\n✅ 消息已导出到: {filename}")


def main():
    parser = argparse.ArgumentParser(
        description="消息消费者 - 从多个 Region 队列消费消息"
    )

    parser.add_argument(
        "--queue-us-east-1",
        required=True,
        help="US East 1 队列 URL"
    )

    parser.add_argument(
        "--queue-us-west-2",
        required=True,
        help="US West 2 队列 URL"
    )

    parser.add_argument(
        "--queue-us-west-1",
        required=True,
        help="US West 1 队列 URL"
    )

    parser.add_argument(
        "--max-messages",
        type=int,
        default=10,
        help="每个队列最多接收消息数（默认: 10）"
    )

    parser.add_argument(
        "--wait-time",
        type=int,
        default=5,
        help="长轮询等待时间秒数（默认: 5）"
    )

    parser.add_argument(
        "--continuous",
        action="store_true",
        help="持续消费模式"
    )

    parser.add_argument(
        "--duration",
        type=int,
        default=60,
        help="持续消费时长秒数（默认: 60）"
    )

    parser.add_argument(
        "--no-delete",
        action="store_true",
        help="不自动删除消息（仅查看）"
    )

    parser.add_argument(
        "--profile",
        default="default",
        help="AWS profile 名称（默认: default）"
    )

    parser.add_argument(
        "--export",
        help="导出消息到 JSON 文件"
    )

    args = parser.parse_args()

    queue_urls = {
        "us-east-1": args.queue_us_east_1,
        "us-west-2": args.queue_us_west_2,
        "us-west-1": args.queue_us_west_1,
    }

    consumer = MessageConsumer(queue_urls, args.profile)

    auto_delete = not args.no_delete

    if args.continuous:
        consumer.consume_continuous(
            duration=args.duration,
            max_messages_per_region=args.max_messages,
            auto_delete=auto_delete
        )
    else:
        consumer.consume_from_all_regions(
            max_messages_per_region=args.max_messages,
            wait_time=args.wait_time,
            auto_delete=auto_delete
        )

    if args.export:
        consumer.export_messages(args.export)


if __name__ == "__main__":
    main()
