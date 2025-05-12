# Base image
FROM python:3.11-slim

# Set work directory
WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app
COPY . .

# Expose port (this is mostly informational, Railway will use its own port)
EXPOSE $PORT

# Start the server
CMD ["gunicorn", "main:app", "--bind", "0.0.0.0:$PORT"]
