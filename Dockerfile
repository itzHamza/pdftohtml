FROM ubuntu:22.04

# Update and install dependencies
RUN apt-get update && apt-get install -y \
    wget \
    build-essential \
    cmake \
    libfreetype6-dev \
    libpng-dev \
    libjpeg-dev \
    python3 \
    python3-pip \
    pkg-config \
    git \
    poppler-utils \
    software-properties-common \
    libfontconfig1-dev \
    libfontforge-dev \
    poppler-data

# Install pdf2htmlEX directly
RUN apt-get install -y pdf2htmlex

# Install Flask and other Python dependencies
COPY requirements.txt /app/requirements.txt
WORKDIR /app
RUN pip3 install --no-cache-dir -r requirements.txt

# Copy the application code
COPY *.py /app/

# Expose the port the app runs on
EXPOSE 8080

# Command to run the application
CMD ["python3", "app.py"]
