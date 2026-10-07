FROM python:3.12-slim

LABEL org.opencontainers.image.source="https://github.com/andr77eeeew/ci-lab-string-utils"

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

CMD ["pytest", "-v"]