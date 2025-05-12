# Alternative options for deploying to Railway

# Use Ubuntu base image which works well with pdf2htmlEX
FROM ubuntu:22.04

# Install essential packages and pdf2htmlEX dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    ca-certificates \
    cmake \
    curl \
    fontconfig \
    git \
    libcairo2-dev \
    libfontconfig1-dev \
    libfreetype6-dev \
    libglib2.0-dev \
    libjpeg-dev \
    libopenjp2-7-dev \
    libpango1.0-dev \
    libpng-dev \
    libpoppler-dev \
    libpoppler-glib-dev \
    libspiro-dev \
    libx11-dev \
    libxext-dev \
    pkg-config \
    poppler-utils \
    python3 \
    python3-pip \
    wget

# Install poppler utils and any other specific dependencies
RUN apt-get install -y poppler-utils

# Install alternative HTML converter
RUN pip3 install pdfminer.six pdf2image Pillow reportlab

# Copy application files
WORKDIR /app
COPY . .

# Install Python dependencies
RUN pip3 install --no-cache-dir -r requirements.txt

# Add alternative script to Dockerfile as fallback
COPY alternative_converter.py /app/

# Set environment variable to use alternative converter
ENV USE_ALTERNATIVE_CONVERTER=true

# Expose port for the application
EXPOSE ${PORT:-3001}

# Start the application
CMD ["python3", "app.py"]
