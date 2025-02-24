import yaml  # For YAML configuration
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
import json


# --- Font Registration Imports ---
from reportlab.pdfbase import pdfmetrics  # For font metrics
from reportlab.pdfbase.ttfonts import TTFont  # For TrueType fonts

# --- Constants ---
CONFIG_FILE_PATH = 'config.yaml'
PDF_FONT = "CustomReceiptFont"  # Name we will REGISTER for our custom font
DEFAULT_FONT = "Helvetica"  # Fallback font if custom font fails
IMAGE_DPI = 200  # DPI for image conversion

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
        validate_config(config)  # Validate after loading
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
        return font_name  # Return the custom font name
    except Exception as e:
        logger.error(f"Error registering custom font '{font_name}' from '{font_path}': {e}. Using default font.")
        return DEFAULT_FONT  # Fallback to default font


# --- PDF Receipt Creation ---
def create_pdf_receipt(text: str) -> str:
    """Converts text to single-page PDF receipt with dynamic height and margin."""
    logger.info(f"ReportLab Version: {reportlab.__version__}")
    pdf_path = _create_pdf_document(text)
    logger.info(f"PDF receipt created with dynamic height and font at: {pdf_path}")
    return pdf_path


def create_drink_label(order: dict, config: dict) -> str:
    """Creates a PDF label for a drink order."""
    font_path = config['fonts']['custom_font_path_drink']
    font_name = "CustomReceiptFont"
    font_size = config['fonts']['font_size']
    line_height_ratio = config['pdf_style']['line_height_ratio']

    # Register the custom font or fallback to default
    active_font = register_custom_font(font_path, font_name, font_size, line_height_ratio)

    # Create a temporary PDF file
    pdf_file = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    pdf_path = pdf_file.name
    pdf_file.close()

    # Create the PDF canvas
    c = canvas.Canvas(pdf_path, pagesize=(config['page_dimensions']['width'] * mm, 100 * mm))
    c.setFont(active_font, font_size)

    # Define padding in millimeters
    padding_mm = config['pdf_style']['padding']  # Adjust this value to increase or decrease padding

    # Draw top separator line
    c.line(config['pdf_style']['margin_left'] * mm, 90 * mm, config['page_dimensions']['width'] * mm - config['pdf_style']['margin_right'] * mm, 90 * mm)

    # Add drink name (with padding)
    c.drawString(config['pdf_style']['margin_left'] * mm, 85 * mm - padding_mm, f"1x {order['drink_name']}")

    # Add date and time (with padding)
    c.setFont(active_font, 10)
    c.drawString(config['pdf_style']['margin_left'] * mm, 80 * mm - padding_mm, order['date_time'])

    # Draw middle separator line (with padding)
    c.line(config['pdf_style']['margin_left'] * mm, 75 * mm - padding_mm, config['page_dimensions']['width'] * mm - config['pdf_style']['margin_right'] * mm, 75 * mm - padding_mm)

    # Add cafe name (with padding)
    cafe_name = "Sample Cafe & Grill"
    c.setFont(active_font, 10)

    # Calculate the width of the text
    text_width = c.stringWidth(cafe_name, active_font, 10)

    # Calculate the x-coordinate for right alignment
    right_margin = config['page_dimensions']['width'] * mm - config['pdf_style']['margin_right'] * mm
    x_coordinate = right_margin - text_width

    # Draw the text at the calculated x-coordinate (with padding)
    c.drawString(x_coordinate, 70 * mm - padding_mm, cafe_name)

    # Draw bottom separator line (with padding)
    c.line(config['pdf_style']['margin_left'] * mm, 65 * mm - padding_mm, config['page_dimensions']['width'] * mm - config['pdf_style']['margin_right'] * mm, 65 * mm - padding_mm)

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
    printer = None  # Initialize printer as None
    try:
        config = load_config(CONFIG_FILE_PATH)

        # Example JSON payload for a drink order
        example_order_json = '''
        {
            "drink_name": "Espresso",
            "date_time": "2023-10-05 14:30",
            "ingredients": ["Coffee", "Water"]
        }
        '''

        # Process the drink order
        process_drink_order(example_order_json, config)

    except FileNotFoundError as e:  # Handle config file not found error
        logger.error(f"Configuration File Error: {e}")
        exit(1)
    except ValueError as e:  # Handle config validation errors
        logger.error(f"Configuration Error: {e}")
        exit(1)
    except Exception as e:  # Handle other main application errors
        logger.error(f"Main application error: {e}", exc_info=True)
        exit(1)
    finally:
        if 'printer' in locals() and printer:
            printer.close()
            logger.info("Printer connection closed.")