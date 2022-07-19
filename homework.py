from functools import wraps
from http import HTTPStatus
import json
import logging
import os
import sys
import time
from urllib.error import URLError

from dotenv import load_dotenv
import requests
from telegram import Bot
from telegram import TelegramError

import exceptions

load_dotenv()

TIME_DIFF_TWO_DAYS = 60 * 60 * 24 * 2

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
    """Кэширование отправленных ботом сообщений."""
    cache = {}
    cache[func.__name__] = {}

    @wraps(func)
    def wrapper(*args):
        if args not in cache[func.__name__]:
            cache[func.__name__][args] = func(*args)
    return wrapper


@cache_messages
def send_message(bot, message):
    """Отправляет сообщение в Telegram чат, если оно новое."""
    try:
        sent_message = bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
        if sent_message:
            logger.info(f'Бот отправил сообщение: "{message}"')
    except TelegramError as error:
        raise TelegramError(f'Бот не смог отправить сообщение: {error}')


def get_api_answer(current_timestamp) -> dict:
    """Делает запрос, возвращает ответ API."""
    timestamp: int = current_timestamp
    params: dict = {'from_date': timestamp}
    try:
        homework_statuses: json = requests.get(
            url=ENDPOINT,
            headers=HEADERS,
            params=params
        )
    except ConnectionError:
        raise ConnectionError('Недоступность эндпоинта')
    if homework_statuses.status_code != HTTPStatus.OK:
        raise URLError(f'Недоступность эндпоинта {ENDPOINT}')
    try:
        response = homework_statuses.json()
    except ValueError:
        raise ValueError('Ответ API не в формате json')
    return response


def check_response(response) -> list:
    """Проверяет ответ API на корректность.

    Возвращает список домашних работ.
    """
    try:
        homeworks = response['homewor']
        if not type(homeworks) is list:
            raise exceptions.NotDefinedStatusException(
                'Недокументированный статус домашней работы'
            )
        if len(homeworks) == 0:
            raise exceptions.NoNewStatusException(
                'Отсутствие в ответе новых статусов'
            )
        logger.debug('Извлечен список работ')
    except KeyError:
        raise KeyError('Отсутствие ожидаемых ключей в ответе API')
    return homeworks


def parse_status(homework) -> str:
    """Извлекает из информации о конкретной домашней работе ее статус.

    Возвращает подготовленную для отправки в Telegram строку.
    """
    if 'status' not in homework or 'homework_name' not in homework:
        raise KeyError('Отсутствие ожидаемых ключей в ответе API')
    homework_status = homework['status']

    if homework_status not in HOMEWORK_STATUSES:
        raise exceptions.NotDefinedStatusException(
            'Недокументированный статус домашней работы'
        )
    verdict = HOMEWORK_STATUSES[homework_status]
    homework_name = homework['homework_name']

    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def check_tokens() -> bool:
    """Проверяет доступность необходимых переменных окружения."""
    env_variables = (
        ('practicum_token', PRACTICUM_TOKEN),
        ('telegram_token', TELEGRAM_TOKEN),
        ('telegram_chat_id', TELEGRAM_CHAT_ID)
    )
    for key, value in env_variables:
        if value == '' or value is None:
            logger.critical(
                'Отсутствует обязательная переменная окружения: '
                f'{key}. '
                'Программа принудительно остановлена.'
            )
    return all((PRACTICUM_TOKEN, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID))


def main(current_timestamp):
    """Основная логика работы бота.

    Вызывает поочередно функции:
    Проверка наличия токенов, запрос к API,
    получение списка работ из ответа API,
    получение информации о статусе последней работы,
    отправка сообщения в телеграм.
    """
    if not check_tokens():
        raise exceptions.NoEnvVariablesException(
            'Отсутствует обязательная переменная окружения'
        )

    bot = Bot(token=TELEGRAM_TOKEN)

    while True:
        try:
            response = get_api_answer(current_timestamp)
            logger.debug('Получен ответ API в формате json')
            homeworks = check_response(response)
            homework = homeworks[0]
            message = parse_status(homework)
            current_timestamp = response['current_date']

        except exceptions.NoNewStatusException as status:
            logger.debug(status)
            message = str(status)

        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            logger.error(message)

        finally:
            try:
                send_message(bot, message)
            except Exception as error:
                logger.error(error)
            time.sleep(RETRY_TIME)
            main(current_timestamp)


if __name__ == '__main__':
    main(current_timestamp=int(time.time()) - TIME_DIFF_TWO_DAYS)
