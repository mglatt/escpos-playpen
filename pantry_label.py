import yaml
import reportlab
from escpos.printer import Usb
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import Paragraph, Spacer, SimpleDocTemplate
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from pdf2image import convert_from_path
import os
import logging
import tempfile
from typing import Optional
import json
import sys

# --- Font Registration Imports ---
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# --- Constants ---
CONFIG_FILE_PATH = 'config.yaml'
PDF_FONT = "CustomReceiptFont"
DEFAULT_FONT = "Helvetica"
IMAGE_DPI = 200

# --- Logging Setup ---
root = logging.getLogger()
root.setLevel(logging.DEBUG)
if not root.handlers:
    sh = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    sh.setFormatter(formatter)
    root.addHandler(sh)
logger = logging.getLogger(__name__)

# --- Configuration Loading and Validation ---
def load_config(config_file_path: str) -> dict:
    """Loads and validates configuration from YAML file."""
    if not os.path.exists(config_file_path):
        raise FileNotFoundError(f"Configuration file not found: {config_file_path}")
    try:
        with open(config_file_path, 'r') as yaml_file:
            config = yaml.safe_load(yaml_file)
        if not isinstance(config, dict):
            raise ValueError("Invalid YAML configuration format: root must be a dictionary.")
        validate_config(config)
        return config
    except yaml.YAMLError as e:
        raise ValueError(f"YAML configuration error in {config_file_path}: {e}")

def validate_config(cfg: dict):
    """Validates the configuration dictionary."""
    if not isinstance(cfg, dict):
        raise ValueError("Configuration must be a dictionary.")
    _validate_section(cfg, 'printer', ['vendor_id', 'product_id', 'max_width'])
    _validate_section(cfg, 'fonts', ['custom_font_path_pantry', 'font_size'])
    _validate_section(cfg, 'pdf_style', [
        'margin_left', 'margin_right', 'margin_top',
        'line_height_ratio', 'paragraph_spacing', 'padding'
    ])
    _validate_section(cfg, 'safety_margins', ['percentage', 'minimum'])
    _validate_section(cfg, 'page_dimensions', ['width'])

def _validate_section(cfg: dict, section_name: str, required_options: list):
    """Validates a specific section in the configuration."""
    if not isinstance(cfg.get(section_name), dict):
        raise ValueError(f"Section '{section_name}' must be a dictionary.")
    for opt in required_options:
        if opt not in cfg[section_name]:
            raise ValueError(f"Missing option '{opt}' in '{section_name}' section")

# --- Font Registration ---
def register_custom_font(font_path: str, font_name: str, font_size: int, line_height_ratio: float) -> str:
    """
    Registers a TrueType font with ReportLab.
    Returns the font name to use (custom or default).
    """
    if not font_path:
        logger.warning("Custom font path is not configured in config.yaml. Using default font.")
        return DEFAULT_FONT

    if not os.path.exists(font_path):
        logger.error(f"Custom font file not found at: {font_path}. Using default font.")
        return DEFAULT_FONT

    try:
        pdfmetrics.registerFont(TTFont(font_name, font_path))
        calculated_line_height = font_size * line_height_ratio
        logger.info(f"Custom font '{font_name}' registered from '{font_path}', font size: {font_size}pt, "
                   f"line height ratio: {line_height_ratio}, calculated line height (per style): {calculated_line_height:.2f}pt.")
        return font_name
    except Exception as e:
        logger.error(f"Error registering custom font '{font_name}' from '{font_path}': {e}. Using default font.")
        return DEFAULT_FONT

def create_pantry_label(label_data: dict, config: dict) -> str:
    """Creates a PDF label for a pantry container with description and date."""
    font_path = config['fonts']['custom_font_path_pantry']
    font_name = "CustomReceiptFont"
    font_size = config['fonts']['font_size']
    line_height_ratio = config['pdf_style']['line_height_ratio']
    padding = config['pdf_style']['padding'] * mm

    # Register the custom font or fallback to default
    active_font = register_custom_font(font_path, font_name, font_size, line_height_ratio)

    # Create a temporary PDF file
    pdf_file = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    pdf_path = pdf_file.name
    pdf_file.close()

    # Page dimensions
    page_width = config['page_dimensions']['width'] * mm
    page_height = 60 * mm  # Standard height for pantry label

    # Margins
    left_margin = config['pdf_style']['margin_left'] * mm
    right_margin = page_width - (config['pdf_style']['margin_right'] * mm)
    
    # Usable width
    usable_width = right_margin - left_margin

    # Create the PDF canvas
    c = canvas.Canvas(pdf_path, pagesize=(page_width, page_height))

    # Starting y position - INCREASED to prevent top being cut off
    # Adding extra top margin (15mm from the top instead of standard padding)
    y = page_height - 15 * mm  # Significantly increased top margin

    # Setup for description text
    description = label_data.get('description', '')
    description_font_size = font_size * 1.8  # Larger font for visibility
    
    # Measure text width to determine if we need line wrapping
    c.setFont(active_font, description_font_size)
    text_width = c.stringWidth(description, active_font, description_font_size)
    
    # If text is too wide for the label, split it into multiple lines
    if text_width > usable_width:
        # Calculate approximately how many characters can fit per line
        # This is a rough estimate - proportional fonts will vary
        avg_char_width = text_width / len(description)
        chars_per_line = max(1, int(usable_width / avg_char_width))
        
        # Create a simple word wrap algorithm
        words = description.split()
        lines = []
        current_line = []
        current_width = 0
        
        for word in words:
            # Calculate this word's width
            word_width = c.stringWidth(word, active_font, description_font_size)
            
            # If adding this word exceeds the line width and we already have some words
            if current_width + word_width > usable_width and current_line:
                # Finish the current line
                lines.append(' '.join(current_line))
                current_line = [word]
                current_width = word_width
            else:
                # Add the word to the current line
                current_line.append(word)
                # Add word width plus space width
                current_width += word_width + c.stringWidth(' ', active_font, description_font_size)
        
        # Don't forget the last line
        if current_line:
            lines.append(' '.join(current_line))
        
        # If we have more than 2 lines, reduce the font size slightly
        if len(lines) > 2:
            description_font_size = description_font_size * 0.8
            c.setFont(active_font, description_font_size)
        
        # Draw each line, centered
        for line in lines:
            line_width = c.stringWidth(line, active_font, description_font_size)
            x_position = (page_width - line_width) / 2
            c.drawString(x_position, y, line)
            y -= description_font_size + 2  # Move down for next line
    else:
        # Center the description if it fits on one line
        x_position = (page_width - text_width) / 2
        c.drawString(x_position, y, description)
        y -= description_font_size + 5  # Move down after description

    # Draw separator line - moved up to ensure it's visible
    y -= padding
    c.setLineWidth(2.0)
    c.line(left_margin, y, right_margin, y)
    
    # Add date with large font
    y -= padding + 10
    date_font_size = font_size * 1.5  # Large font for date
    c.setFont(active_font, date_font_size)
    date_text = label_data.get('date', '')
    
    # Format the date nicely if it's in ISO format (YYYY-MM-DD)
    if date_text and len(date_text) == 10 and date_text[4] == '-' and date_text[7] == '-':
        try:
            year = date_text[0:4]
            month = date_text[5:7]
            day = date_text[8:10]
            # Convert month to abbreviated name
            months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
            month_num = int(month)
            if 1 <= month_num <= 12:
                month_name = months[month_num - 1]
                date_text = f"{month_name} {int(day)}, {year}"
        except:
            # If any error in parsing, keep original
            pass
    
    # Center the date
    date_width = c.stringWidth(date_text, active_font, date_font_size)
    x_position = (page_width - date_width) / 2
    c.drawString(x_position, y, date_text)

    c.save()
    return pdf_path

# --- Image Conversion and Resizing ---
def convert_pdf_to_image(pdf_path: str):
    """Converts PDF to PIL Image (first page only)."""
    images = convert_from_path(pdf_path, dpi=IMAGE_DPI)
    if not images:
        raise ValueError(f"No images converted from PDF: {pdf_path}")
    return images[0]

def resize_image_to_width(image, max_width: int):
    """Resizes image to max printer width."""
    width = image.size[0]
    if width > max_width:
        new_height = int((max_width / width) * image.size[1])
        resized_image = image.resize((max_width, new_height))
        logger.info(f"Image resized from {width}px to {max_width}px width.")
        return resized_image
    return image

# --- Printer Interaction ---
def print_image_receipt(printer: Usb, image):
    """Prints PIL Image on ESC/POS printer."""
    if printer:
        printer.image(image)
        printer.cut()
        logger.info("Pantry label printed.")
    else:
        logger.warning("Printer not initialized, cannot print pantry label.")

# --- Pantry Label Processing ---
def process_pantry_label(label_json: str, config: dict):
    """Processes a pantry label JSON payload, generates a PDF label, converts it to an image, and prints it."""
    try:
        # Parse the JSON payload
        label_data = json.loads(label_json)

        # Generate the PDF label
        pdf_path = create_pantry_label(label_data, config)
        logger.info(f"PDF label generated at: {pdf_path}")

        # Convert the PDF to an image
        image = convert_pdf_to_image(pdf_path)
        logger.info("PDF converted to image.")

        # Resize the image to fit the printer width
        max_width = config['printer']['max_width']
        resized_image = resize_image_to_width(image, max_width)
        logger.info(f"Image resized to fit printer width: {max_width}px")

        # Print the image
        printer = Usb(int(config['printer']['vendor_id'], 16), int(config['printer']['product_id'], 16), profile="TM-L90")
        print_image_receipt(printer, resized_image)
        logger.info("Pantry label printed successfully.")

    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON payload: {e}")
    except Exception as e:
        logger.error(f"Error processing pantry label: {e}", exc_info=True)

# --- Main Execution ---
if __name__ == "__main__":
    printer = None
    try:
        config = load_config(CONFIG_FILE_PATH)

        # Get the JSON payload from the command line arguments
        if len(sys.argv) < 2:
            logger.error("No JSON payload provided.")
            exit(1)

        label_json = sys.argv[1]

        # Process the pantry label
        process_pantry_label(label_json, config)

    except FileNotFoundError as e:
        logger.error(f"Configuration File Error: {e}")
        exit(1)
    except ValueError as e:
        logger.error(f"Configuration Error: {e}")
        exit(1)
    except Exception as e:
        logger.error(f"Main application error: {e}", exc_info=True)
        exit(1)
    finally:
        if 'printer' in locals() and printer:
            printer.close()
            logger.info("Printer connection closed.")