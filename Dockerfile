# Base image
FROM python:3.11-slim

# Set work directory
WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app
COPY . .

# Expose port (this is just documentation, the actual port is set by CMD)
EXPOSE 8080

# Start the server - use env var PORT or default to 8080
CMD gunicorn main:app --bind 0.0.0.0:${PORT:-8080}
