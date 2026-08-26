"""
SQLite 历史价格存储。

数据库默认保存在：

    data/prices.db

GitHub Actions 每次运行时都会产生数据库。
如果希望历史数据跨 workflow 永久保存，
后面可以再增加 GitHub Actions artifact / commit / external storage。
"""

import sqlite3
from pathlib import Path
from datetime import datetime, timezone
from decimal import Decimal


class PriceStorage:

    def __init__(self, database_path: str = "data/prices.db"):
        self.database_path = Path(database_path)

        # 确保 data/ 目录存在。
        self.database_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        self._initialize()

    def _connect(self):
        return sqlite3.connect(self.database_path)

    def _initialize(self):
        """创建数据库表。"""

        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS price_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    cluster_id TEXT NOT NULL,
                    price TEXT NOT NULL,
                    checked_at TEXT NOT NULL
                )
                """
            )

            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS
                idx_cluster_time
                ON price_history(cluster_id, checked_at)
                """
            )

    def add_price(
        self,
        cluster_id: str,
        price: Decimal,
    ):
        """保存一次价格检测结果。"""

        timestamp = datetime.now(
            timezone.utc
        ).isoformat()

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO price_history
                (cluster_id, price, checked_at)
                VALUES (?, ?, ?)
                """,
                (
                    cluster_id,
                    str(price),
                    timestamp,
                ),
            )

    def latest_price(
        self,
        cluster_id: str,
    ):
        """获取最近一次价格。"""

        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT price
                FROM price_history
                WHERE cluster_id = ?
                ORDER BY checked_at DESC
                LIMIT 1
                """,
                (cluster_id,),
            ).fetchone()

        if row is None:
            return None

        return Decimal(row[0])
