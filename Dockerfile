# Official Microsoft Playwright image ships Chromium + all system deps.
# No manual `playwright install` or apt-get required.
FROM mcr.microsoft.com/playwright/python:v1.44.0-jammy

WORKDIR /app

# Install Python deps first (layer cached unless requirements.txt changes)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 5000

ENV PYTHONUNBUFFERED=1 \
    HEADLESS=true      \
    LOG_LEVEL=INFO     \
    PORT=5000

CMD ["python", "main.py"]
