from datetime import datetime
from functools import wraps
import json
import logging
import sys
import requests
import os
from dotenv import load_dotenv
import time
from telegram import Bot
from exceptions import NoEnvVariablesException

load_dotenv()

TIME_DIFF = 60 * 60 * 24 * 30

PRACTICUM_TOKEN: str = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN: str = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID: int = os.getenv('TELEGRAM_CHAT_ID')

RETRY_TIME: int = 600
ENDPOINT: str = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS: dict = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}


HOMEWORK_STATUSES: dict = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}

logger = logging.getLogger()
handler = logging.StreamHandler(sys.stdout)
logger.addHandler(handler)
logger.setLevel(logging.DEBUG)
formatter = logging.Formatter(
    '%(asctime)s, %(levelname)s, %(message)s, %(name)s'
)
handler.setFormatter(formatter)


def cache_messages(func):
    cache = {}
    cache[func.__name__] = {}

    @wraps(func)
    def wrapper(*args):
        if args not in cache[func.__name__]:
            cache[func.__name__][args] = func(*args)
        time.sleep(RETRY_TIME)
        main()
    return wrapper


@cache_messages
def send_message(bot, message):
    """Отправляет сообщение в Telegram чат"""
    success = bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
    if success:
        logger.info(f'Бот отправил сообщение: "{message}"')


def get_api_answer(current_timestamp) -> dict:
    """Делает запрос, возвращает ответ API."""
    try:
        timestamp: datetime = current_timestamp or int(time.time())
        params: dict = {'from_date': timestamp}
        homework_statuses: json = requests.get(
            url=ENDPOINT,
            headers=HEADERS,
            params=params
        )
    except Exception:
        logging.error(f'Недоступность эндпоинта {ENDPOINT}')

    return homework_statuses.json()


def check_response(response) -> list:
    """Проверяет ответ API на корректность,
    возвращает список домашних работ."""
    homework = response['homeworks']
    logger.debug('Извлечен список работ')
    return homework


def parse_status(homework) -> str:
    """Извлекает из информации о конкретной домашней работе
    статус этой работы, возвращает подготовленную для отправки
    в Telegram строку."""
    try:
        if len(homework) == 0:
            message = 'Отсутствие в ответе новых статусов'
            logger.debug(message)
            return message
        if homework[0]['status'] not in HOMEWORK_STATUSES:
            message = 'Недокументированный статус домашней работы'
            logger.error(message)
            return message
        homework_name = homework[0]['homework_name']
        for homework_status in HOMEWORK_STATUSES:
            homework_status = homework[0]['status']
            verdict = HOMEWORK_STATUSES[homework_status]
        message = (
            f'Изменился статус проверки работы "{homework_name}". {verdict}'
        )
    except KeyError:
        message = 'Отсутствуют ожидаемые ключи в ответе API'
        logger.error(message)
    return message


def check_tokens(value) -> bool:
    """Проверяет доступность переменных окружения,
    которые необходимы для работы программы."""
    if value == '':
        return False
    return True


def main():
    """Основная логика работы бота. Вызывает поочередно функции:
    Проверка наличия токенов, запрос к API,
    получение списка работ из ответа API,
    получение информации о статусе последней работы,
    отправка сообщения в телеграм"""
    env_variables = (
        ('practicum_token', PRACTICUM_TOKEN),
        ('telegram_token', TELEGRAM_TOKEN),
        ('telegram_chat_id', TELEGRAM_CHAT_ID)
    )
    for key, value in env_variables:
        token = check_tokens(value)
        if not token:
            logger.critical('Отсутствует обязательная переменная окружения: '
                            f'{key}. '
                            'Программа принудительно остановлена.')
            raise NoEnvVariablesException

    bot = Bot(token=TELEGRAM_TOKEN)
    current_timestamp = int(time.time()) - TIME_DIFF

    while True:
        try:
            response = get_api_answer(current_timestamp)
            logger.debug('Получен ответ API в формате json')
            homework = check_response(response)
            message = parse_status(homework)
            current_timestamp = response['current_date']
            try:
                send_message(bot, message)
            except Exception:
                logger.error('Бот не смог отправить сообщение')

            time.sleep(RETRY_TIME)

        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            logger.error(message)
            time.sleep(RETRY_TIME)


if __name__ == '__main__':
    main()
