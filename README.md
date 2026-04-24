# 1C DevOps Pipeline

CI/CD-конвейер для автоматизированного тестирования конфигураций 1С:Предприятие 8.3 с использованием Docker, GitLab CI/CD, Vanessa-Automation и vanessa-runner.

Выпускная квалификационная работа бакалавра. Филимонов И.Д., МТУСИ, 2026.

---

## Что это делает

- Автоматически проверяет синтаксис конфигураций 1С (`vrunner syntax-check`)
- Прогоняет BDD-сценарии на русском Gherkin через Vanessa-Automation
- Формирует отчёты в формате JUnit XML для GitLab Tests и HTML
- Работает на трёх конфигурациях одновременно: DemoVKR (XML), Управляемое приложение (.dt), Mobile (.cf)

## Архитектура стенда (гибридная)

```
Windows 11
├── WSL2 Ubuntu 24.04
│   ├── Платформа 1С 8.3.27.1936 (нативно в /opt/1cv8/)
│   ├── OneScript 2.0.0 + vanessa-runner + Vanessa-ADD
│   ├── GitLab Runner (shell-executor)
│   └── Проект ~/1c-devops-pipeline/
└── Docker Desktop
    └── onec-postgres (собственный образ: Debian 11 + PostgreSQL 16.3-16.1C + патчи 1С)
```

**Почему гибридная:** платформа 1С в headless-Docker отказывается работать с ошибкой «Цифровая подпись неверна» при запуске служебных .epf Vanessa. Решение — PostgreSQL в Docker (нужна изоляция и воспроизводимость), платформа 1С нативно в WSL.

---

## Требования к окружению

- Windows 11 (для WSLg) или Linux Ubuntu 24.04 напрямую
- WSL2 с Ubuntu 24.04
- Docker Desktop (с интеграцией WSL2)
- Платформа 1С:Предприятие 8.3.27.1936 установленная в WSL
- Комьюнити-лицензия 1С (developer.1c.ru)
- OneScript 2.0.0 + пакеты vanessa-runner, add
- Python 3.10+
- Git, GitLab-аккаунт

---

## Структура проекта

```
1c-devops-pipeline/
├── .gitlab-ci.yml              # конвейер из 11 джоб в 4 стадиях
├── docker-compose.yml          # 2 сервиса: postgres + onec-test
├── config/
│   ├── demo-config/            # DemoVKR — собственная конфигурация (XML)
│   ├── managed-app.dt          # Управляемое приложение — демо от 1С (.dt, 193 МБ)
│   └── mobile-demo.cf          # Mobile — мобильная демо (.cf)
├── docker/
│   ├── postgres/Dockerfile     # собственный образ onec-postgres
│   ├── onec/Dockerfile         # резервный образ с платформой 1С
│   ├── licenses/               # лицензии (в .gitignore)
│   └── platform/               # дистрибутив 1С (в .gitignore)
├── scripts/
│   ├── deploy.py               # оркестратор стенда (6 этапов)
│   ├── manage_db.py            # обёртка для работы с PostgreSQL
│   └── run_vanessa.sh          # wrapper для запуска Vanessa в headless
├── tests/
│   ├── VAParams.json           # настройки Vanessa-Automation
│   └── features/
│       ├── smoke/              # 3 сценария — открытие ключевых форм
│       ├── regression/         # 3 сценария — CRUD-операции
│       └── functional/         # 2 сценария — навигация и поиск
├── tools/vanessa/              # Vanessa-Automation (в .gitignore, качается отдельно)
├── build/                      # файловые ИБ после deploy.py (в .gitignore)
└── reports/                    # отчёты прогонов (vanessa/, syntax-*.xml)
```

---

## Запуск проекта

### 1. Клонирование и первичная настройка

```bash
# Клонируем репозиторий
git clone git@gitlab.com:JolyCole/1c-devops-pipeline.git
cd 1c-devops-pipeline

# Устанавливаем пакеты OneScript (если не установлены)
opm install vanessa-runner    # CLI-обёртка для Vanessa
opm install add               # Vanessa-ADD с bddRunner.epf

# Копируем лицензию 1С в docker/licenses/ (файл .lic должен быть получен ранее с developer.1c.ru)
cp /path/to/your/*.lic docker/licenses/
```

### 2. Развёртывание стенда — `deploy.py`

**Два режима работы стенда:**

```bash
# Минимальный режим — PostgreSQL в Docker + файловая ИБ Управляемого приложения
# Используется для BDD-тестов (быстрее, без зависимости от кластера)
# Время: ~13 секунд
python3 scripts/deploy.py

# Полный режим — всё выше + клиент-серверный кластер 1С через systemd
# Поднимает ragent (1540), rmngr (1541), rphost (1560), ras (1545)
# Регистрирует ИБ managed_app на PostgreSQL через rac
# Время: ~24 секунды, нужен sudo-пароль для systemctl start
python3 scripts/deploy.py --full

# Очистка стенда — остановка контейнеров, удаление файловых ИБ
python3 scripts/deploy.py --cleanup
```

**Этапы deploy.py (в минимальном режиме):**
1. Запуск контейнера PostgreSQL (`docker compose up postgres`)
2. Ожидание готовности (`pg_isready`)
3. (--full) Запуск кластера 1С через systemctl
4. (--full) Ожидание готовности кластера через `rac cluster list`
5. (--full) Регистрация ИБ в кластере через `rac infobase create`
6. Создание файловой ИБ через `ibcmd infobase create --restore=managed-app.dt`

### 3. Запуск тестов локально

**BDD-тесты через wrapper** (обход зависания TestClient в headless):

```bash
# Smoke-тесты — 3 сценария, проверка открытия ключевых форм
./scripts/run_vanessa.sh tests/features/smoke/01_managed_smoke.feature

# Регрессионные тесты — 3 сценария, CRUD-операции
./scripts/run_vanessa.sh tests/features/regression/01_managed_crud.feature

# Функциональные тесты — 2 сценария, навигация и поиск
./scripts/run_vanessa.sh tests/features/functional/01_managed_search.feature

# Одна фича занимает ~25-28 секунд, все три ~78 секунд
```

**Синтаксическая проверка** (статический анализ):

```bash
# Проверка Управляемого приложения — находит 2 замечания про ПолучитьИмяВременногоФайла (Веб-клиент)
vrunner syntax-check \
  --ibconnection "/F$(pwd)/build/ib_managed" \
  --db-user "Администратор" \
  --db-pwd "" \
  --junitpath reports/syntax-managed.xml

# Проверка DemoVKR — без замечаний
vrunner syntax-check \
  --ibconnection "/F$(pwd)/build/ib_demovkr" \
  --db-user "Администратор" \
  --db-pwd "" \
  --junitpath reports/syntax-demovkr.xml
```

### 4. Запуск через GitLab CI/CD

```bash
# Любой push в main триггерит pipeline из 11 джоб
git add .
git commit -m "тестовые изменения"
git push origin main

# Пустой коммит для перезапуска pipeline без изменений кода
git commit --allow-empty -m "rerun pipeline"
git push origin main

# Смотрим статус через терминал
sudo journalctl -u gitlab-runner -f --no-pager | grep -iE "received|succeeded|failed"

# Или в браузере: https://gitlab.com/JolyCole/1c-devops-pipeline/-/pipelines
```

---

## Запуск через VS Code (задачи)

В `.vscode/tasks.json` настроены 8 задач. Вызов: **Ctrl+Shift+P → Tasks: Run Task → выбрать задачу**.

| Задача | Что делает |
|---|---|
| `1C: deploy стенд (минимальный)` | `python3 scripts/deploy.py` |
| `1C: deploy стенд (--full с ragent)` | `python3 scripts/deploy.py --full` |
| `1C: cleanup стенда` | `python3 scripts/deploy.py --cleanup` |
| `BDD: smoke УП` | Прогон smoke-сценариев |
| `BDD: regression УП` | Прогон регрессионных сценариев |
| `BDD: functional УП` | Прогон функциональных сценариев |
| `Syntax: проверка УП` | Статический анализ Управляемого приложения |
| `Git: push (триггер CI-пайплайна)` | Коммит с вводом сообщения + push |

---

## Просмотр отчётов

### Локальные отчёты после прогона `run_vanessa.sh`

```bash
# JUnit XML от Vanessa (именно его потребляет GitLab)
cat reports/vanessa/junit/junit.xml

# Статус последнего прогона (0 = успех)
cat reports/vanessa/logs/status.txt

# Скриншоты от Vanessa (если делала)
ls -la reports/vanessa/screenshots/

# Отчёты синтаксической проверки
cat reports/syntax-managed.xml
cat reports/syntax-demovkr.xml
cat reports/syntax-mobile.xml
```

---

## Команды для разработки

### Git и ветвление

```bash
# Посмотреть историю коммитов pipeline
git log --oneline --all -- .gitlab-ci.yml | head -20

# Откатить файл к состоянию конкретного коммита
git checkout <hash> -- path/to/file

# Создать бэкап-архив проекта (без тяжёлых папок)
cd ~
tar --exclude='1c-devops-pipeline/tools/vanessa/vanessa-automation' \
    --exclude='1c-devops-pipeline/docker/platform' \
    --exclude='1c-devops-pipeline/build' \
    -czf backup_$(date +%Y%m%d_%H%M).tar.gz \
    1c-devops-pipeline/
```

### Docker

```bash
# Пересобрать образ PostgreSQL после изменения Dockerfile
docker compose build postgres

# Посмотреть статус контейнеров
docker compose ps

# Зайти внутрь контейнера postgres
docker exec -it onec-postgres bash

# Проверить что расширение mchar создано
docker exec onec-postgres psql -U postgres -c "\dx"

# Полная очистка: остановить и удалить контейнеры + volumes
docker compose down -v
```

### Работа с ИБ вручную

```bash
# Создать файловую ИБ с правильной локалью (именно ru_RU, а не ru!)
/opt/1cv8/x86_64/8.3.27.1936/ibcmd infobase create \
  --database-path="$HOME/1c-devops-pipeline/build/ib_managed" \
  --restore="$HOME/1c-devops-pipeline/config/managed-app.dt" \
  --locale=ru_RU

# Открыть ИБ в клиенте (через WSLg)
/opt/1cv8/x86_64/8.3.27.1936/1cv8c ENTERPRISE \
  /F$HOME/1c-devops-pipeline/build/ib_managed &

# Список ИБ в кластере (когда deploy.py --full запущен)
/opt/1cv8/x86_64/8.3.27.1936/rac infobase --cluster=<UUID> list localhost:1545
```

### Диагностика проблем

```bash
# Прибить висящие процессы 1С
pkill -9 -f "1cv8c.*TESTCLIENT"
pkill -9 -f "vrunner"
rm -f /tmp/v8_*.tmp

# Остановить кластер 1С
sudo systemctl stop srv1cv8-8.3.27.1936@default
sudo systemctl stop ras-8.3.27.1936

# Проверить занятые порты кластера
ss -tlnp 2>/dev/null | grep -E "1540|1541|1545|1560"

# Проверить статус GitLab Runner
sudo systemctl status gitlab-runner
sudo journalctl -u gitlab-runner -f --no-pager | grep -iE "received|succeeded|failed"
```

---

## Известные ограничения

1. **Лицензия 1С** — комьюнити-лицензия ограничена 3 слотами на устройство, отвязка через 7 дней.
2. **Цифровая подпись в Docker** — клиент 1С (`1cv8c`) не работает в headless-Docker контейнерах из-за проверки подписи .epf. Решено гибридной архитектурой (PG в Docker, платформа в WSL).
3. **BDD на файловых ИБ** — тесты работают через `/F<path>` подключение. Перевод на серверное подключение `/S<server>/<base>` — направление развития.
4. **Пароль PostgreSQL в открытом виде** — для production нужно перенести в GitLab CI/CD Variables (Settings → CI/CD → Variables → Protected + Masked).
5. **Self-hosted runner работает в WSL того же хоста** — используется shared workspace pattern с dev-каталогом. Для публичного раннера потребуется переработка путей в `run_vanessa.sh`.

---

## Результаты

**Pipeline:** 5 замерных прогонов, среднее время 4:21, разброс 3:53-5:38

**Локальные замеры:** 8 BDD-сценариев за ~78 секунд (3 прогона, разброс 5%)

**Находка статанализа:** в эталонной конфигурации Управляемого приложения от фирмы 1С обнаружены 2 дефекта совместимости с веб-клиентом (процедура `ПолучитьИмяВременногоФайла` в модуле `Справочник.ХранимыеФайлы.Форма.ФормаЭлемента.Форма`, строки 844 и 476).

---

## Полезные ссылки

- Vanessa-Automation: https://github.com/vanessa-opensource/vanessa-automation
- vanessa-runner: https://github.com/vanessa-opensource/vanessa-runner
- Vanessa-ADD: https://github.com/vanessa-opensource/add
- OneScript: https://oscript.io
- GitLab CI/CD: https://docs.gitlab.com/ee/ci/
- Проект в GitLab: https://gitlab.com/JolyCole/1c-devops-pipeline

---

## Автор

Филимонов Иван Денисович, группа БВТ 2205, МТУСИ
ВКР бакалавра по направлению 09.03.01 «Информатика и вычислительная техника»
Тема: «Разработка метода автоматизации тестирования конфигураций 1С:Предприятие с использованием DevOps инструментов»
Москва, 2026