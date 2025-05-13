from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import os
import tempfile
import uuid
import requests
from io import BytesIO
import logging
from werkzeug.utils import secure_filename

# Check if Spire.PDF is available, if not use alternative converter
try:
    # Import Spire.PDF for Python
    from spire.pdf import PdfDocument, PdfPageBase
    from spire.pdf.common import PdfHtmlLayoutFormat
    from spire.pdf.conversion import HtmlConverter
    use_spire = True
except ImportError:
    use_spire = False
    # We'll define an alternative conversion method below
    logging.warning("Spire.PDF not found. Using fallback conversion method.")

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create temp directory for storing files if it doesn't exist
TEMP_DIR = os.path.join(tempfile.gettempdir(), 'pdf-converter')
os.makedirs(TEMP_DIR, exist_ok=True)

# Create a requirements variable to help with debugging
required_packages = """
Flask==2.0.1
flask-cors==3.0.10
requests==2.26.0
PyPDF2>=3.0.0
"""

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
    """Convert PDF to HTML using available method"""
    if use_spire:
        return convert_with_spire(pdf_path, html_path)
    else:
        return convert_with_fallback(pdf_path, html_path)

def convert_with_spire(pdf_path, html_path):
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

def convert_with_fallback(pdf_path, html_path):
    """
    Fallback conversion method that uses pdfminer.six if available,
    otherwise returns a simple HTML page
    """
    try:
        # Try to import pdfminer.six
        try:
            from pdfminer.high_level import extract_text_to_fp
            from pdfminer.layout import LAParams
            import io
            
            logger.info("Using pdfminer.six for conversion")
            
            # Extract text from PDF
            output_string = io.StringIO()
            with open(pdf_path, 'rb') as fin:
                extract_text_to_fp(fin, output_string, laparams=LAParams(), 
                                  output_type='html', codec=None)
            
            # Basic styling for the HTML
            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <style>
                    body {{ font-family: Arial, sans-serif; line-height: 1.6; }}
                    .pdf-page {{ 
                        position: relative;
                        margin-bottom: 20px;
                        padding: 20px;
                        background-color: white;
                        box-shadow: 0 0 10px rgba(0,0,0,0.3);
                        transform-origin: top center;
                        width: 800px;
                        margin-left: auto;
                        margin-right: auto;
                    }}
                </style>
            </head>
            <body>
                <div class="pdf-page">
                    {output_string.getvalue()}
                </div>
            </body>
            </html>
            """
            
            # Write HTML to file
            with open(html_path, 'w', encoding='utf-8') as html_file:
                html_file.write(html_content)
                
        except ImportError:
            logger.warning("pdfminer.six not available, using simple text extraction")
            
            # Try to use PyPDF2 as a last resort
            try:
                import PyPDF2
                
                pdf_reader = PyPDF2.PdfReader(pdf_path)
                text_content = ""
                
                # Extract text from each page
                for page_num in range(len(pdf_reader.pages)):
                    page = pdf_reader.pages[page_num]
                    text_content += page.extract_text() + "\n\n"
                
                # Create simple HTML
                html_content = f"""
                <!DOCTYPE html>
                <html>
                <head>
                    <meta charset="UTF-8">
                    <style>
                        body {{ font-family: Arial, sans-serif; line-height: 1.6; }}
                        .pdf-page {{ 
                            position: relative;
                            margin-bottom: 20px;
                            padding: 20px;
                            background-color: white;
                            box-shadow: 0 0 10px rgba(0,0,0,0.3);
                            transform-origin: top center;
                            width: 800px;
                            margin-left: auto;
                            margin-right: auto;
                        }}
                        pre {{ 
                            white-space: pre-wrap;
                            word-wrap: break-word;
                        }}
                    </style>
                </head>
                <body>
                    <div class="pdf-page">
                        <pre>{text_content}</pre>
                    </div>
                </body>
                </html>
                """
                
                # Write HTML to file
                with open(html_path, 'w', encoding='utf-8') as html_file:
                    html_file.write(html_content)
                    
            except ImportError:
                # If all else fails, generate a simple message
                html_content = """
                <!DOCTYPE html>
                <html>
                <head>
                    <meta charset="UTF-8">
                    <style>
                        body { font-family: Arial, sans-serif; text-align: center; padding: 50px; }
                        .error { color: #721c24; background-color: #f8d7da; padding: 20px; border-radius: 5px; }
                    </style>
                </head>
                <body>
                    <div class="error">
                        <h2>PDF Conversion Notice</h2>
                        <p>No PDF conversion libraries are available on this system.</p>
                        <p>Please install one of the following packages:</p>
                        <ul style="text-align: left; display: inline-block;">
                            <li>spire.pdf</li>
                            <li>pdfminer.six</li>
                            <li>PyPDF2</li>
                        </ul>
                    </div>
                </body>
                </html>
                """
                
                # Write HTML to file
                with open(html_path, 'w', encoding='utf-8') as html_file:
                    html_file.write(html_content)
        
        # Read the generated HTML file
        with open(html_path, 'r', encoding='utf-8') as html_file:
            content = html_file.read()
        
        # Clean up the HTML file
        try:
            os.remove(html_path)
        except Exception as e:
            logger.warning(f"Could not remove temporary HTML file: {e}")
        
        return content
        
    except Exception as e:
        logger.error(f"Error in fallback PDF conversion: {str(e)}")
        
        # Return an error message as HTML
        error_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                body {{ font-family: Arial, sans-serif; text-align: center; padding: 50px; }}
                .error {{ color: #721c24; background-color: #f8d7da; padding: 20px; border-radius: 5px; }}
            </style>
        </head>
        <body>
            <div class="error">
                <h2>PDF Conversion Error</h2>
                <p>An error occurred while converting the PDF:</p>
                <p>{str(e)}</p>
            </div>
        </body>
        </html>
        """
        
        return error_html

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
