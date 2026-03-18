FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir anthropic openai fastapi uvicorn
COPY . .
CMD ["uvicorn", "app:app", "--host", "0.0.0.0"]
