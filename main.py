from flask import Flask, request, send_file, jsonify
import os, uuid, requests, subprocess

app = Flask(__name__)

UPLOAD_FOLDER = "uploads"
OUTPUT_FOLDER = "outputs"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

@app.route("/convert")
def convert_pdf():
    url = request.args.get("url")
    if not url:
        return jsonify({"error": "No URL provided"}), 400

    # تحميل الملف PDF
    try:
        response = requests.get(url)
        if response.status_code != 200:
            return jsonify({"error": "Failed to download PDF"}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 400

    pdf_id = str(uuid.uuid4())
    pdf_path = f"{UPLOAD_FOLDER}/{pdf_id}.pdf"
    html_path = f"{OUTPUT_FOLDER}/{pdf_id}.html"

    with open(pdf_path, "wb") as f:
        f.write(response.content)

    # تحويل PDF إلى HTML
    try:
        subprocess.run(["pdf2htmlEX", pdf_path, html_path], check=True)
    except subprocess.CalledProcessError:
        return jsonify({"error": "Conversion failed"}), 500

    return send_file(html_path, as_attachment=True, download_name="converted.html")

@app.route("/")
def home():
    return "PDF to HTML API is working."

