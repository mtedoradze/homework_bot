from datetime import datetime
from functools import wraps
from http import HTTPStatus
import json
import logging
import sys
import requests
import os
from dotenv import load_dotenv
import time
from telegram import Bot
from exceptions import (
    NoEnvVariablesException,
    NoNewStatusException,
    NotDefinedStatusException
)

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
    """Кэширование отправленных ботом сообщений."""
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
    """Отправляет сообщение в Telegram чат, если оно новое."""
    success = bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
    if success:
        logger.info(f'Бот отправил сообщение: "{message}"')


def get_api_answer(current_timestamp) -> dict:
    """Делает запрос, возвращает ответ API."""
    timestamp: datetime = current_timestamp or int(time.time())
    params: dict = {'from_date': timestamp}
    homework_statuses: json = requests.get(
        url=ENDPOINT,
        headers=HEADERS,
        params=params
    )
    if homework_statuses.status_code != HTTPStatus.OK:
        raise ConnectionError
    return homework_statuses.json()


def check_response(response) -> list:
    """Проверяет ответ API на корректность.
    Возвращает список домашних работ.
    """
    homeworks = response['homeworks']
    if type(homeworks) != list:
        raise NotDefinedStatusException
    if len(homeworks) == 0:
        raise NoNewStatusException
    logger.debug('Извлечен список работ')
    return homeworks


def parse_status(homework) -> str:
    """Извлекает из информации о конкретной домашней работе ее статус.
    Возвращает подготовленную для отправки в Telegram строку.
    """
    if 'status' not in homework or 'homework_name' not in homework:
        raise KeyError
    homework_status = homework['status']

    if homework_status not in HOMEWORK_STATUSES.keys():
        raise NotDefinedStatusException
    verdict = HOMEWORK_STATUSES[homework_status]
    homework_name = homework['homework_name']

    return (f'Изменился статус проверки работы "{homework_name}". {verdict}')


def check_tokens() -> bool:
    """Проверяет доступность необходимых переменных окружения."""
    env_variables = (
        ('practicum_token', PRACTICUM_TOKEN),
        ('telegram_token', TELEGRAM_TOKEN),
        ('telegram_chat_id', TELEGRAM_CHAT_ID)
    )
    for key, value in env_variables:
        if value == '':
            logger.critical('Отсутствует обязательная переменная окружения: '
                            f'{key}. '
                            'Программа принудительно остановлена.')
            raise NoEnvVariablesException
    return all((PRACTICUM_TOKEN, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID))


def main():
    """Основная логика работы бота.
    Вызывает поочередно функции:
    Проверка наличия токенов, запрос к API,
    получение списка работ из ответа API,
    получение информации о статусе последней работы,
    отправка сообщения в телеграм.
    """
    check_tokens()
    bot = Bot(token=TELEGRAM_TOKEN)
    current_timestamp = int(time.time())

    while True:
        try:
            response = get_api_answer(current_timestamp)
            logger.debug('Получен ответ API в формате json')
            homeworks = check_response(response)
            homework = homeworks[0]
            message = parse_status(homework)
            current_timestamp = response['current_date']
        except NoEnvVariablesException:
            pass
        except NoNewStatusException:
            message = 'Отсутствие в ответе новых статусов'
            logger.debug(message)
            return message
        except KeyError:
            message = 'Отсутствие ожидаемых ключей в ответе API'
            logger.error(message)
            return message
        except NotDefinedStatusException:
            message = 'Недокументированный статус домашней работы'
            logger.error(message)
            return message
        except ConnectionError:
            message = f'Недоступность эндпоинта {ENDPOINT}'
            logger.error(message)
            return message
        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            logger.error(message)
            time.sleep(RETRY_TIME)
        finally:
            try:
                send_message(bot, message)
            except Exception:
                logger.error('Бот не смог отправить сообщение')
            time.sleep(RETRY_TIME)


if __name__ == '__main__':
    main()
