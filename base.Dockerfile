FROM pypy:3.7

ENV TINI_VERSION v0.18.0
RUN curl -Lo /tini https://github.com/krallin/tini/releases/download/${TINI_VERSION}/tini && \
    chmod +x /tini

ENV PYTHONFAULTHANDLER=1

RUN mkdir -p /usr/src/app/home && \
    useradd -d /usr/src/app/home -s /usr/sbin/nologin -u 998 appuser && \
    chown appuser /usr/src/app/home
WORKDIR /usr/src/app
RUN apt-get update && apt-get install -y gcc gfortran libopenblas-dev liblapack-dev && rm -rf /var/lib/apt/lists/*
RUN curl -sSL https://raw.githubusercontent.com/sdispater/poetry/master/get-poetry.py | python - --version 1.1.4 && $HOME/.poetry/bin/poetry config virtualenvs.create false
RUN pip --disable-pip-version-check --no-cache-dir install toml
COPY docker/install_deps.py poetry.lock /usr/src/app/
RUN pypy3 -c "import json, toml; json.dump(toml.load(open('poetry.lock')), open('poetry.lock.json', 'w'))"
RUN pypy3 install_deps.py poetry.lock.json
# CI: RUN pip --disable-pip-version-check install coverage==5.3.1
# CI: COPY .coveragerc /usr/src/app/

# This is the common part of the Dockerfiles
# It is copied in all of them, and this file is used for the CI
