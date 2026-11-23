FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1     PYTHONUNBUFFERED=1     API_HOST=0.0.0.0     API_PORT=8080

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends     tesseract-ocr tesseract-ocr-fas tesseract-ocr-eng     fonts-dejavu fonts-noto-core libreoffice-writer     && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/legal_bot/storage /app/legal_bot/uploads

EXPOSE 8080

CMD ["python", "-m", "legal_bot.api"]
