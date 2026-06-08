FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .

RUN addgroup --system --gid 1001 app && \
    adduser --system --uid 1001 --ingroup app app
USER app

EXPOSE 9100

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "9100"]
