from flask import Flask, request, jsonify
import fitz  # PyMuPDF
import base64
import io
from PIL import Image
import re
import uuid
import os
from flask_cors import CORS

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

def sanitize_text(text):
    """Clean up text extracted from PDF"""
    # Remove excessive whitespace
    text = re.sub(r'\s+', ' ', text)
    # Escape HTML special characters
    text = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    return text.strip()

def get_image_data_url(img):
    """Convert image to base64 data URL"""
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
        images = page.get_images(full=True)
        for img_index, img_info in enumerate(images):
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
                    
                    # Add image with positioning
                    html_parts.append(
                        f'<img class="pdf-image" src="{data_url}" style="'
                        f'left:{x0}px;top:{y0}px;width:{x1-x0}px;height:{y1-y0}px;">'
                    )
        
        html_parts.append('</div>')  # Close page div
    
    html_parts.append('</body></html>')
    return ''.join(html_parts)

@app.route('/convert', methods=['POST'])
def convert():
    # Check if request includes file
    if 'file' not in request.files:
        pdf_data = request.data
        if not pdf_data:
            return jsonify({'error': 'No PDF data provided'}), 400
    else:
        pdf_file = request.files['file']
        pdf_data = pdf_file.read()
    
    try:
        # Convert PDF to HTML
        html_content = pdf_to_html(pdf_data)
        return html_content, 200, {'Content-Type': 'text/html'}
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({'status': 'ok'}), 200

if __name__ == '__main__':
    # Explicitly print the port we're trying to use for debugging
    port_env = os.environ.get('PORT')
    print(f"PORT environment variable: {port_env}")
    
    # Try to convert to integer, with more robust error handling
    try:
        if port_env:
            port = int(port_env)
        else:
            port = 8080
    except ValueError:
        print(f"Warning: Invalid PORT value '{port_env}', using default 8080")
        port = 8080
        
    print(f"Starting server on port {port}")
    app.run(host='0.0.0.0', port=port)
