# Fixture: deliberately hazardous. Every line should trip a rule.
# Used by tests/test_docker_check.py. Do not "fix" this file.
FROM python:latest

ENV API_KEY=sk-live-abc123
ARG DB_PASSWORD=hunter2

ADD https://example.com/installer.sh /tmp/installer.sh
RUN curl -sSL https://get.example.com | sh
RUN sudo apt-get install -y build-essential
RUN chmod 777 /app

COPY . /app
RUN pip install -r /app/requirements.txt

CMD ["python", "/app/main.py"]
