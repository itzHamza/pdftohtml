FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8080

# Set environment variable with default value
ENV PORT=8080

CMD ["gunicorn", "--bind", "0.0.0.0:${PORT}", "main:app"]
