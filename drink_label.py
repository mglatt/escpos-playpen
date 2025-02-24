import yaml
import reportlab
from escpos.printer import Usb
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import Paragraph, Spacer, SimpleDocTemplate
from reportlab.lib.enums import TA_LEFT
from pdf2image import convert_from_path
import os
import logging
import tempfile
from typing import Optional
import json  # Ensure this import is present
import sys  # For command-line arguments

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
    _validate_section(cfg, 'fonts', ['custom_font_path_drink', 'font_size'])
    _validate_section(cfg, 'pdf_style', [
        'margin_left', 'margin_right', 'margin_top',
        'line_height_ratio', 'paragraph_spacing', 'ingredient_indent'
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

def create_drink_label(order: dict, config: dict) -> str:
    """Creates a PDF label for a drink order matching the sample receipt format."""
    font_path = config['fonts']['custom_font_path_drink']
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
    page_height = 80 * mm

    # Margins
    left_margin = config['pdf_style']['margin_left'] * mm
    right_margin = page_width - (config['pdf_style']['margin_right'] * mm)

    # Create the PDF canvas
    c = canvas.Canvas(pdf_path, pagesize=(page_width, page_height))

    # Starting y position (from top of page)
    y = page_height - padding

    # Add customer name (large)
    c.setFont(active_font, font_size * 1.2)
    c.drawString(left_margin, y, order.get('customer_name', ''))

    # Draw first separator line (thicker)
    y -= padding + 5
    c.setLineWidth(3.0)
    c.line(left_margin, y, right_margin, y)
    c.setLineWidth(1.0)

    # Add date and time
    y -= padding + 10
    c.setFont(active_font, 12)

    # Parse the datetime string
    from datetime import datetime
    date_obj = datetime.strptime(order['date_time'], "%B %d %Y %I:%M %p")

    # Format date and time components
    date_str = date_obj.strftime("%B %d, %Y")
    time_str = date_obj.strftime("%I:%M %p")

    # Draw date (left) and time (right)
    c.drawString(left_margin, y, date_str)
    time_width = c.stringWidth(time_str, active_font, 12)
    c.drawString(right_margin - time_width, y, time_str)

    # Draw second separator line
    y -= padding
    c.line(left_margin, y, right_margin, y)

    # Add drink name with larger font and modifiers with consistent spacing
    y -= padding + 15
    line_spacing = 18

    # Larger font for drink name
    c.setFont(active_font, 18)
    if 'drink_name' in order:
        c.drawString(left_margin, y, order['drink_name'])
        y -= line_spacing + 3

    # Regular font for modifiers
    c.setFont(active_font, 12)
    if 'modifiers' in order:
        for modifier in order['modifiers']:
            c.drawString(left_margin, y, modifier)
            y -= line_spacing

    # Draw bottom separator line
    y += line_spacing / 2
    c.line(left_margin, y, right_margin, y)

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
        logger.info("Receipt page printed.")
    else:
        logger.warning("Printer not initialized, cannot print receipt page.")

# --- Drink Order Processing ---
def process_drink_order(order_json: str, config: dict):
    """Processes a drink order JSON payload, generates a PDF label, converts it to an image, and prints it."""
    try:
        # Parse the JSON payload
        order = json.loads(order_json)

        # Generate the PDF label
        pdf_path = create_drink_label(order, config)
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
        logger.info("Drink label printed successfully.")

    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON payload: {e}")
    except Exception as e:
        logger.error(f"Error processing drink order: {e}", exc_info=True)

# --- Main Execution ---
if __name__ == "__main__":
    printer = None
    try:
        config = load_config(CONFIG_FILE_PATH)

        # Get the JSON payload from the command line arguments
        if len(sys.argv) < 2:
            logger.error("No JSON payload provided.")
            exit(1)

        order_json = sys.argv[1]

        # Process the drink order
        process_drink_order(order_json, config)

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
