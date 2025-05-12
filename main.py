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

def get_image_data_url(img):
    """Convert image to base64 data URL"""
    try:
        # Get image format (default to PNG if unknown)
        img_format = img["colorspace"].name if hasattr(img, "colorspace") and img["colorspace"] else "png"
        if img_format.lower() not in ["rgb", "cmyk", "gray"]:
            img_format = "png"
        else:
            img_format = "jpeg" if img_format.lower() in ["rgb", "cmyk"] else "png"
        
        # Convert pixmap to PIL Image
        pil_img = Image.frombytes("RGB", [img.width, img.height], img.samples)
        
        # Save to bytes buffer
        buffer = io.BytesIO()
        pil_img.save(buffer, format=img_format.upper())
        img_str = base64.b64encode(buffer.getvalue()).decode('utf-8')
        
        # Return as data URL
        return f"data:image/{img_format};base64,{img_str}"
    except Exception as e:
        app.logger.error(f"Error processing image: {str(e)}")
        return ""  # Return empty string on error instead of breaking the whole process

def pdf_to_html(pdf_data):
    """Convert PDF data to HTML with text and embedded images"""
    # Open the PDF from binary data
    doc = fitz.open(stream=pdf_data, filetype="pdf")
    
    html_parts = ['<!DOCTYPE html><html><head><meta charset="UTF-8">',
                  '<style>',
                  '.pdf-page { position: relative; margin-bottom: 20px; }',
                  '.text-layer { position: absolute; top: 0; left: 0; right: 0; bottom: 0; }',
                  '.pdf-text { position: absolute; line-height: 1.2; }',
                  '.pdf-image { position: absolute; }',
                  '</style>',
                  '</head><body>']
    
    # Process each page
    for page_num, page in enumerate(doc):
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
                        font_color = f"#{span['color'][0]:02x}{span['color'][1]:02x}{span['color'][2]:02x}"
                        
                        # Add text with positioning
                        html_parts.append(
                            f'<div class="pdf-text" style="left:{x0}px;top:{y0}px;'
                            f'font-size:{font_size}px;color:{font_color};">{text}</div>'
                        )
                        
        html_parts.append('</div>')  # Close text layer
        
        # Extract and embed images
        try:
            images = page.get_images(full=True)
            for img_index, img_info in enumerate(images):
                try:
                    img_index, xref, smask, *_ = img_info
                    
                    # Get the base image
                    base_img = doc.extract_image(xref)
                    pixmap = fitz.Pixmap(doc, xref)
                    
                    # If we have a mask, apply it
                    if smask > 0:
                        mask_img = fitz.Pixmap(doc, smask)
                        pixmap = fitz.Pixmap(pixmap, mask_img)
                    
                    # Get the image position on the page
                    for img_block in text_blocks:
                        if img_block["type"] == 1:  # Image block
                            bbox = img_block["bbox"]
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
                    app.logger.error(f"Error processing image {img_index} on page {page_num}: {str(e)}")
                    # Continue with the next image instead of breaking
                    continue
        except Exception as e:
            app.logger.error(f"Error extracting images from page {page_num}: {str(e)}")
            # Continue with the next page
        
        html_parts.append('</div>')  # Close page div
    
    html_parts.append('</body></html>')
    return ''.join(html_parts)

@app.route('/convert', methods=['POST'])
def convert():
    try:
        app.logger.info(f"Received conversion request. Content-Type: {request.content_type}")
        app.logger.info(f"Request headers: {request.headers}")
        
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
        
        # Validate PDF data
        if len(pdf_data) < 4 or pdf_data[:4] != b'%PDF':
            app.logger.error("Invalid PDF data - doesn't start with %PDF signature")
            return jsonify({'error': 'Invalid PDF data'}), 400
            
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
    return jsonify({'status': 'ok'}), 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))  # Default to 8080 if PORT not set
    app.run(host='0.0.0.0', port=port, debug=True)
