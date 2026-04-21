#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Управление информационной базой 1С для CI/CD пайплайна.

Поддерживает два режима работы ИБ:
    file     - файловая ИБ на диске (по умолчанию, для автоматических тестов)
    postgres - клиент-серверная ИБ на PostgreSQL (для демонстрации архитектуры)

Команды:
    create    - создать пустую ИБ и загрузить конфигурацию из XML
    drop      - удалить ИБ
    recreate  - drop + create (полная пересборка, для чистого прогона тестов)
    status    - проверить что ИБ доступна

Переменные окружения:
    DB_MODE      - режим работы ИБ: file | postgres (по умолчанию file)
    IB_PATH      - путь к файловой ИБ (для file режима)
    DB_HOST, DB_NAME, DB_USER, DB_PASSWORD - параметры PostgreSQL (для postgres режима)
    ONEC_BIN     - путь к ibcmd в контейнере
    CONFIG_DIR   - путь к XML-конфигурации
"""

import argparse
import logging
import os
import shutil
import subprocess
import sys


# Режим работы ИБ (file / postgres). По умолчанию file,
# так как headless-запуск thick-клиента 1С на Linux в клиент-серверном
# режиме требует дополнительной настройки (публикация на веб-сервере либо
# промышленная серверная лицензия). Для CI-тестирования используется
# файловый режим, клиент-серверная часть реализована как демонстрация
# полного development-стенда.
DB_MODE = os.environ.get("DB_MODE", "file")

# Общие параметры
ONEC_BIN = os.environ.get("ONEC_BIN", "/opt/1cv8/x86_64/8.3.27.1936/ibcmd")
CONFIG_DIR = os.environ.get("CONFIG_DIR", "/workspace/config/demo-config")

# Параметры файлового режима
IB_PATH = os.environ.get("IB_PATH", "/var/1C/infobases/demo_vkr")

# Параметры PostgreSQL режима
DB_HOST = os.environ.get("DB_HOST", "postgres")
DB_NAME = os.environ.get("DB_NAME", "demo_vkr")
DB_USER = os.environ.get("DB_USER", "postgres")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "postgres1c")


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("manage_db")


def db_flags():
    """Параметры подключения к ИБ в зависимости от режима."""
    if DB_MODE == "file":
        return [f"--db-path={IB_PATH}"]
    elif DB_MODE == "postgres":
        return [
            "--dbms=PostgreSQL",
            f"--database-server={DB_HOST}",
            f"--database-name={DB_NAME}",
            f"--database-user={DB_USER}",
            f"--database-password={DB_PASSWORD}",
        ]
    else:
        log.error("Неизвестный DB_MODE='%s' (ожидается file или postgres)", DB_MODE)
        sys.exit(2)


def run_ibcmd(args, check=True):
    """Запустить ibcmd с параметрами текущего режима."""
    cmd = [ONEC_BIN, "infobase", *args, *db_flags()]
    log.info("Запуск: ibcmd infobase %s", " ".join(args))
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.stdout:
        for line in result.stdout.strip().split("\n"):
            log.info("  %s", line)
    if result.stderr:
        for line in result.stderr.strip().split("\n"):
            log.warning("  %s", line)
    if check and result.returncode != 0:
        log.error("ibcmd вернул код %d", result.returncode)
        sys.exit(result.returncode)
    return result


def cmd_create():
    """Создание новой ИБ с загрузкой конфигурации из XML."""
    if DB_MODE == "file":
        log.info("Создание файловой ИБ в '%s'", IB_PATH)
        os.makedirs(IB_PATH, exist_ok=True)
        run_ibcmd([
            "create",
            f"--import={CONFIG_DIR}",
            "--apply",
            "--force",
        ])
    else:
        log.info("Создание ИБ '%s' на PostgreSQL @ %s", DB_NAME, DB_HOST)
        run_ibcmd([
            "create",
            "--create-database",
            f"--import={CONFIG_DIR}",
            "--apply",
            "--force",
        ])
    log.info("ИБ создана и конфигурация загружена")


def cmd_drop():
    """Удаление ИБ в зависимости от режима."""
    if DB_MODE == "file":
        log.info("Удаление файловой ИБ '%s'", IB_PATH)
        if os.path.exists(IB_PATH):
            for entry in os.listdir(IB_PATH):
                full = os.path.join(IB_PATH, entry)
                if os.path.isdir(full):
                    shutil.rmtree(full)
                else:
                    os.remove(full)
            log.info("Каталог ИБ очищен")
        else:
            log.info("Каталог ИБ не существует, пропускаем")
    else:
        import psycopg2
        from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

        log.info("Удаление базы данных '%s' в PostgreSQL", DB_NAME)
        try:
            conn = psycopg2.connect(
                host=DB_HOST, user=DB_USER, password=DB_PASSWORD, dbname="postgres"
            )
            conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
            cur = conn.cursor()
            cur.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = %s AND pid <> pg_backend_pid();", (DB_NAME,)
            )
            cur.execute(f"DROP DATABASE IF EXISTS {DB_NAME};")
            cur.close()
            conn.close()
            log.info("База '%s' удалена", DB_NAME)
        except Exception as exc:
            log.error("Ошибка удаления БД: %s", exc)
            sys.exit(1)


def cmd_recreate():
    """Полная пересборка - удалить и создать заново."""
    log.info("Пересборка информационной базы")
    cmd_drop()
    cmd_create()


def cmd_status():
    """Проверка доступности ИБ через экспорт конфигурации."""
    log.info("Проверка доступности ИБ")
    cmd = [ONEC_BIN, "config", "export", *db_flags(), "/tmp/status-check"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        log.info("ИБ доступна и отвечает корректно")
    else:
        log.error("ИБ недоступна: %s", result.stderr.strip())
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Управление ИБ 1С")
    parser.add_argument(
        "action",
        choices=["create", "drop", "recreate", "status"],
        help="Действие над информационной базой",
    )
    args = parser.parse_args()

    log.info("=" * 60)
    log.info("Параметры:")
    log.info("  Режим: %s", DB_MODE)
    if DB_MODE == "file":
        log.info("  Путь к ИБ: %s", IB_PATH)
    else:
        log.info("  PostgreSQL: %s@%s / %s", DB_USER, DB_HOST, DB_NAME)
    log.info("  Config: %s", CONFIG_DIR)
    log.info("  ibcmd: %s", ONEC_BIN)
    log.info("=" * 60)

    actions = {
        "create": cmd_create,
        "drop": cmd_drop,
        "recreate": cmd_recreate,
        "status": cmd_status,
    }
    actions[args.action]()


if __name__ == "__main__":
    main()
