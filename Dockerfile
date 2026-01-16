FROM python:3.10-bookworm

ENV PYTHONIOENCODING=utf-8
ENV PYTHONUNBUFFERED 1
ENV PYTHONPATH="/app:${PYTHONPATH}"

COPY requirements-hjlp-live.txt /app/requirements.txt
RUN pip install -r /app/requirements.txt

COPY core /app/core
COPY live /app/live

VOLUME .env

WORKDIR /app
CMD [ "python", "/app/live/run.py" ]