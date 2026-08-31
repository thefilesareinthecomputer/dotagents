.PHONY: migrate seed test worker run

migrate:
	python3 manage.py migrate --noinput

seed:
	python3 manage.py seed

test:
	python3 manage.py test core

worker:
	python3 manage.py runworker

run:
	python3 manage.py runserver 0.0.0.0:8000
