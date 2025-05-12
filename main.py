from flask import Flask, request, jsonify, send_file
import os
import subprocess
import uuid
import tempfile
import shutil
import logging
import traceback
from flask_cors import CORS

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Ensure temp directory exists
TEMP_DIR = os.path.join(tempfile.gettempdir(), 'pdf2html_converter')
os.makedirs(TEMP_DIR, exist_ok=True)

def convert_pdf_to_html(pdf_path, output_dir):
    """
    Convert PDF to HTML using pdf2htmlEX
    Returns the path to the HTML file
    """
    logger.info(f"Converting PDF: {pdf_path} to HTML in directory: {output_dir}")
    
    # Define output filename (use a fixed name as pdf2htmlEX will use the PDF filename as prefix)
    html_filename = "output.html"
    
    # Construct the pdf2htmlEX command
    # For a complete list of options, run: pdf2htmlEX --help
    command = [
        'pdf2htmlEX',
        '--dest-dir', output_dir,
        '--outfile', html_filename,
        # Options for better rendering
        '--fit-width', '1024',
        '--zoom', '1.3',
        '--embed', 'cfijo',  # Embed: css, fonts, images, javascript, outline
        '--split-pages', '0',  # Don't split pages
        '--process-outline', '1',  # Process outlines
        '--correct-text-visibility', '1',  # Correct text visibility
        pdf_path
    ]
    
    logger.debug(f"Running command: {' '.join(command)}")
    
    try:
        # Run the conversion process
        process = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True
        )
        
        logger.debug(f"pdf2htmlEX stdout: {process.stdout}")
        if process.stderr:
            logger.warning(f"pdf2htmlEX stderr: {process.stderr}")
            
        # Return the path to the generated HTML file
        html_path = os.path.join(output_dir, html_filename)
        if os.path.exists(html_path):
            logger.info(f"Successfully created HTML file: {html_path}")
            return html_path
        else:
            raise FileNotFoundError(f"Output HTML file not found: {html_path}")
            
    except subprocess.CalledProcessError as e:
        logger.error(f"pdf2htmlEX failed with return code {e.returncode}")
        logger.error(f"stdout: {e.stdout}")
        logger.error(f"stderr: {e.stderr}")
        raise RuntimeError(f"pdf2htmlEX conversion failed: {e.stderr}")
    except Exception as e:
        logger.error(f"Conversion error: {str(e)}")
        logger.error(traceback.format_exc())
        raise

@app.route('/convert', methods=['POST'])
def convert():
    try:
        logger.info(f"Received conversion request. Content-Type: {request.content_type}")
        
        # Create unique working directory for this conversion
        job_id = str(uuid.uuid4())
        job_dir = os.path.join(TEMP_DIR, job_id)
        os.makedirs(job_dir, exist_ok=True)
        
        pdf_path = os.path.join(job_dir, "input.pdf")
        
        # Check if request includes file or raw data
        if 'file' not in request.files:
            logger.info("No file in request, trying to read raw data")
            pdf_data = request.data
            if not pdf_data:
                logger.error("No PDF data provided")
                return jsonify({'error': 'No PDF data provided'}), 400
            
            logger.info(f"Read {len(pdf_data)} bytes of raw PDF data")
            
            # Save the raw data to a file
            with open(pdf_path, 'wb') as f:
                f.write(pdf_data)
        else:
            logger.info("File found in request")
            pdf_file = request.files['file']
            pdf_file.save(pdf_path)
            logger.info(f"Saved uploaded file to {pdf_path}")
        
        try:
            # Create output directory
            output_dir = os.path.join(job_dir, "output")
            os.makedirs(output_dir, exist_ok=True)
            
            # Convert PDF to HTML
            html_path = convert_pdf_to_html(pdf_path, output_dir)
            
            # Read the HTML content
            with open(html_path, 'r', encoding='utf-8') as f:
                html_content = f.read()
            
            logger.info(f"Conversion successful, generated {len(html_content)} bytes of HTML")
            
            # Clean up job directory
            shutil.rmtree(job_dir, ignore_errors=True)
            
            return html_content, 200, {'Content-Type': 'text/html'}
            
        except Exception as e:
            logger.error(f"Error in pdf2html conversion: {str(e)}")
            logger.error(traceback.format_exc())
            return jsonify({'error': f'PDF conversion error: {str(e)}'}), 500
            
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({'error': f'Server error: {str(e)}'}), 500
    finally:
        # Make sure to clean up regardless of success or failure
        try:
            if 'job_dir' in locals() and os.path.exists(job_dir):
                shutil.rmtree(job_dir, ignore_errors=True)
        except Exception as cleanup_error:
            logger.error(f"Error during cleanup: {str(cleanup_error)}")

@app.route('/health', methods=['GET'])
def health_check():
    try:
        # Check if pdf2htmlEX is installed and get its version
        process = subprocess.run(
            ['pdf2htmlEX', '--version'],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        pdf2html_version = process.stdout.strip() if process.stdout else process.stderr.strip()
        
        return jsonify({
            'status': 'ok',
            'versions': {
                'pdf2htmlEX': pdf2html_version,
                'flask_version': Flask.__version__,
                'python_version': os.sys.version
            }
        }), 200
    except Exception as e:
        logger.error(f"Health check error: {str(e)}")
        return jsonify({
            'status': 'error',
            'error': str(e),
            'message': 'pdf2htmlEX may not be installed correctly'
        }), 500

@app.route('/', methods=['GET'])
def index():
    return """
    <html>
        <head><title>PDF to HTML Converter</title></head>
        <body>
            <h1>PDF to HTML Converter</h1>
            <p>This service converts PDF files to HTML using pdf2htmlEX.</p>
            <h2>Usage:</h2>
            <p>Send a POST request to /convert with either:</p>
            <ul>
                <li>A file field named 'file' containing your PDF</li>
                <li>Raw PDF data in the request body</li>
            </ul>
            <h3>Example form</h3>
            <form action="/convert" method="post" enctype="multipart/form-data">
                <input type="file" name="file" accept="application/pdf">
                <input type="submit" value="Convert">
            </form>
        </body>
    </html>
    """

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))  # Default to 8080 if PORT not set
    app.run(host='0.0.0.0', port=port, debug=True)
