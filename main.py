from flask import Flask, request, jsonify
import fitz  # PyMuPDF
import base64
import io
from PIL import Image
import re
import uuid
import os
import traceback
from flask_cors import CORS

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# Add logging
import logging
logging.basicConfig(level=logging.DEBUG)

def sanitize_text(text):
    """Clean up text extracted from PDF"""
    # Remove excessive whitespace
    text = re.sub(r'\s+', ' ', text)
    # Escape HTML special characters
    text = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    return text.strip()

def get_image_data_url(pixmap):
    """Convert pixmap to base64 data URL"""
    try:
        # Determine format based on pixmap characteristics
        img_format = "jpeg" if pixmap.n >= 3 else "png"
        
        # Convert pixmap to PIL Image
        # For RGB images
        if pixmap.n >= 3:
            pil_img = Image.frombytes("RGB", [pixmap.width, pixmap.height], pixmap.samples)
        # For grayscale images
        else:
            pil_img = Image.frombytes("L", [pixmap.width, pixmap.height], pixmap.samples)
        
        # Save to bytes buffer
        buffer = io.BytesIO()
        pil_img.save(buffer, format=img_format.upper())
        img_str = base64.b64encode(buffer.getvalue()).decode('utf-8')
        
        # Return as data URL
        return f"data:image/{img_format};base64,{img_str}"
    except Exception as e:
        app.logger.error(f"Error processing image: {str(e)}")
        app.logger.error(traceback.format_exc())
        return ""  # Return empty string on error instead of breaking the whole process

def pdf_to_html(pdf_data):
    """Convert PDF data to HTML with text and embedded images"""
    # Open the PDF from binary data
    doc = fitz.open(stream=pdf_data, filetype="pdf")
    
    html_parts = ['<!DOCTYPE html><html><head><meta charset="UTF-8">',
                  '<style>',
                  '.pdf-page { position: relative; margin-bottom: 20px; border: 1px solid #ddd; background: white; }',
                  '.text-layer { position: absolute; top: 0; left: 0; right: 0; bottom: 0; }',
                  '.pdf-text { position: absolute; white-space: nowrap; }',
                  '.pdf-image { position: absolute; }',
                  '</style>',
                  '</head><body>']
    
    # Process each page
    for page_num, page in enumerate(doc):
        try:
            app.logger.info(f"Processing page {page_num+1}/{len(doc)}")
            width, height = page.rect.width, page.rect.height
            
            # Start a new page div
            html_parts.append(f'<div class="pdf-page" style="width:{width}px;height:{height}px;">')
            
            # Extract text with positions
            text_blocks = page.get_text("dict")["blocks"]
            html_parts.append('<div class="text-layer">')
            
            # Process text blocks
            for block in text_blocks:
                if block["type"] == 0:  # Text block
                    for line in block["lines"]:
                        for span in line["spans"]:
                            text = sanitize_text(span["text"])
                            if not text:
                                continue
                                
                            # Get text position and styling
                            x0, y0 = span["origin"]
                            font_size = span["size"]
                            
                            # Check if color is a tuple/list or an integer
                            if isinstance(span["color"], (list, tuple)):
                                font_color = f"#{span['color'][0]:02x}{span['color'][1]:02x}{span['color'][2]:02x}"
                            else:
                                # Handle the case where color is an int (single value)
                                color_val = span["color"]
                                font_color = f"#{color_val:02x}{color_val:02x}{color_val:02x}"
                            
                            # Add text with positioning
                            html_parts.append(
                                f'<div class="pdf-text" style="left:{x0}px;top:{y0}px;'
                                f'font-size:{font_size}px;color:{font_color};">{text}</div>'
                            )
                            
            html_parts.append('</div>')  # Close text layer
            
            # Extract and embed images - FIXED to handle image processing errors
            try:
                images = page.get_images(full=True)
                for img_index, img_info in enumerate(images):
                    try:
                        # Properly handle the img_info tuple unpacking
                        if not img_info or len(img_info) < 3:
                            app.logger.warning(f"Skipping invalid image info on page {page_num+1}: {img_info}")
                            continue
                            
                        # Unpack with proper indexing - this is where the error was likely happening
                        # img_info format varies between PyMuPDF versions
                        xref = img_info[0] if isinstance(img_info[0], int) else img_info[1]
                        
                        # Get the base image
                        try:
                            base_img = doc.extract_image(xref)
                            pixmap = fitz.Pixmap(doc, xref)
                        except Exception as e:
                            app.logger.error(f"Error extracting image {xref}: {str(e)}")
                            continue
                        
                        # Skip problem images
                        if pixmap.width == 0 or pixmap.height == 0:
                            app.logger.warning(f"Skipping zero-sized image on page {page_num+1}")
                            continue
                        
                        # Try to find image position - just use a default if we can't find it
                        x0, y0, x1, y1 = 0, 0, pixmap.width, pixmap.height
                        for img_block in text_blocks:
                            if img_block.get("type") == 1:  # Image block
                                bbox = img_block.get("bbox")
                                if bbox:
                                    x0, y0, x1, y1 = bbox
                        
                        # Convert image to data URL
                        data_url = get_image_data_url(pixmap)
                        if data_url:  # Only add if we got a valid data URL
                            # Add image with positioning
                            html_parts.append(
                                f'<img class="pdf-image" src="{data_url}" style="'
                                f'left:{x0}px;top:{y0}px;width:{x1-x0}px;height:{y1-y0}px;">'
                            )
                    except Exception as e:
                        app.logger.error(f"Error processing image {img_index} on page {page_num+1}: {str(e)}")
                        app.logger.error(traceback.format_exc())
                        continue
            except Exception as e:
                app.logger.error(f"Error extracting images from page {page_num+1}: {str(e)}")
                app.logger.error(traceback.format_exc())
            
            html_parts.append('</div>')  # Close page div
        except Exception as e:
            app.logger.error(f"Error processing page {page_num+1}: {str(e)}")
            app.logger.error(traceback.format_exc())
            # Add an error message in the HTML
            html_parts.append(f'<div class="error-page">Error rendering page {page_num+1}: {str(e)}</div>')
    
    html_parts.append('</body></html>')
    return ''.join(html_parts)

@app.route('/convert', methods=['POST'])
def convert():
    try:
        app.logger.info(f"Received conversion request. Content-Type: {request.content_type}")
        
        # Check if request includes file
        if 'file' not in request.files:
            app.logger.info("No file in request, trying to read raw data")
            pdf_data = request.data
            if not pdf_data:
                app.logger.error("No PDF data provided")
                return jsonify({'error': 'No PDF data provided'}), 400
            app.logger.info(f"Read {len(pdf_data)} bytes of raw PDF data")
        else:
            app.logger.info("File found in request")
            pdf_file = request.files['file']
            pdf_data = pdf_file.read()
            app.logger.info(f"Read {len(pdf_data)} bytes from uploaded file")
        
        # Validate PDF data (basic check)
        if len(pdf_data) < 4:
            app.logger.error(f"PDF data too small: {len(pdf_data)} bytes")
            return jsonify({'error': 'PDF data too small'}), 400
            
        # Check for PDF signature - be more lenient as some valid PDFs might not start with %PDF
        if not pdf_data[:4].startswith(b'%PDF') and not pdf_data[:4].startswith(b'\x25PDF'):
            app.logger.warning(f"PDF signature not found, but continuing anyway")
            
        try:
            # Convert PDF to HTML
            html_content = pdf_to_html(pdf_data)
            app.logger.info(f"Conversion successful, generated {len(html_content)} bytes of HTML")
            return html_content, 200, {'Content-Type': 'text/html'}
        except Exception as e:
            app.logger.error(f"Error in pdf_to_html: {str(e)}")
            app.logger.error(traceback.format_exc())
            return jsonify({'error': f'PDF conversion error: {str(e)}'}), 500
    except Exception as e:
        app.logger.error(f"Unexpected error: {str(e)}")
        app.logger.error(traceback.format_exc())
        return jsonify({'error': f'Server error: {str(e)}'}), 500

@app.route('/health', methods=['GET'])
def health_check():
    version_info = {
        'pymupdf_version': fitz.version[0],
        'flask_version': Flask.__version__,
        'python_version': os.sys.version
    }
    return jsonify({'status': 'ok', 'versions': version_info}), 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))  # Default to 8080 if PORT not set
    app.run(host='0.0.0.0', port=port, debug=True)
