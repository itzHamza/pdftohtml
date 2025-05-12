FROM ubuntu:22.04

# Install dependencies
RUN apt-get update && \
    apt-get install -y \
    wget \
    build-essential \
    cmake \
    libfontconfig1-dev \
    libfreetype6-dev \
    libx11-dev \
    libxext-dev \
    libpng-dev \
    libjpeg-dev \
    python3 \
    python3-pip \
    poppler-utils \
    git \
    pkg-config

# Install pdf2htmlEX dependencies
RUN apt-get install -y \
    libjpeg-dev \
    libopenjp2-7-dev \
    libfontconfig1-dev \
    libfreetype6-dev \
    libpoppler-dev \
    libpoppler-glib-dev \
    libspiro-dev \
    libcairo2-dev \
    libpango1.0-dev \
    libglib2.0-dev

# Build and install pdf2htmlEX from source
WORKDIR /tmp
RUN git clone --depth 1 --branch v0.18.9.0 https://github.com/pdf2htmlEX/pdf2htmlEX.git pdf2htmlEX && \
    cd pdf2htmlEX && \
    git submodule update --init --recursive && \
    mkdir build && \
    cd build && \
    cmake -DENABLE_LIBJPEG=ON .. && \
    make -j$(nproc) && \
    make install && \
    cd / && \
    rm -rf /tmp/pdf2htmlEX

# Create app directory
WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Expose port
EXPOSE 3001

# Run the application
CMD ["gunicorn", "--bind", "0.0.0.0:3001", "--workers", "4", "app:app"]
