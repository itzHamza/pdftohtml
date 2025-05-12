FROM bwits/pdf2htmlex:latest

RUN apt-get update && apt-get install -y python3 python3-pip git
WORKDIR /app
COPY . .
RUN pip3 install -r requirements.txt

EXPOSE 8000
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "app:app"]
