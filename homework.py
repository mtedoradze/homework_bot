from datetime import datetime
from http import HTTPStatus
import json
import logging
from pickle import FALSE
import requests
import os
from dotenv import load_dotenv
import time
from telegram import Bot
from exceptions import NoEnvVariablesException, NotExpectedKeysException, NoNewStatusException, NoResponseException, NotDefinedStatusException

load_dotenv()


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

logging.basicConfig(
    level=logging.DEBUG,
    filename='main.log',
    filemode='w',
    format='%(asctime)s, %(levelname)s, %(message)s, %(name)s'
)


def send_message(bot, message):
    """Отправляет сообщение в Telegram чат"""
    bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)


def get_api_answer(current_timestamp) -> dict:
    """Делает запрос, возвращает ответ API."""
    timestamp: datetime = current_timestamp
    params: dict = {'from_date': timestamp}
    homework_statuses: json = requests.get(
        url=ENDPOINT,
        headers=HEADERS,
        params=params
    )
    return homework_statuses.json()


def check_response(response) -> list:
    """Проверяет ответ API на корректность,
    возвращает список домашних работ."""
    return response['homeworks']


def parse_status(homework) -> str:
    """Извлекает из информации о конкретной домашней работе
    статус этой работы, возвращает подготовленную для отправки
    в Telegram строку."""
    homework_name = homework[0]['homework_name']
    for homework_status in HOMEWORK_STATUSES:
        homework_status = homework[0]['status']
        verdict = HOMEWORK_STATUSES[homework_status]
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def check_tokens(env_variables) -> bool:
    """Проверяет доступность переменных окружения,
    которые необходимы для работы программы."""
    for key, value in env_variables:
        if value == 0 or value == '':
            return False
        return True


def main() -> str:
    """Основная логика работы бота."""
    bot = Bot(token=TELEGRAM_TOKEN)
    env_variables = (
        ('practicum_token', PRACTICUM_TOKEN),
        ('telegram_token', TELEGRAM_TOKEN),
        ('telegram_chat_id', TELEGRAM_CHAT_ID)
    )
    tokens = check_tokens(env_variables)
    if not tokens:
        logging.critical('Отсутствует обязательная переменная окружения: '
                         f'{tokens}'
                         'Программа принудительно остановлена.')
        raise NoEnvVariablesException

    try:
        current_timestamp = int(time.time()) - 60*60*24*30
        response = get_api_answer(current_timestamp)
        logging.debug('Получен ответ API в формате json')

        if len(check_response(response)) == 0:
            logging.debug('Отсутствие в ответе новых статусов')
            message = f'Отсутствие в ответе новых статусов'
            current_timestamp = response['current_date']
            time.sleep(RETRY_TIME)
            main()
            return message

        if 'status' and 'homework_name' not in check_response(response)[0]:
            logging.error('Отсутствуют ожидаемые ключи в ответе API')
            raise NotExpectedKeysException(
                'Отсутствуют ожидаемые ключи в ответе API'
            )
        logging.debug('Выполнена проверка основных условий главной функции')
        homework = check_response(response)
        logging.debug('Извлечен список работ')
    
    except Exception as error:
        message = f'Сбой в работе программы: {error}'
        logging.error(f'Сбой в работе программы: {error}')
        return message

    else:
        if homework[0]['status'] not in HOMEWORK_STATUSES:
            logging.error('Недокументированный статус домашней работы, '
                          'обнаруженный в ответе API')
            raise NotDefinedStatusException(
                'Недокументированный статус домашней работы'
            )
        message = parse_status(homework)
        logging.debug(f'{message}')
        try:
            send_message(bot, message)
            logging.info('Сообщение отправлено')
        except Exception:
            logging.error('Бот не смог отправить сообщение')
    time.sleep(RETRY_TIME)


if __name__ == '__main__':
    main()
