from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import os
import tempfile
import uuid
import requests
from io import BytesIO
import logging
from werkzeug.utils import secure_filename

# Import Spire.PDF for Python
# You'll need to install this with: pip install spire.pdf
from spire.pdf import PdfDocument, PdfPageBase
from spire.pdf.common import PdfHtmlLayoutFormat
from spire.pdf.conversion import HtmlConverter

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create temp directory for storing files if it doesn't exist
TEMP_DIR = os.path.join(tempfile.gettempdir(), 'pdf-converter')
os.makedirs(TEMP_DIR, exist_ok=True)

@app.route('/health', methods=['GET'])
def health_check():
    """Simple health check endpoint"""
    return jsonify({"status": "healthy"})

@app.route('/convert', methods=['POST'])
def convert_pdf():
    """Convert an uploaded PDF file to HTML"""
    try:
        # Check if a file was uploaded
        if 'file' not in request.files:
            return jsonify({"error": "No file part"}), 400
        
        file = request.files['file']
        
        # Check if file is empty
        if file.filename == '':
            return jsonify({"error": "No file selected"}), 400
        
        # Check if file is a PDF
        if not file.filename.lower().endswith('.pdf'):
            return jsonify({"error": "File must be a PDF"}), 400
        
        # Create a unique filename
        unique_id = str(uuid.uuid4())
        pdf_path = os.path.join(TEMP_DIR, f"{unique_id}.pdf")
        html_path = os.path.join(TEMP_DIR, f"{unique_id}.html")
        
        # Save the uploaded file
        file.save(pdf_path)
        logger.info(f"PDF saved to {pdf_path}")
        
        # Convert PDF to HTML using Spire.PDF
        html_content = convert_pdf_to_html(pdf_path, html_path)
        
        # Clean up the temporary PDF file
        try:
            os.remove(pdf_path)
        except Exception as e:
            logger.warning(f"Could not remove temporary PDF file: {e}")
        
        return html_content
    
    except Exception as e:
        logger.error(f"Error in PDF conversion: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/convert-url', methods=['POST'])
def convert_url():
    """Convert a PDF from a URL to HTML"""
    try:
        # Get URL from request body
        data = request.get_json()
        if not data or 'url' not in data:
            return jsonify({"error": "URL is required"}), 400
        
        url = data['url']
        logger.info(f"Processing PDF from URL: {url}")
        
        # Download the PDF file
        response = requests.get(url, stream=True)
        if response.status_code != 200:
            return jsonify({"error": f"Failed to download PDF. Status code: {response.status_code}"}), 400
        
        # Create temporary files
        unique_id = str(uuid.uuid4())
        pdf_path = os.path.join(TEMP_DIR, f"{unique_id}.pdf")
        html_path = os.path.join(TEMP_DIR, f"{unique_id}.html")
        
        # Save the downloaded file
        with open(pdf_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        logger.info(f"Downloaded PDF saved to {pdf_path}")
        
        # Convert PDF to HTML using Spire.PDF
        html_content = convert_pdf_to_html(pdf_path, html_path)
        
        # Clean up the temporary PDF file
        try:
            os.remove(pdf_path)
        except Exception as e:
            logger.warning(f"Could not remove temporary PDF file: {e}")
        
        return html_content
    
    except Exception as e:
        logger.error(f"Error in URL conversion: {str(e)}")
        return jsonify({"error": str(e)}), 500

def convert_pdf_to_html(pdf_path, html_path):
    """Convert PDF to HTML using Spire.PDF"""
    try:
        # Load PDF document
        pdf = PdfDocument()
        pdf.LoadFromFile(pdf_path)
        
        logger.info(f"PDF loaded with {pdf.Pages.Count} pages")
        
        # Configure HTML conversion options
        options = PdfHtmlLayoutFormat()
        options.IsEmbedImages = True
        options.IsEmbedFonts = True
        options.IsEmbedCss = True
        
        # Convert to HTML
        with open(html_path, 'w', encoding='utf-8') as html_file:
            # Initialize HTML string with necessary styling
            html_content = """
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <style>
                    .pdf-page {
                        position: relative;
                        margin-bottom: 20px;
                        background-color: white;
                        box-shadow: 0 0 10px rgba(0,0,0,0.3);
                        transform-origin: top center;
                    }
                    .text-layer {
                        position: absolute;
                        top: 0;
                        left: 0;
                        right: 0;
                        bottom: 0;
                        overflow: hidden;
                        user-select: text;
                        pointer-events: auto;
                    }
                    .pdf-text {
                        position: absolute;
                        white-space: pre;
                        cursor: text;
                        transform-origin: 0% 0%;
                    }
                </style>
            </head>
            <body>
            """
            
            # Process each page
            for i in range(pdf.Pages.Count):
                page = pdf.Pages[i]
                page_width = page.Size.Width
                page_height = page.Size.Height
                
                # Add page div
                html_content += f'<div class="pdf-page" style="width:{page_width}px;height:{page_height}px;">\n'
                
                # Convert page to HTML
                page_html = HtmlConverter.ToHtml(page, options)
                
                # Create text layer with the HTML content
                html_content += f'<div class="text-layer">{page_html}</div>\n'
                
                # Close page div
                html_content += '</div>\n'
            
            # Close HTML document
            html_content += """
            </body>
            </html>
            """
            
            # Write to file
            html_file.write(html_content)
        
        logger.info(f"HTML saved to {html_path}")
        
        # Read the HTML file to return its content
        with open(html_path, 'r', encoding='utf-8') as html_file:
            content = html_file.read()
        
        # Clean up the HTML file
        try:
            os.remove(html_path)
        except Exception as e:
            logger.warning(f"Could not remove temporary HTML file: {e}")
        
        return content
    
    except Exception as e:
        logger.error(f"Error in PDF to HTML conversion: {str(e)}")
        raise e

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
