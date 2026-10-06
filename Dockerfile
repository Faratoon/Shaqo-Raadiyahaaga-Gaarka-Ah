# Lightweight official Python 3.11 image
FROM python:3.11-slim

# Prevent Python from writing .pyc and enable unbuffered output
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONIOENCODING=utf-8
ENV DOCKER=1
ENV PORT=5050

WORKDIR /app

# Install system dependencies needed for curl-cffi and basic utilities
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements-portal.txt /app/
RUN pip install --no-cache-dir -r requirements-portal.txt

# Copy application files
COPY portal_app.py /app/
COPY telegram_career_bot.py /app/
COPY telegram_management_data.json /app/
COPY templates/ /app/templates/
COPY data_folder/ /app/data_folder/

EXPOSE 5050

# Default command (overridden per service in docker-compose.yml)
CMD ["gunicorn", "--bind", "0.0.0.0:5050", "--workers", "2", "--timeout", "120", "portal_app:app"]
