# Автоматизация тестирования конфигураций 1С:Предприятие с использованием DevOps-инструментов

Практическая часть выпускной квалификационной работы.

**Автор:** Филимонов И. Д., МТУСИ, 2026
**Тема:** Разработка метода автоматизации тестирования конфигураций 1С:Предприятие с использованием DevOps-инструментов
**Платформа:** 1С:Предприятие 8.3.27.1936

---

## Описание

Проект демонстрирует метод автоматизированного тестирования конфигураций 1С:Предприятие в рамках CI/CD-конвейера. Конвейер автоматически собирает информационные базы из исходников, разворачивает тестовый стенд, прогоняет BDD-сценарии и статический анализ, после чего агрегирует результаты в единый отчёт.

Метод проверяется на трёх конфигурациях, что показывает его универсальность:

- **Управляемое приложение (УП)** — основная конфигурация, проходит полный цикл: сборка из `.dt`, развёртывание стенда и все виды тестирования.
- **DemoVKR** — референсная конфигурация из XML-исходников, проходит статический анализ.
- **Мобильная конфигурация** — референсная конфигурация из `.cf`, проходит статический анализ.

---

## Архитектура конвейера

Конвейер GitLab CI/CD состоит из четырёх последовательных стадий:
build -> deploy -> test -> report

**build** — сборка файловых информационных баз из трёх конфигураций (`ibcmd` и `vanessa-runner`).

**deploy** — развёртывание тестового стенда: запуск PostgreSQL в Docker и создание файловой ИБ из дампа (`scripts/deploy.py`).

**test** — тестирование: BDD-сценарии для УП через Vanessa-Automation (smoke, regression, functional) и статический синтаксический анализ всех трёх конфигураций.

**report** — агрегация JUnit-отчётов всех тестовых задач в единый HTML-отчёт.

---

## Стек технологий

- **1С:Предприятие 8.3.27.1936** — тестируемая платформа (headless-режим под Xvfb).
- **WSL2 (Ubuntu)** — среда исполнения.
- **OneScript + vanessa-runner 2.6.0** — оркестрация запусков 1С из командной строки.
- **Vanessa-Automation** — фреймворк BDD-тестирования (Gherkin-сценарии).
- **Docker** — контейнеризация PostgreSQL (`onec-postgres`).
- **GitLab CI/CD** — конвейер и self-hosted runner (shell-executor).
- **Python 3** — скрипты развёртывания и агрегации отчётов.

---

## Структура репозитория
.
├── .gitlab-ci.yml          # описание CI/CD-конвейера (4 стадии)
├── docker-compose.yml      # PostgreSQL для тестового стенда
├── config/                 # конфигурации для тестирования
│   ├── managed-app.dt      # дамп управляемого приложения
│   ├── demo-config/        # DemoVKR (XML-исходники)
│   ├── demo-config.cf      # DemoVKR (cf)
│   └── mobile-demo.cf      # мобильная конфигурация
├── docker/                 # Dockerfile'ы и дистрибутивы
│   ├── postgres/           # образ PostgreSQL для 1С
│   ├── onec/               # образ для тестирования 1С
│   ├── platform/           # дистрибутивы платформы 1С и PostgreSQL
│   └── licenses/           # лицензии 1С
├── scripts/
│   ├── deploy.py           # развёртывание стенда (PostgreSQL + ИБ)
│   ├── manage_db.py        # управление базами данных
│   ├── run_vanessa.sh      # запуск Vanessa-Automation
│   └── 1c/create_admin.os  # создание администратора (OneScript)
├── tests/
│   ├── VAParams.json       # параметры Vanessa-Automation
│   └── features/           # BDD-сценарии (Gherkin)
│       ├── smoke/          # открытие ключевых форм
│       ├── regression/     # CRUD-операции справочников
│       └── functional/     # бизнес-сценарии навигации
└── reports/                # результаты тестов (JUnit, статусы, HTML)

---

## Требования

- WSL2 с Ubuntu;
- 1С:Предприятие 8.3.27.1936 в `/opt/1cv8/`;
- действующая лицензия 1С (`.lic`);
- OneScript с установленным пакетом `vanessa-runner`;
- Vanessa-Automation в `tools/vanessa/`;
- Docker с образом `onec-postgres`;
- Python 3, Xvfb;
- системная локаль `ru_RU.UTF-8`;
- зарегистрированный GitLab Runner (shell-executor).

Дистрибутивы платформы 1С и PostgreSQL для сборки Docker-образов находятся в `docker/platform/`.

---

## Запуск

### Через GitLab CI/CD (основной способ)

Любой push в ветку `main` запускает конвейер автоматически:
git push origin main

Ручной перезапуск без изменений в коде:
git commit --allow-empty -m "rerun pipeline"
git push origin main

Состояние конвейера: https://gitlab.com/JolyCole/1c-devops-pipeline/-/pipelines

### Локальное развёртывание стенда
python3 scripts/deploy.py            # PostgreSQL + файловая ИБ из managed-app.dt
python3 scripts/deploy.py --full     # дополнительно сервер 1С

### Локальный прогон BDD-тестов
xvfb-run -a ./scripts/run_vanessa.sh tests/features/smoke/01_managed_smoke.feature
xvfb-run -a ./scripts/run_vanessa.sh tests/features/regression/01_managed_crud.feature
xvfb-run -a ./scripts/run_vanessa.sh tests/features/functional/01_managed_search.feature

---

## Просмотр результатов
cat reports/vanessa/junit/junit.xml     # JUnit-отчёт BDD-прогона
cat reports/vanessa/logs/status.txt     # код статуса (0 = успех)
cat reports/syntax-managed.xml          # результат статического анализа

Сводный HTML-отчёт формируется на стадии report и доступен в артефактах конвейера (`reports/html/aggregated-report.html`).

---

## Диагностика
sudo gitlab-runner status               # состояние GitLab Runner
docker compose ps                        # контейнер PostgreSQL
docker logs onec-postgres                # логи PostgreSQL
pkill -9 -f "1cv8c.*TESTCLIENT"          # снять зависшие процессы 1С
pkill -9 -f "vrunner"

---

## Тестовые сценарии

| Вид        | Файл                                                  | Что проверяет                                  |
|------------|-------------------------------------------------------|------------------------------------------------|
| Smoke      | tests/features/smoke/01_managed_smoke.feature         | Открытие ключевых форм управляемого приложения |
| Regression | tests/features/regression/01_managed_crud.feature     | CRUD-операции над справочниками                |
| Functional | tests/features/functional/01_managed_search.feature   | Навигация, поиск, стабильность интерфейса      |
