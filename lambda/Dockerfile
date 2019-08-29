FROM python:3.7

RUN pip3 install -U pip

COPY requirements /tmp/requirements

RUN pip3 install -r /tmp/requirements/requirements.txt -r /tmp/requirements/requirements-dev.txt

COPY /src /src
COPY /test /test

ENV PYTHONPATH=/src

CMD ["pytest", "-s", "--cov=/src", "--cov-report=term-missing", "--disable-warnings", "/test"]
