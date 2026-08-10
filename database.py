# database.py
import sqlite3
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class SubscriberDB:
    def __init__(self, db_path="subscribers.db"):
        """Инициализация базы данных подписчиков."""
        self.db_path = db_path
        self.init_db()
    
    def init_db(self):
        """Создание таблицы, если её нет."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS subscribers (
                        chat_id INTEGER PRIMARY KEY,
                        username TEXT,
                        first_name TEXT,
                        subscribed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        is_active BOOLEAN DEFAULT 1
                    )
                """)
                conn.commit()
                logger.info("Database initialized successfully")
        except Exception as e:
            logger.error(f"Database initialization error: {e}")
    
    def add_subscriber(self, chat_id, username=None, first_name=None):
        """Добавление или обновление подписчика."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO subscribers (chat_id, username, first_name, is_active, subscribed_at)
                    VALUES (?, ?, ?, 1, CURRENT_TIMESTAMP)
                """, (chat_id, username, first_name))
                conn.commit()
                logger.info(f"Subscriber added: {chat_id}")
                return True
        except Exception as e:
            logger.error(f"Error adding subscriber {chat_id}: {e}")
            return False
    
    def remove_subscriber(self, chat_id):
        """Мягкое удаление подписчика (деактивация)."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE subscribers SET is_active = 0 WHERE chat_id = ?",
                    (chat_id,)
                )
                conn.commit()
                logger.info(f"Subscriber deactivated: {chat_id}")
                return True
        except Exception as e:
            logger.error(f"Error removing subscriber {chat_id}: {e}")
            return False
    
    def get_active_subscribers(self):
        """Получение списка активных подписчиков."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT chat_id FROM subscribers WHERE is_active = 1"
                )
                return [row[0] for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error getting subscribers: {e}")
            return []
    
    def get_stats(self):
        """Получение статистики подписчиков."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM subscribers WHERE is_active = 1")
                active = cursor.fetchone()[0]
                cursor.execute("SELECT COUNT(*) FROM subscribers")
                total = cursor.fetchone()[0]
                return {"active": active, "total": total}
        except Exception as e:
            logger.error(f"Error getting stats: {e}")
            return {"active": 0, "total": 0}