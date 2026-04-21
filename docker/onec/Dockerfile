# Базовый образ
FROM ubuntu:22.04

# Неинтерактивный режим для apt
ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=Europe/Moscow

# Русская локализация - обязательно для 1С
RUN apt-get update && apt-get install -y --no-install-recommends \
        locales tzdata \
    && locale-gen ru_RU.UTF-8 \
    && update-locale LANG=ru_RU.UTF-8 \
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone \
    && rm -rf /var/lib/apt/lists/*

ENV LANG=ru_RU.UTF-8
ENV LC_ALL=ru_RU.UTF-8
ENV LANGUAGE=ru_RU:ru

# Системные зависимости для платформы 1С и Xvfb (headless-режим)
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl wget gnupg unzip \
        xvfb xauth \
        fontconfig xfonts-utils xfonts-75dpi xfonts-100dpi \
        libfontconfig1 libfreetype6 \
        libglib2.0-0 libgsf-1-114 \
        libsm6 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 \
        libxcb-render-util0 libxkbcommon-x11-0 \
        libwebkit2gtk-4.0-37 \
        libstdc++6 \
        libpq5 \
        sudo \
        mono-runtime \
        python3 python3-pip \
        iproute2 \
    && rm -rf /var/lib/apt/lists/*

# Копируем коммерческий .run-инсталлятор платформы (уже без учебки)
COPY platform/setup-full-8.3.27.1936-x86_64.run /tmp/setup-1c.run

# Запускаем установку в silent-режиме с компонентами для клиент-серверного режима
RUN chmod +x /tmp/setup-1c.run \
    && /tmp/setup-1c.run --mode unattended --enable-components client_full,server \
    && rm -f /tmp/setup-1c.run

# Пользователь usr1cv8 уже создан установщиком платформы, настраиваем окружение
RUN mkdir -p /home/usr1cv8/.1cv8 \
    && mkdir -p /var/1C/licenses \
    && chown -R usr1cv8:usr1cv8 /home/usr1cv8 /var/1C/licenses 2>/dev/null || true

# Ставим OneScript 2.0 из self-contained ZIP-архива с GitHub
RUN mkdir -p /opt/onescript \
    && cd /tmp \
    && curl -fsSL https://github.com/EvilBeaver/OneScript/releases/download/v2.0.0/OneScript-2.0.0-linux-x64.zip -o onescript.zip \
    && unzip onescript.zip -d /opt/onescript \
    && chmod +x /opt/onescript/bin/* \
    && rm -f /tmp/onescript.zip

# Регистрируем oscript и opm в системном PATH
ENV PATH="/opt/onescript/bin:${PATH}"
RUN ln -sf /opt/onescript/bin/oscript /usr/local/bin/oscript \
    && ln -sf /opt/onescript/bin/opm /usr/local/bin/opm

# Ставим vanessa-runner через opm
RUN pip3 install --no-cache-dir psycopg2-binary

RUN opm install vanessa-runner

# Рабочая папка внутри контейнера
WORKDIR /workspace

# Дисплей для Xvfb
ENV DISPLAY=:99

# При старте контейнера поднимаем Xvfb в фоне
CMD ["bash", "-c", "Xvfb :99 -screen 0 1024x768x16 & sleep 2 && tail -f /dev/null"]