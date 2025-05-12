FROM ubuntu:22.04

# تحديث الحزم
RUN apt-get update && apt-get install -y \
    python3 python3-pip \
    git cmake g++ pkg-config \
    poppler-utils \
    wget curl zip unzip \
    make fontforge


# تثبيت pdf2htmlEX
RUN git clone https://github.com/pdf2htmlEX/pdf2htmlEX.git && \
    cd pdf2htmlEX && cmake . && make && make install && cd .. && rm -rf pdf2htmlEX

# نسخ الكود
WORKDIR /app
COPY . .
RUN pip3 install -r requirements.txt

EXPOSE 8000
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "app:app"]
