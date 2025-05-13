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
import logging
from concurrent.futures import ThreadPoolExecutor
import time

# Configure logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# Configuration settings
MAX_WORKERS = 4  # Number of worker threads for parallel processing
FONT_SCALE_FACTOR = 0.85  # Scale down fonts by 15%
IMAGE_QUALITY = 85  # JPEG quality for image compression
CACHE_CONTROL = 'public, max-age=86400'  # Cache for 24 hours
ENABLE_TEXT_SPACING = True  # Add letter-spacing to improve readability

def sanitize_text(text):
    """Clean up text extracted from PDF"""
    # Remove excessive whitespace
    text = re.sub(r'\s+', ' ', text)
    # Escape HTML special characters
    text = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    return text.strip()

def optimize_image(pixmap, quality=IMAGE_QUALITY):
    """Convert pixmap to optimized base64 data URL"""
    try:
        start_time = time.time()
        
        # Determine format based on pixmap characteristics
        img_format = "jpeg" if pixmap.n >= 3 else "png"
        
        # Convert pixmap to PIL Image
        if pixmap.n >= 3:
            pil_img = Image.frombytes("RGB", [pixmap.width, pixmap.height], pixmap.samples)
        else:
            pil_img = Image.frombytes("L", [pixmap.width, pixmap.height], pixmap.samples)
        
        # Optimize image size if larger than threshold
        max_dimension = max(pixmap.width, pixmap.height)
        if max_dimension > 1200:
            scale_factor = 1200 / max_dimension
            new_width = int(pixmap.width * scale_factor)
            new_height = int(pixmap.height * scale_factor)
            pil_img = pil_img.resize((new_width, new_height), Image.LANCZOS)
            
        # Save to bytes buffer with quality setting
        buffer = io.BytesIO()
        if img_format == "jpeg":
            pil_img.save(buffer, format="JPEG", quality=quality, optimize=True)
        else:
            pil_img.save(buffer, format="PNG", optimize=True)
            
        img_str = base64.b64encode(buffer.getvalue()).decode('utf-8')
        
        logger.debug(f"Image optimization took {time.time() - start_time:.2f}s, reduced to {len(img_str)} chars")
        
        # Return as data URL
        return f"data:image/{img_format};base64,{img_str}"
    except Exception as e:
        logger.error(f"Error processing image: {str(e)}")
        logger.error(traceback.format_exc())
        return ""  # Return empty string on error

def process_page(doc, page_num, page):
    """Process a single PDF page (for parallel execution)"""
    try:
        start_time = time.time()
        logger.debug(f"Processing page {page_num+1}")
        
        width, height = page.rect.width, page.rect.height
        
        # Start a new page div
        html_parts = [f'<div class="pdf-page" style="width:{width}px;height:{height}px;">']
        
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
                        
                        # Scale down font size to reduce overlap
                        font_size = span["size"] * FONT_SCALE_FACTOR
                        
                        # Determine text color
                        if isinstance(span["color"], (list, tuple)):
                            r, g, b = span["color"][:3]
                            font_color = f"#{r:02x}{g:02x}{b:02x}"
                        else:
                            # Handle grayscale color
                            color_val = span["color"]
                            font_color = f"#{color_val:02x}{color_val:02x}{color_val:02x}"
                        
                        # Calculate font weight
                        font_flags = span.get("flags", 0)
                        font_weight = "bold" if font_flags & 2**4 else "normal"  # Check if bold flag is set
                        
                        # Calculate letter spacing to reduce overlap
                        letter_spacing = "0.02em" if ENABLE_TEXT_SPACING else "normal"
                        
                        # Add text with improved positioning and styling
                        html_parts.append(
                            f'<div class="pdf-text" style="left:{x0}px;top:{y0}px;'
                            f'font-size:{font_size}px;color:{font_color};'
                            f'font-weight:{font_weight};letter-spacing:{letter_spacing};">{text}</div>'
                        )
                        
        html_parts.append('</div>')  # Close text layer
        
        # Extract and embed images
        images_html = []
        try:
            images = page.get_images(full=True)
            for img_index, img_info in enumerate(images):
                try:
                    if not img_info or len(img_info) < 3:
                        logger.warning(f"Skipping invalid image info on page {page_num+1}")
                        continue
                        
                    # Extract xref from image info
                    xref = img_info[0] if isinstance(img_info[0], int) else img_info[1]
                    
                    # Get the image
                    try:
                        base_img = doc.extract_image(xref)
                        pixmap = fitz.Pixmap(doc, xref)
                    except Exception as e:
                        logger.error(f"Error extracting image {xref}: {str(e)}")
                        continue
                    
                    # Skip problem images
                    if pixmap.width < 10 or pixmap.height < 10 or pixmap.width > 5000 or pixmap.height > 5000:
                        logger.warning(f"Skipping problematic image (size: {pixmap.width}x{pixmap.height}) on page {page_num+1}")
                        continue
                    
                    # Find image position in the page
                    x0, y0, x1, y1 = 0, 0, pixmap.width, pixmap.height
                    for img_block in text_blocks:
                        if img_block.get("type") == 1:  # Image block
                            bbox = img_block.get("bbox")
                            if bbox:
                                x0, y0, x1, y1 = bbox
                    
                    # Convert image to data URL with optimization
                    data_url = optimize_image(pixmap)
                    if data_url:  # Only add if we got a valid data URL
                        # Add image with positioning
                        images_html.append(
                            f'<img class="pdf-image" src="{data_url}" style="'
                            f'left:{x0}px;top:{y0}px;width:{x1-x0}px;height:{y1-y0}px;" '
                            f'loading="lazy" alt="PDF image {img_index}">'
                        )
                except Exception as e:
                    logger.error(f"Error processing image {img_index} on page {page_num+1}: {str(e)}")
                    continue
        except Exception as e:
            logger.error(f"Error extracting images from page {page_num+1}: {str(e)}")
        
        # Append images after text layer for better z-ordering
        html_parts.extend(images_html)
        
        html_parts.append('</div>')  # Close page div
        
        logger.debug(f"Page {page_num+1} processed in {time.time() - start_time:.2f}s")
        return ''.join(html_parts)
    
    except Exception as e:
        logger.error(f"Error processing page {page_num+1}: {str(e)}")
        return f'<div class="error-page">Error rendering page {page_num+1}: {str(e)}</div>'

def pdf_to_html(pdf_data):
    """Convert PDF data to HTML with text and embedded images using parallel processing"""
    start_time = time.time()
    
    # Open the PDF from binary data
    doc = fitz.open(stream=pdf_data, filetype="pdf")
    page_count = len(doc)
    logger.info(f"Converting PDF with {page_count} pages")
    
    # Generate CSS with improved styling
    css = '''
    .pdf-page { 
        position: relative; 
        margin-bottom: 20px; 
        border: 1px solid #ddd; 
        background: white;
        box-shadow: 0 2px 5px rgba(0,0,0,0.1);
        overflow: hidden;
    }
    .text-layer { 
        position: absolute; 
        top: 0; 
        left: 0; 
        right: 0; 
        bottom: 0;
        pointer-events: none;
        line-height: normal;
    }
    .pdf-text { 
        position: absolute; 
        white-space: nowrap;
        transform-origin: left top;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    }
    .pdf-image { 
        position: absolute;
        z-index: 1;
    }
    @media print {
        .pdf-page {
            break-inside: avoid;
            page-break-inside: avoid;
            margin: 0;
            border: none;
            box-shadow: none;
        }
    }
    '''
    
    # Start HTML document
    html_parts = [
        '<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">',
        f'<style>{css}</style>',
        f'<title>PDF Document ({page_count} pages)</title>',
        '</head><body>'
    ]
    
    # Process pages in parallel for better performance
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # Submit all page processing tasks
        future_to_page = {
            executor.submit(process_page, doc, i, page): i 
            for i, page in enumerate(doc)
        }
        
        # Add pages in order as they complete
        for future in sorted(future_to_page, key=lambda x: future_to_page[x]):
            html_parts.append(future.result())
    
    # Add script for lazy loading and visibility optimization
    js_code = '''
    <script>
    document.addEventListener('DOMContentLoaded', function() {
        // Lazy loading for images
        const observer = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    const page = entry.target;
                    // Show images in this page if they were hidden
                    const images = page.querySelectorAll('img[data-src]');
                    images.forEach(img => {
                        img.src = img.dataset.src;
                        img.removeAttribute('data-src');
                    });
                    observer.unobserve(page);
                }
            });
        }, {
            rootMargin: '200px 0px',
            threshold: 0.01
        });
        
        // Observe all pages
        document.querySelectorAll('.pdf-page').forEach(page => {
            observer.observe(page);
        });
    });
    </script>
    '''
    
    html_parts.append(js_code)
    html_parts.append('</body></html>')
    
    final_html = ''.join(html_parts)
    logger.info(f"PDF conversion completed in {time.time() - start_time:.2f}s, generated {len(final_html)} bytes of HTML")
    
    return final_html

@app.route('/convert', methods=['POST'])
def convert():
    try:
        request_start_time = time.time()
        logger.info(f"Received conversion request. Content-Type: {request.content_type}")
        
        # Check if request includes file
        if 'file' not in request.files:
            logger.info("No file in request, trying to read raw data")
            pdf_data = request.data
            if not pdf_data:
                logger.error("No PDF data provided")
                return jsonify({'error': 'No PDF data provided'}), 400
            logger.info(f"Read {len(pdf_data)} bytes of raw PDF data")
        else:
            logger.info("File found in request")
            pdf_file = request.files['file']
            pdf_data = pdf_file.read()
            logger.info(f"Read {len(pdf_data)} bytes from uploaded file")
        
        # Validate PDF data (basic check)
        if len(pdf_data) < 4:
            logger.error(f"PDF data too small: {len(pdf_data)} bytes")
            return jsonify({'error': 'PDF data too small'}), 400
        
        try:
            # Convert PDF to HTML
            html_content = pdf_to_html(pdf_data)
            
            # Calculate performance metrics
            total_time = time.time() - request_start_time
            logger.info(f"Total request processing time: {total_time:.2f}s")
            
            # Set cache headers for better client-side performance
            response_headers = {
                'Content-Type': 'text/html',
                'Cache-Control': CACHE_CONTROL,
                'X-Processing-Time': f"{total_time:.2f}s"
            }
            
            return html_content, 200, response_headers
            
        except Exception as e:
            logger.error(f"Error in pdf_to_html: {str(e)}")
            logger.error(traceback.format_exc())
            return jsonify({'error': f'PDF conversion error: {str(e)}'}), 500
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({'error': f'Server error: {str(e)}'}), 500

@app.route('/health', methods=['GET'])
def health_check():
    version_info = {
        'pymupdf_version': fitz.version[0],
        'flask_version': Flask.__version__,
        'python_version': os.sys.version,
        'workers': MAX_WORKERS,
        'font_scale': FONT_SCALE_FACTOR
    }
    return jsonify({
        'status': 'ok', 
        'versions': version_info,
        'config': {
            'max_workers': MAX_WORKERS,
            'font_scale': FONT_SCALE_FACTOR,
            'image_quality': IMAGE_QUALITY,
            'text_spacing': ENABLE_TEXT_SPACING
        }
    }), 200

@app.route('/config', methods=['GET', 'POST'])
def config():
    global MAX_WORKERS, FONT_SCALE_FACTOR, IMAGE_QUALITY, ENABLE_TEXT_SPACING
    
    if request.method == 'POST':
        try:
            data = request.json
            if data.get('max_workers') is not None:
                MAX_WORKERS = max(1, min(8, int(data['max_workers'])))
            if data.get('font_scale') is not None:
                FONT_SCALE_FACTOR = max(0.5, min(1.5, float(data['font_scale'])))
            if data.get('image_quality') is not None:
                IMAGE_QUALITY = max(50, min(100, int(data['image_quality'])))
            if data.get('text_spacing') is not None:
                ENABLE_TEXT_SPACING = bool(data['text_spacing'])
                
            logger.info(f"Configuration updated: workers={MAX_WORKERS}, font_scale={FONT_SCALE_FACTOR}, "
                      f"image_quality={IMAGE_QUALITY}, text_spacing={ENABLE_TEXT_SPACING}")
            
            return jsonify({'status': 'ok', 'message': 'Configuration updated'})
        except Exception as e:
            logger.error(f"Error updating configuration: {str(e)}")
            return jsonify({'error': f'Configuration update failed: {str(e)}'}), 400
    
    # GET method returns current configuration
    return jsonify({
        'max_workers': MAX_WORKERS,
        'font_scale': FONT_SCALE_FACTOR,
        'image_quality': IMAGE_QUALITY,
        'text_spacing': ENABLE_TEXT_SPACING
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    debug = os.environ.get('FLASK_ENV') == 'development'
    
    # Log startup information
    logger.info(f"Starting PDF to HTML conversion service on port {port}")
    logger.info(f"Workers: {MAX_WORKERS}, Font scale: {FONT_SCALE_FACTOR}")
    
    app.run(host='0.0.0.0', port=port, debug=debug)
