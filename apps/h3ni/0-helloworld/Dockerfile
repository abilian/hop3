FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt requirements.txt
RUN pip install -r requirements.txt --no-cache-dir

COPY app.py app.py

CMD ["gunicorn", "--bind", "0.0.0.0:8080", "app:app"]
