FROM debian:11

ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=Europe/Moscow

RUN apt-get update && apt-get install -y --no-install-recommends \
        locales tzdata \
    && sed -i 's/# ru_RU.UTF-8 UTF-8/ru_RU.UTF-8 UTF-8/' /etc/locale.gen \
    && locale-gen ru_RU.UTF-8 \
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone \
    && rm -rf /var/lib/apt/lists/*

ENV LANG=ru_RU.UTF-8
ENV LC_ALL=ru_RU.UTF-8

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl wget bzip2 gnupg lsb-release \
    && rm -rf /var/lib/apt/lists/*

RUN install -d /usr/share/postgresql-common/pgdg \
    && curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc \
         -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc \
    && echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt $(lsb_release -cs)-pgdg main" > /etc/apt/sources.list.d/pgdg.list

COPY platform/postgresql_16.3_16.1C_amd64_deb.tar.bz2 /tmp/pg.tar.bz2

RUN cd /tmp && tar -xjf pg.tar.bz2

RUN apt-get update && apt-get install -y --no-install-recommends \
        libxml2 libxslt1.1 libldap-2.4-2 \
        libssl1.1 libkrb5-3 libedit2 libllvm11 \
        libreadline8 libpam0g libossp-uuid16 \
        postgresql-common ssl-cert ucf \
    && rm -rf /var/lib/apt/lists/*

RUN cd /tmp \
    && curl -fsSL -o libicu66.deb http://archive.ubuntu.com/ubuntu/pool/main/i/icu/libicu66_66.1-2ubuntu2.1_amd64.deb \
    && dpkg -i libicu66.deb \
    && rm -f libicu66.deb

RUN cd /tmp/postgresql-16.3-16.1C_amd64_deb \
    && dpkg -i --force-depends libpq5_16.3-16.1C_amd64.deb \
    && dpkg -i --force-depends postgresql-client-16_16.3-16.1C_amd64.deb \
    && dpkg -i --force-depends postgresql-16_16.3-16.1C_amd64.deb \
    && cd /tmp \
    && rm -rf postgresql-16.3-16.1C_amd64_deb pg.tar.bz2

ENV PGDATA=/var/lib/postgresql/16/main

USER postgres

RUN rm -rf $PGDATA/* \
    && /usr/lib/postgresql/16/bin/initdb -D $PGDATA --locale=ru_RU.UTF-8 --encoding=UTF8

RUN echo "listen_addresses = '*'" >> $PGDATA/postgresql.conf \
    && echo "local all postgres trust" > $PGDATA/pg_hba.conf \
    && echo "host all all 0.0.0.0/0 md5" >> $PGDATA/pg_hba.conf \
    && /usr/lib/postgresql/16/bin/pg_ctl -D $PGDATA -w -t 30 start \
    && /usr/lib/postgresql/16/bin/psql -c "ALTER USER postgres WITH PASSWORD 'postgres1c';" \
    && /usr/lib/postgresql/16/bin/pg_ctl -D $PGDATA -w -t 30 stop

EXPOSE 5432

CMD ["/usr/lib/postgresql/16/bin/postgres", "-D", "/var/lib/postgresql/16/main"]
