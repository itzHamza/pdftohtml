#!/usr/bin/env python3
import os
import io
import uuid
import base64
import tempfile
import logging
from pathlib import Path
from typing import Tuple, List, Dict, Any

# PDF text extraction
from pdfminer.high_level import extract_pages
from pdfminer.layout import LTTextContainer, LTChar, LTPage

# PDF rendering to images
from pdf2image import convert_from_path, convert_from_bytes
from PIL import Image

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class AlternativePdfConverter:
    """
    Alternative PDF to HTML converter that uses pdfminer.six for text extraction
    and pdf2image for visual representation when pdf2htmlEX is not available.
    """
    
    def __init__(self, temp_dir=None):
        """Initialize the converter with a temporary directory"""
        self.temp_dir = temp_dir or tempfile.gettempdir()
        
    def convert_pdf_to_html(self, pdf_path: str) -> Tuple[str, str]:
        """
        Convert PDF to HTML with selectable text overlaid on page images
        
        Args:
            pdf_path: Path to the PDF file
            
        Returns:
            Tuple[str, str]: HTML content and output path
        """
        logger.info(f"Converting PDF to HTML using alternative method: {pdf_path}")
        
        # Create output directory
        output_dir = os.path.join(self.temp_dir, str(uuid.uuid4()))
        os.makedirs(output_dir, exist_ok=True)
        
        filename = os.path.basename(pdf_path)
        output_filename = os.path.splitext(filename)[0] + '.html'
        output_path = os.path.join(output_dir, output_filename)
        
        try:
            # 1. Extract text and positions from PDF
            page_texts = self._extract_text_with_positions(pdf_path)
            
            # 2. Convert PDF pages to images
            page_images = self._convert_pdf_to_images(pdf_path)
            
            # 3. Generate HTML with text overlay on images
            html_content = self._generate_html(page_texts, page_images)
            
            # Save the HTML file
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(html_content)
                
            logger.info(f"PDF successfully converted to HTML: {output_path}")
            return html_content, output_path
            
        except Exception as e:
            logger.error(f"Error in alternative PDF conversion: {str(e)}")
            raise
    
    def _extract_text_with_positions(self, pdf_path: str) -> List[Dict[str, Any]]:
        """
        Extract text and position information from each page of the PDF
        
        Args:
            pdf_path: Path to the PDF file
            
        Returns:
            List of dictionaries with page text elements and their positions
        """
        logger.info("Extracting text with positions from PDF")
        pages = []
        
        for page_layout in extract_pages(pdf_path):
            page_number = page_layout.pageid
            page_width = page_layout.width
            page_height = page_layout.height
            
            text_elements = []
            
            # Extract text elements with their positions
            for element in page_layout:
                if isinstance(element, LTTextContainer):
                    text = element.get_text().strip()
                    if not text:
                        continue
                        
                    # Get bounding box coordinates (x0, y0, x1, y1)
                    x0, y0, x1, y1 = element.bbox
                    
                    # Convert PDF coordinates (origin at bottom-left) to HTML/image coordinates (origin at top-left)
                    # and scale to percentage for responsive layout
                    left = (x0 / page_width) * 100
                    # Flip y-coordinate since PDF origin is bottom-left but HTML is top-left
                    top = ((page_height - y1) / page_height) * 100
                    width = ((x1 - x0) / page_width) * 100
                    height = ((y1 - y0) / page_height) * 100
                    
                    # Get font information if available
                    font_name = "Arial"
                    font_size = 12
                    
                    for text_line in element:
                        for char in text_line:
                            if isinstance(char, LTChar):
                                font_name = char.fontname
                                font_size = char.size
                                break
                        if font_name != "Arial":
                            break
                    
                    text_elements.append({
                        'text': text,
                        'left': left,
                        'top': top,
                        'width': width,
                        'height': height,
                        'font_name': font_name,
                        'font_size': font_size
                    })
            
            pages.append({
                'page_number': page_number,
                'width': page_width,
                'height': page_height,
                'text_elements': text_elements
            })
            
        logger.info(f"Extracted text from {len(pages)} pages")
        return pages
    
    def _convert_pdf_to_images(self, pdf_path: str) -> List[str]:
        """
        Convert PDF pages to base64-encoded image strings
        
        Args:
            pdf_path: Path to the PDF file
            
        Returns:
            List of base64-encoded image strings for each page
        """
        logger.info("Converting PDF pages to images")
        
        # Convert PDF to list of PIL Images with high DPI for better quality
        images = convert_from_path(pdf_path, dpi=150)
        
        # Convert each image to base64-encoded string
        base64_images = []
        for i, img in enumerate(images):
            image_io = io.BytesIO()
            img.save(image_io, format='PNG')
            encoded_image = base64.b64encode(image_io.getvalue()).decode('utf-8')
            base64_images.append(f"data:image/png;base64,{encoded_image}")
        
        logger.info(f"Converted {len(base64_images)} PDF pages to images")
        return base64_images
    
    def _generate_html(self, page_texts: List[Dict[str, Any]], page_images: List[str]) -> str:
        """
        Generate HTML with text overlay on page images
        
        Args:
            page_texts: List of dictionaries with page text elements and positions
            page_images: List of base64-encoded image strings for each page
            
        Returns:
            HTML content as string
        """
        logger.info("Generating HTML with text overlay")
        
        # Start HTML document
        html = [
            '<!DOCTYPE html>',
            '<html lang="en">',
            '<head>',
            '  <meta charset="UTF-8">',
            '  <meta name="viewport" content="width=device-width, initial-scale=1.0">',
            '  <title>PDF Document</title>',
            '  <style>',
            '    body { margin: 0; padding: 0; background-color: #f0f0f0; font-family: Arial, sans-serif; }',
            '    .pdf-container { display: flex; flex-direction: column; align-items: center; }',
            '    .pdf-page { position: relative; margin-bottom: 20px; box-shadow: 0 2px 5px rgba(0,0,0,0.2); background-color: white; }',
            '    .page-image { width: 100%; height: auto; display: block; }',
            '    .text-layer { position: absolute; top: 0; left: 0; right: 0; bottom: 0; overflow: hidden; opacity: 1; line-height: 1; }',
            '    .text-element { position: absolute; white-space: pre; cursor: text; transform-origin: 0% 0%; pointer-events: all; }',
            '    .text-element:hover { background-color: rgba(180, 0, 170, 0.2); }',
            '  </style>',
            '</head>',
            '<body>',
            '  <div class="pdf-container">'
        ]
        
        # Process each page
        for i, (page_text, page_image) in enumerate(zip(page_texts, page_images)):
            page_number = i + 1
            aspect_ratio = page_text['height'] / page_text['width']
            
            # Page container
            html.append(f'    <div id="page-{page_number}" class="pdf-page" style="width: 100%; max-width: 1000px;">')
            
            # Page image with base64 encoding
            html.append(f'      <img class="page-image" src="{page_image}" alt="Page {page_number}" '
                        f'style="aspect-ratio: {1/aspect_ratio};">')
            
            # Text layer
            html.append('      <div class="text-layer">')
            
            # Add each text element
            for elem in page_text['text_elements']:
                escaped_text = elem['text'].replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                
                # Position the text element using absolute positioning with percentages
                html.append(f'        <div class="text-element pdf-text" '
                            f'style="left: {elem["left"]}%; top: {elem["top"]}%; '
                            f'width: {elem["width"]}%; height: {elem["height"]}%; '
                            f'font-size: {elem["font_size"] * 0.8}px;">'
                            f'{escaped_text}</div>')
            
            html.append('      </div>')  # End text layer
            html.append('    </div>')    # End page container
        
        # End HTML document
        html.extend([
            '  </div>',
            '  <script>',
            '    // Script to make text selectable and apply any needed interactivity',
            '    document.addEventListener("DOMContentLoaded", function() {',
            '      const textElements = document.querySelectorAll(".text-element");',
            '      textElements.forEach(el => {',
            '        el.style.userSelect = "text";',
            '        el.style.cursor = "text";',
            '      });',
            '    });',
            '  </script>',
            '</body>',
            '</html>'
        ])
        
        return '\n'.join(html)


def convert_from_file(pdf_path: str) -> Tuple[str, str]:
    """
    Convert PDF file to HTML (helper function)
    
    Args:
        pdf_path: Path to the PDF file
        
    Returns:
        Tuple[str, str]: HTML content and output path
    """
    converter = AlternativePdfConverter()
    return converter.convert_pdf_to_html(pdf_path)


def convert_from_bytes(pdf_bytes: bytes) -> Tuple[str, str]:
    """
    Convert PDF bytes to HTML (helper function)
    
    Args:
        pdf_bytes: PDF content as bytes
        
    Returns:
        Tuple[str, str]: HTML content and output path
    """
    # Save bytes to temporary file
    with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp:
        tmp.write(pdf_bytes)
        tmp_path = tmp.name
    
    try:
        # Convert the temporary file
        converter = AlternativePdfConverter()
        return converter.convert_pdf_to_html(tmp_path)
    finally:
        # Clean up the temporary file
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


if __name__ == "__main__":
    # Example usage
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python alternative_converter.py <pdf_file>")
        sys.exit(1)
        
    pdf_file = sys.argv[1]
    if not os.path.exists(pdf_file):
        print(f"Error: File {pdf_file} does not exist")
        sys.exit(1)
        
    html_content, output_path = convert_from_file(pdf_file)
    print(f"PDF converted to HTML: {output_path}")
