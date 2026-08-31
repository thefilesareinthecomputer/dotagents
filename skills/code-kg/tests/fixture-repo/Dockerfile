FROM python:3.12-slim
WORKDIR /srv
COPY app app
COPY queries/report.sql queries/report.sql
CMD ["python3", "app/main.py"]
