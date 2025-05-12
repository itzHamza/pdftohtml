# Use lightweight Python base image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Copy dependency list and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose default port (Railway will override it via $PORT)
EXPOSE 8080

# Run the application with Gunicorn
CMD gunicorn --bind 0.0.0.0:8080 main:app
