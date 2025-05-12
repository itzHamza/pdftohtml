from flask import Flask, request, send_file, jsonify, Response
from flask_cors import CORS
import requests
import os
import subprocess
import tempfile
import uuid
import logging
from werkzeug.utils import secure_filename
import shutil
import urllib.parse

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create temporary directory for storing files
TEMP_DIR = os.path.join(tempfile.gettempdir(), 'pdf2html_temp')
os.makedirs(TEMP_DIR, exist_ok=True)

def download_pdf(url):
    """Download a PDF file from a URL and save it to a temporary file"""
    logger.info(f"Downloading PDF from URL: {url}")
    try:
        response = requests.get(url, stream=True, timeout=30)
        response.raise_for_status()
        
        # Extract filename from URL or use a random name
        filename = os.path.basename(urllib.parse.urlparse(url).path) or f"{uuid.uuid4()}.pdf"
        filename = secure_filename(filename)
        if not filename.lower().endswith('.pdf'):
            filename += '.pdf'
            
        filepath = os.path.join(TEMP_DIR, filename)
        
        with open(filepath, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
                
        logger.info(f"PDF downloaded successfully to {filepath}")
        return filepath
    except Exception as e:
        logger.error(f"Error downloading PDF: {str(e)}")
        raise

def convert_pdf_to_html(pdf_path):
    """Convert PDF to HTML using pdf2htmlEX"""
    logger.info(f"Converting PDF to HTML: {pdf_path}")
    
    # Create a unique output directory
    output_dir = os.path.join(TEMP_DIR, str(uuid.uuid4()))
    os.makedirs(output_dir, exist_ok=True)
    
    filename = os.path.basename(pdf_path)
    output_filename = os.path.splitext(filename)[0] + '.html'
    output_path = os.path.join(output_dir, output_filename)
    
    try:
        # pdf2htmlEX command with options to preserve text selection
        cmd = [
            'pdf2htmlEX',
            '--zoom', '1.3',  # Scale factor
            '--fit-width', '1024',  # Target page width
            '--process-outline', '0',  # Skip outline processing for speed
            '--dest-dir', output_dir,  # Output directory
            '--optimize-text', '1',  # Optimize text for selection
            '--font-format', 'woff',  # Use WOFF format for fonts
            '--data-dir', output_dir,  # Directory for data files
            '--split-pages', '0',  # Don't split pages into separate files
            '--embed', 'cfijo',  # Embed: css,fonts,images,javascript,outline
            pdf_path,
            output_filename
        ]
        
        logger.info(f"Running command: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            logger.error(f"pdf2htmlEX error: {result.stderr}")
            raise Exception(f"PDF conversion failed: {result.stderr}")
        
        logger.info(f"PDF successfully converted to HTML: {output_path}")
        
        # Read the HTML file
        with open(output_path, 'r', encoding='utf-8') as f:
            html_content = f.read()
        
        # Clean up the temporary files but keep the output for a while
        # (We'll clean it later with a scheduled task)
        
        return html_content, output_path
    except Exception as e:
        logger.error(f"Error converting PDF to HTML: {str(e)}")
        # Clean up on failure
        if os.path.exists(output_dir):
            shutil.rmtree(output_dir, ignore_errors=True)
        raise

@app.route('/convert-url', methods=['POST'])
def convert_url():
    """Convert PDF from URL to HTML"""
    try:
        data = request.get_json()
        if not data or 'url' not in data:
            return jsonify({'error': 'No URL provided'}), 400
        
        url = data['url']
        pdf_path = download_pdf(url)
        html_content, _ = convert_pdf_to_html(pdf_path)
        
        # Clean up the PDF file
        if os.path.exists(pdf_path):
            os.remove(pdf_path)
        
        return Response(html_content, mimetype='text/html')
    except Exception as e:
        logger.exception("Error in convert-url endpoint")
        return jsonify({'error': str(e)}), 500

@app.route('/convert', methods=['POST'])
def convert_file():
    """Convert uploaded PDF file to HTML"""
    try:
        if 'file' in request.files:
            # Handle multipart/form-data upload
            file = request.files['file']
            if file.filename == '':
                return jsonify({'error': 'No file selected'}), 400
            
            filename = secure_filename(file.filename)
            pdf_path = os.path.join(TEMP_DIR, f"{uuid.uuid4()}_{filename}")
            file.save(pdf_path)
            
        elif request.content_type == 'application/pdf':
            # Handle direct binary upload
            pdf_data = request.data
            if not pdf_data:
                return jsonify({'error': 'No PDF data received'}), 400
            
            pdf_path = os.path.join(TEMP_DIR, f"{uuid.uuid4()}.pdf")
            with open(pdf_path, 'wb') as f:
                f.write(pdf_data)
        else:
            return jsonify({'error': 'Invalid request format'}), 400
        
        html_content, _ = convert_pdf_to_html(pdf_path)
        
        # Clean up the PDF file
        if os.path.exists(pdf_path):
            os.remove(pdf_path)
        
        return Response(html_content, mimetype='text/html')
    except Exception as e:
        logger.exception("Error in convert endpoint")
        return jsonify({'error': str(e)}), 500

# Cleanup task
@app.before_first_request
def setup_cleanup():
    """Set up a background task to clean up old temporary files"""
    def cleanup_old_files():
        import threading
        import time
        
        def run_cleanup():
            while True:
                logger.info("Running cleanup task")
                try:
                    # Remove files older than 1 hour
                    now = time.time()
                    for root, dirs, files in os.walk(TEMP_DIR):
                        for f in files:
                            filepath = os.path.join(root, f)
                            if os.path.isfile(filepath):
                                if os.stat(filepath).st_mtime < now - 3600:  # 1 hour
                                    try:
                                        os.remove(filepath)
                                        logger.info(f"Removed old file: {filepath}")
                                    except Exception as e:
                                        logger.error(f"Error removing file {filepath}: {str(e)}")
                        
                        # Also clean up empty directories
                        for d in dirs:
                            dirpath = os.path.join(root, d)
                            if not os.listdir(dirpath):  # Check if directory is empty
                                try:
                                    os.rmdir(dirpath)
                                    logger.info(f"Removed empty directory: {dirpath}")
                                except Exception as e:
                                    logger.error(f"Error removing directory {dirpath}: {str(e)}")
                except Exception as e:
                    logger.error(f"Error in cleanup task: {str(e)}")
                
                # Sleep for 30 minutes before next cleanup
                time.sleep(1800)
        
        # Start the cleanup thread
        cleanup_thread = threading.Thread(target=run_cleanup, daemon=True)
        cleanup_thread.start()
    
    # Run the setup
    cleanup_old_files()

if __name__ == '__main__':
    # Create gunicorn compatible entry point
    app.run(host='0.0.0.0', port=3001, debug=True)
