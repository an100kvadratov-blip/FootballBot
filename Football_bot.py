# telegram_rss_bot.py
import requests
from bs4 import BeautifulSoup
import schedule
import time
from datetime import datetime
import logging
import json
import os
import ssl
import urllib3
from urllib3.util.ssl_ import create_urllib3_context

# Фикс для SSL на Mac
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class TelegramRSSBot:
    def __init__(self, config_path='config.json'):
        self.config_path = config_path
        self.load_config()
        self.processed_links = set()
        self.load_processed_links()

        # Настройка сессии с SSL фиксом
        self.session = requests.Session()
        self.session.verify = False

    def load_config(self):
        """Загрузка конфигурации из JSON файла"""
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    self.config = json.load(f)
            else:
                # Конфиг по умолчанию
                self.config = {
                    "telegram_channel": "https://t.me/s/euro_football_ru",
                    "bot_token": "YOUR_BOT_TOKEN_HERE",
                    "target_chat_id": "YOUR_CHAT_ID_HERE",
                    "check_interval_minutes": 30,
                    "schedule_times": ["09:00", "11:00", "13:00", "15:00", "17:00", "19:00", "21:00"]
                }
                self.save_config()

            logger.info("✅ Конфигурация загружена")

        except Exception as e:
            logger.error(f"❌ Ошибка загрузки конфига: {e}")
            raise

    def save_config(self):
        """Сохранение конфигурации"""
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения конфига: {e}")

    def load_processed_links(self):
        """Загрузка обработанных ссылок"""
        try:
            if os.path.exists('processed_links.json'):
                with open('processed_links.json', 'r', encoding='utf-8') as f:
                    self.processed_links = set(json.load(f))
                logger.info(f"📂 Загружено {len(self.processed_links)} обработанных ссылок")
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки ссылок: {e}")

    def save_processed_links(self):
        """Сохранение обработанных ссылок"""
        try:
            with open('processed_links.json', 'w', encoding='utf-8') as f:
                json.dump(list(self.processed_links), f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения ссылок: {e}")

    def parse_telegram_channel(self):
        """Парсинг Telegram канала"""
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
            }

            logger.info(f"📡 Парсинг канала: {self.config['telegram_channel']}")
            response = self.session.get(
                self.config['telegram_channel'],
                headers=headers,
                timeout=30
            )

            if response.status_code == 200:
                soup = BeautifulSoup(response.content, 'html.parser')
                messages = soup.find_all('div', class_='tgme_widget_message')

                logger.info(f"📝 Найдено сообщений: {len(messages)}")
                return messages
            else:
                logger.error(f"❌ Ошибка HTTP: {response.status_code}")
                return []

        except Exception as e:
            logger.error(f"❌ Ошибка парсинга: {e}")
            return []

    def extract_message_data(self, message):
        """Извлечение данных из сообщения"""
        try:
            # Текст
            text_div = message.find('div', class_='tgme_widget_message_text')
            text = text_div.get_text(strip=True) if text_div else ""

            # Ссылка
            link_tag = message.find('a', class_='tgme_widget_message_date')
            link = link_tag['href'] if link_tag and 'href' in link_tag.attrs else ""

            # Изображение
            photo_div = message.find('a', class_='tgme_widget_message_photo_wrap')
            image_url = None

            if photo_div and 'style' in photo_div.attrs:
                style = photo_div['style']
                if 'background-image:url(' in style:
                    start = style.find('background-image:url(') + 22
                    end = style.find(')', start)
                    image_url = style[start:end]

            return {
                'text': text,
                'link': link,
                'image_url': image_url,
                'has_image': image_url is not None,
                'timestamp': datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"❌ Ошибка извлечения данных: {e}")
            return None

    def find_latest_news_with_image(self, messages):
        """Поиск самой последней новости с изображением"""
        # Идем с конца (самые свежие первыми)
        for message in reversed(messages):
            data = self.extract_message_data(message)

            if not data or not data['link']:
                continue

            # Пропускаем обработанные
            if data['link'] in self.processed_links:
                continue

            # Ищем с изображением
            if data['has_image'] and data['image_url']:
                logger.info(f"✅ Найдена новая новость: {data['link']}")
                return data

        logger.info("📭 Новых новостей с изображениями не найдено")
        return None

    def send_to_telegram(self, news_data):
        """Отправка в Telegram"""
        try:
            if not news_data['image_url']:
                logger.error("❌ Нет URL изображения")
                return False

            # Загрузка изображения
            logger.info(f"📥 Загрузка изображения...")
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
            }

            image_response = self.session.get(
                news_data['image_url'],
                headers=headers,
                timeout=30
            )

            if image_response.status_code != 200:
                logger.error(f"❌ Ошибка загрузки изображения: {image_response.status_code}")
                return False

            # Подготовка подписи
            caption = news_data['text']
            if len(caption) > 900:
                caption = caption[:897] + "..."

            # Отправка
            send_url = f"https://api.telegram.org/bot{self.config['bot_token']}/sendPhoto"

            files = {'photo': ('image.jpg', image_response.content)}
            data = {
                'chat_id': self.config['target_chat_id'],
                'caption': caption,
                'parse_mode': 'HTML'
            }

            logger.info("📤 Отправка в Telegram...")
            response = self.session.post(send_url, files=files, data=data, timeout=30)
            result = response.json()

            if response.status_code == 200 and result.get('ok'):
                logger.info("✅ Сообщение отправлено!")
                return True
            else:
                logger.error(f"❌ Ошибка отправки: {result}")
                return False

        except Exception as e:
            logger.error(f"❌ Ошибка отправки: {e}")
            return False

    def process_news(self):
        """Основной процесс обработки"""
        try:
            logger.info("🔄 Запуск обработки...")

            messages = self.parse_telegram_channel()
            if not messages:
                return

            news = self.find_latest_news_with_image(messages)
            if news:
                if self.send_to_telegram(news):
                    self.processed_links.add(news['link'])
                    self.save_processed_links()
                    logger.info(f"✅ Новость обработана: {news['link']}")
                else:
                    logger.error("❌ Не удалось отправить новость")
            else:
                logger.info("📭 Новых новостей нет")

        except Exception as e:
            logger.error(f"❌ Ошибка обработки: {e}")

    def setup_schedule(self):
        """Настройка расписания"""
        # По расписанию
        for time_str in self.config['schedule_times']:
            schedule.every().day.at(time_str).do(self.process_news)
            logger.info(f"⏰ Настроено время: {time_str}")

        # Интервальная проверка
        interval = self.config.get('check_interval_minutes', 30)
        schedule.every(interval).minutes.do(self.process_news)
        logger.info(f"⏰ Интервальная проверка: каждые {interval} минут")

    def run_once(self):
        """Однократный запуск"""
        logger.info("🔴 Однократный запуск")
        self.process_news()

    def run_scheduled(self):
        """Запуск по расписанию"""
        logger.info("🟢 Запуск по расписанию")
        self.setup_schedule()

        # Первый запуск
        self.process_news()

        logger.info("⏰ Бот запущен. Ожидание расписания...")
        while True:
            schedule.run_pending()
            time.sleep(60)


def main():
    print("🤖 Telegram RSS Bot - Production Version")
    print("=" * 50)

    bot = TelegramRSSBot()

    # АВТОМАТИЧЕСКИ ВЫБИРАЕМ РЕЖИМ 2 (ПО РАСПИСАНИЮ)
    print("🟢 Автоматический запуск по расписанию")
    bot.run_scheduled()


if __name__ == "__main__":
    main()