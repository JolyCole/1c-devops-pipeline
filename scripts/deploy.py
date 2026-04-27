#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Оркестратор развёртывания стенда автоматизации тестирования 1С:Предприятие.

Выполняет последовательное развёртывание всех компонентов CI/CD стенда:
    1. Контейнер PostgreSQL (через docker compose)
    2. Ожидание готовности PostgreSQL через pg_isready
    3. (--full) Запуск сервера 1С:Предприятия как systemd-сервиса
    4. (--full) Ожидание готовности кластера 1С через rac
    5. (--full) Регистрация ИБ в кластере с созданием БД в PostgreSQL через rac
    6. Создание файловой ИБ из выгрузки .dt через ibcmd (для тестов)

Режимы запуска:
    deploy.py           — минимальный стенд: PostgreSQL + файловая ИБ для тестов
    deploy.py --full    — полный стенд: +сервер 1С в systemd, +клиент-серверная ИБ в PG
    deploy.py --cleanup — остановка: docker compose down, systemctl stop srv1cv8/ras

Переменные окружения (все опциональные, есть значения по умолчанию):
    PROJECT_ROOT    — корень проекта (по умолчанию: каталог скрипта/..)
    PLATFORM_PATH   — путь к установленной платформе 1С
    PG_PASSWORD     — пароль пользователя postgres в контейнере
    IB_DT_PATH      — путь к файлу .dt для восстановления
    IB_FILE_PATH    — путь к создаваемой файловой ИБ
    IB_FILE_NAME    — имя ИБ в кластере и БД в PostgreSQL

Коды возврата:
    0 — все этапы выполнены успешно
    1 — ошибка выполнения какого-либо этапа
    2 — некорректные аргументы или окружение
"""

import argparse
import logging
import os
import subprocess
import sys
import time
from pathlib import Path
import shutil


# ──────────────────────────────────────────────────────────────────────────────
# Конфигурация по умолчанию
# ──────────────────────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(
    os.environ.get("PROJECT_ROOT", Path(__file__).resolve().parent.parent)
)
PLATFORM_PATH = os.environ.get("PLATFORM_PATH", "/opt/1cv8/x86_64/8.3.27.1936")

# PostgreSQL
PG_HOST = os.environ.get("PG_HOST", "localhost")
PG_PORT = int(os.environ.get("PG_PORT", "5432"))
PG_USER = os.environ.get("PG_USER", "postgres")
PG_PASSWORD = os.environ.get("PG_PASSWORD", "postgres1c")
PG_CONTAINER = os.environ.get("PG_CONTAINER", "onec-postgres")

# 1C Server (systemd service names from platform install)
SRV1CV8_UNIT = os.environ.get(
    "SRV1CV8_UNIT", "srv1cv8-8.3.27.1936@default.service"
)
RAS_UNIT = os.environ.get("RAS_UNIT", "ras-8.3.27.1936.service")
RAC_HOST_PORT = os.environ.get("RAC_HOST_PORT", "localhost:1545")

# Information base
IB_DT_PATH = Path(
    os.environ.get("IB_DT_PATH", PROJECT_ROOT / "config" / "managed-app.dt")
)
IB_FILE_PATH = Path(
    os.environ.get("IB_FILE_PATH", PROJECT_ROOT / "build" / "ib_managed")
)
IB_FILE_NAME = os.environ.get("IB_FILE_NAME", "managed_app")

# Пути к утилитам платформы
RAC = f"{PLATFORM_PATH}/rac"
IBCMD = f"{PLATFORM_PATH}/ibcmd"

# Настройки ожидания
PG_READY_TIMEOUT = 60       # секунд ожидания pg_isready
RAC_READY_TIMEOUT = 30      # секунд ожидания rac cluster list
POLL_INTERVAL = 2           # пауза между попытками, секунд


# ──────────────────────────────────────────────────────────────────────────────
# Логирование
# ──────────────────────────────────────────────────────────────────────────────

log = logging.getLogger("deploy")


def setup_logging(verbose: bool = False) -> None:
    """Настраивает вывод в stdout + файл deploy.log в корне проекта."""
    level = logging.DEBUG if verbose else logging.INFO
    log_file = PROJECT_ROOT / "deploy.log"

    fmt = "%(asctime)s [%(levelname)s] %(message)s"
    datefmt = "%H:%M:%S"

    logging.basicConfig(
        level=level,
        format=fmt,
        datefmt=datefmt,
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_file, mode="a", encoding="utf-8"),
        ],
    )


# ──────────────────────────────────────────────────────────────────────────────
# Вспомогательные функции для subprocess
# ──────────────────────────────────────────────────────────────────────────────


def run(
    cmd: list[str],
    check: bool = True,
    capture: bool = False,
    timeout: int | None = None,
    cwd: str | Path | None = None,
) -> subprocess.CompletedProcess:
    """
    Запускает внешнюю команду. Логирует команду и результат.

    :param cmd: список аргументов (безопаснее shell=True)
    :param check: при non-zero exit выбросить CalledProcessError
    :param capture: перехватить stdout/stderr (иначе в консоль)
    :param timeout: таймаут в секундах
    :param cwd: рабочий каталог
    :return: CompletedProcess с stdout/stderr если capture=True
    """
    log.debug("RUN: %s", " ".join(str(x) for x in cmd))
    result = subprocess.run(
        cmd,
        check=check,
        capture_output=capture,
        text=True,
        timeout=timeout,
        cwd=cwd,
    )
    if capture:
        log.debug("STDOUT: %s", result.stdout.strip())
        if result.stderr.strip():
            log.debug("STDERR: %s", result.stderr.strip())
    return result


# ──────────────────────────────────────────────────────────────────────────────
# Этап 1-2: PostgreSQL (docker compose + pg_isready)
# ──────────────────────────────────────────────────────────────────────────────


def start_postgres() -> None:
    """Поднимает контейнер PostgreSQL через docker compose."""
    log.info("═══ Этап 1/6: запуск контейнера PostgreSQL ═══")
    run(
        ["docker", "compose", "up", "-d", "postgres"],
        cwd=PROJECT_ROOT,
    )
    log.info("docker compose: PostgreSQL сервис запущен")


def wait_postgres_ready(timeout: int = PG_READY_TIMEOUT) -> None:
    """
    Ожидает готовности PostgreSQL через pg_isready внутри контейнера.
    Выбрасывает TimeoutError если не дождались за timeout секунд.
    """
    log.info("═══ Этап 2/6: ожидание готовности PostgreSQL (до %ds) ═══", timeout)
    deadline = time.time() + timeout

    while time.time() < deadline:
        result = run(
            ["docker", "exec", PG_CONTAINER, "pg_isready", "-U", PG_USER],
            check=False,
            capture=True,
            timeout=10,
        )
        if result.returncode == 0:
            log.info("PostgreSQL готов: %s", result.stdout.strip())
            return
        log.debug("PostgreSQL ещё не готов (rc=%d), ждём…", result.returncode)
        time.sleep(POLL_INTERVAL)

    raise TimeoutError(
        f"PostgreSQL не готов за {timeout}с. Проверьте 'docker logs {PG_CONTAINER}'"
    )


# ──────────────────────────────────────────────────────────────────────────────
# Этап 3-5: сервер 1С (systemd) + кластер + ИБ в PostgreSQL (rac)
# Запускаются только в режиме --full
# ──────────────────────────────────────────────────────────────────────────────


def start_onec_server() -> None:
    """Запускает systemd-сервисы srv1cv8 и ras."""
    log.info("═══ Этап 3/6: запуск сервера 1С:Предприятия (systemd) ═══")

    for unit in (SRV1CV8_UNIT, RAS_UNIT):
        log.info("sudo systemctl start %s", unit)
        run(["sudo", "systemctl", "start", unit])

    # Короткая пауза на инициализацию процессов ragent/rphost/rmngr
    time.sleep(3)

    # Убедимся что сервисы активны
    for unit in (SRV1CV8_UNIT, RAS_UNIT):
        result = run(
            ["systemctl", "is-active", unit],
            check=False,
            capture=True,
        )
        state = result.stdout.strip()
        if state != "active":
            raise RuntimeError(
                f"systemd-сервис {unit} в состоянии '{state}' (ожидалось 'active'). "
                f"Проверьте 'journalctl -u {unit} -n 30'"
            )
        log.info("%s: %s", unit, state)


def wait_rac_ready(timeout: int = RAC_READY_TIMEOUT) -> str:
    """
    Дожидается доступности ras и возвращает UUID кластера.

    :return: UUID кластера
    :raises TimeoutError: если rac не отвечает за timeout секунд
    :raises RuntimeError: если rac не вернул UUID
    """
    log.info("═══ Этап 4/6: ожидание готовности кластера 1С ═══")
    deadline = time.time() + timeout

    while time.time() < deadline:
        result = run(
            [RAC, "cluster", "list", RAC_HOST_PORT],
            check=False,
            capture=True,
            timeout=10,
        )
        if result.returncode == 0 and "cluster" in result.stdout:
            # Парсим строку формата "cluster : <uuid>"
            for line in result.stdout.splitlines():
                if line.strip().startswith("cluster"):
                    parts = line.split(":", 1)
                    if len(parts) == 2:
                        uuid = parts[1].strip()
                        log.info("Кластер доступен: UUID=%s", uuid)
                        return uuid
            raise RuntimeError(
                "rac cluster list вернул ответ без UUID:\n" + result.stdout
            )
        log.debug("rac cluster list не готов, ждём…")
        time.sleep(POLL_INTERVAL)

    raise TimeoutError(
        f"Кластер 1С не готов за {timeout}с. "
        f"Проверьте 'systemctl status {SRV1CV8_UNIT}'"
    )


def register_infobase_in_cluster(cluster_uuid: str) -> None:
    """
    Регистрирует клиент-серверную ИБ в кластере с созданием БД в PostgreSQL.
    Идемпотентно: если ИБ с таким именем уже есть — пропускает.
    """
    log.info("═══ Этап 5/6: регистрация ИБ '%s' в PostgreSQL ═══", IB_FILE_NAME)

    # Проверка идемпотентности
    result = run(
        [
            RAC,
            "infobase",
            f"--cluster={cluster_uuid}",
            "summary",
            "list",
            RAC_HOST_PORT,
        ],
        capture=True,
    )
    if f"name     : {IB_FILE_NAME}" in result.stdout:
        log.info("ИБ '%s' уже зарегистрирована в кластере — пропускаем", IB_FILE_NAME)
        return

    # Создание
    run(
        [
            RAC,
            "infobase",
            f"--cluster={cluster_uuid}",
            "create",
            "--create-database",
            f"--name={IB_FILE_NAME}",
            f"--descr=Информационная база для автоматизированного тестирования",
            "--dbms=PostgreSQL",
            f"--db-server={PG_HOST}",
            f"--db-name={IB_FILE_NAME}",
            "--locale=ru_RU",
            f"--db-user={PG_USER}",
            f"--db-pwd={PG_PASSWORD}",
            "--license-distribution=allow",
            RAC_HOST_PORT,
        ]
    )
    log.info("ИБ '%s' зарегистрирована в кластере и БД создана в PostgreSQL", IB_FILE_NAME)


# ──────────────────────────────────────────────────────────────────────────────
# Этап 6: файловая ИБ через ibcmd (используется для автоматических тестов)
# ──────────────────────────────────────────────────────────────────────────────


def create_file_infobase() -> None:
    """
    Создаёт файловую ИБ и восстанавливает в неё данные из .dt-выгрузки.
    Идемпотентно: если ИБ уже существует — пересоздаёт с нуля (иначе ibcmd падает).
    """
    log.info("═══ Этап 6/6: создание файловой ИБ из %s ═══", IB_DT_PATH.name)

    if not IB_DT_PATH.is_file():
        raise FileNotFoundError(
            f"Файл выгрузки ИБ не найден: {IB_DT_PATH}. "
            f"Поместите .dt в config/ или задайте IB_DT_PATH."
        )

    # Если каталог ИБ уже есть — очищаем (файловая ИБ хранится в 1Cv8.1CD)
    if IB_FILE_PATH.exists() and any(IB_FILE_PATH.iterdir()):
        log.info("Каталог %s не пуст, очищаем для пересборки", IB_FILE_PATH)
        for item in IB_FILE_PATH.iterdir():
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()
    else:
        IB_FILE_PATH.mkdir(parents=True, exist_ok=True)

    run(
        [
            IBCMD,
            "infobase",
            "create",
            f"--database-path={IB_FILE_PATH}",
            f"--restore={IB_DT_PATH}",
            "--locale=ru_RU",
        ]
    )

    # Убедимся что файл 1Cv8.1CD создан
    cd_file = IB_FILE_PATH / "1Cv8.1CD"
    if not cd_file.is_file():
        raise RuntimeError(f"Файл {cd_file} не появился после ibcmd create")

    size_mb = cd_file.stat().st_size // (1024 * 1024)
    log.info("Файловая ИБ создана: %s (%d МБ)", cd_file, size_mb)


# ──────────────────────────────────────────────────────────────────────────────
# Команда --cleanup
# ──────────────────────────────────────────────────────────────────────────────


def cleanup() -> None:
    """Останавливает все подсистемы стенда (обратный порядок)."""
    log.info("═══ Cleanup: остановка стенда ═══")

    # 1. systemd-сервисы 1С (best-effort, если не запущены — не страшно)
    for unit in (RAS_UNIT, SRV1CV8_UNIT):
        log.info("Останавливаем %s", unit)
        run(["sudo", "systemctl", "stop", unit], check=False)

    # 2. docker compose
    log.info("docker compose down")
    run(["docker", "compose", "down"], cwd=PROJECT_ROOT, check=False)

    log.info("Стенд остановлен")


# ──────────────────────────────────────────────────────────────────────────────
# CLI / main
# ──────────────────────────────────────────────────────────────────────────────


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Полное развёртывание: PostgreSQL + сервер 1С (systemd) "
        "+ клиент-серверная ИБ в PG + файловая ИБ (по умолчанию только PG + файловая)",
    )
    parser.add_argument(
        "--cleanup",
        action="store_true",
        help="Остановить стенд (docker compose down, systemctl stop) и выйти",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Подробное логирование (DEBUG)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    setup_logging(verbose=args.verbose)

    log.info("deploy.py: стартуем развёртывание стенда")
    log.info("PROJECT_ROOT  = %s", PROJECT_ROOT)
    log.info("PLATFORM_PATH = %s", PLATFORM_PATH)

    # Режим cleanup
    if args.cleanup:
        try:
            cleanup()
            return 0
        except Exception as exc:
            log.error("Ошибка cleanup: %s", exc)
            return 1

    # Основной flow развёртывания
    try:
        # Этапы 1-2: PostgreSQL всегда
        start_postgres()
        wait_postgres_ready()

        # Этапы 3-5: только в режиме --full
        if args.full:
            start_onec_server()
            cluster_uuid = wait_rac_ready()
            register_infobase_in_cluster(cluster_uuid)
        else:
            log.info("═══ Этапы 3-5 пропущены (запустите с --full для сервера 1С) ═══")

        # Этап 6: файловая ИБ всегда
        create_file_infobase()

        log.info("═══ Развёртывание стенда завершено успешно ═══")
        return 0

    except subprocess.CalledProcessError as exc:
        log.error("Внешняя команда завершилась с ошибкой (rc=%d):", exc.returncode)
        log.error("  Команда: %s", " ".join(str(x) for x in exc.cmd))
        if exc.stderr:
            log.error("  stderr: %s", exc.stderr.strip())
        return 1
    except (TimeoutError, FileNotFoundError, RuntimeError) as exc:
        log.error("Ошибка этапа развёртывания: %s", exc)
        return 1
    except KeyboardInterrupt:
        log.warning("Прервано пользователем")
        return 130


if __name__ == "__main__":
    sys.exit(main())