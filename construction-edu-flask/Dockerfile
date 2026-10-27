FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN pip install --no-cache-dir Flask==3.1.1 gunicorn==23.0.0 && \
    useradd --create-home --uid 10001 webuser
COPY construction-edu-flask/app.py ./app.py
COPY prompt-web/index.html prompt-web/app.js prompt-web/styles.css ./prompt-web/
USER webuser
EXPOSE 8000
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", "--timeout", "120", "app:app"]
