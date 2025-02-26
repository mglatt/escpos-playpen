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
import requests
import openai


# --- Font Registration Imports ---
from reportlab.pdfbase import pdfmetrics  # For font metrics
from reportlab.pdfbase.ttfonts import TTFont  # For TrueType fonts

# --- Constants ---
CONFIG_FILE_PATH = 'config.yaml'
PDF_FONT = "CustomReceiptFont"  # Name we will REGISTER for our custom font
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
    _validate_section(cfg, 'fonts', ['custom_font_path_shopping', 'font_size'])
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
def register_custom_font(font_path: str, font_name: str, font_size: int, line_height_ratio: float):
    """Registers a TrueType font with ReportLab."""
    if not font_path:
        logger.warning("Custom font path is not configured in config.yaml. Using default Helvetica font.")
        return

    if not os.path.exists(font_path):
        logger.error(f"Custom font file not found at: {font_path}. Using default Helvetica font.")
        return

    try:
        pdfmetrics.registerFont(TTFont(font_name, font_path))
        calculated_line_height = font_size * line_height_ratio
        logger.info(f"Custom font '{font_name}' registered from '{font_path}', font size: {font_size}pt, "
                   f"line height ratio: {line_height_ratio}, calculated line height (per style): {calculated_line_height:.2f}pt.")
    except Exception as e:
        logger.error(f"Error registering custom font '{font_name}' from '{font_path}': {e}. Using default Helvetica font.")


# --- PDF Receipt Creation ---
def create_pdf_receipt(text: str) -> str:
    """Converts text to single-page PDF receipt with dynamic height and margin."""
    logger.info(f"ReportLab Version: {reportlab.__version__}")
    pdf_path = _create_pdf_document(text)
    logger.info(f"PDF receipt created with dynamic height and font at: {pdf_path}")
    return pdf_path


def _create_pdf_document(text: str) -> str:
    """Helper function to generate the PDF document using ReportLab."""
    pdf_file = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    pdf_path = pdf_file.name
    pdf_file.close()

    styles = getSampleStyleSheet()
    category_header_style = ParagraphStyle(
        name='CategoryHeaderStyle',
        parent=styles['Normal'],
        fontName=PDF_FONT,
        fontSize=PDF_FONT_SIZE,
        leading=PDF_FONT_SIZE * PDF_LINE_HEIGHT_RATIO,
        alignment=TA_LEFT,
        spaceAfter=PDF_FONT_SIZE * 0.5
    )

    ingredient_line_style = ParagraphStyle(
        name='IngredientLineStyle',
        parent=styles['Normal'],
        fontName=PDF_FONT,
        fontSize=PDF_FONT_SIZE,
        leading=PDF_FONT_SIZE * PDF_LINE_HEIGHT_RATIO * 0.8,
        alignment=TA_LEFT,
        leftIndent=INGREDIENT_INDENT  # Dynamically loaded indent
    )

    flowables = []
    paragraphs = text.split('\n\n')  # Split into categories by double newline

    for para_text in paragraphs:
        if not para_text.strip():
            continue

        lines = para_text.split('\n')
        for line in lines:
            if not line.strip():
                continue

            processed_line = line.replace('\n', '<br/>')

            # Check if this is a category header (ends with colon)
            if processed_line.strip().endswith(':'):
                if flowables:  # Add extra space before new category (except first)
                    flowables.append(Spacer(1, PDF_PARAGRAPH_SPACING))
                p = Paragraph(processed_line.strip(), category_header_style)
            else:
                # This is an ingredient line
                p = Paragraph(processed_line.strip(), ingredient_line_style)

            flowables.append(p)

            # Add small space after each line
            flowables.append(Spacer(1, PDF_FONT_SIZE * PDF_LINE_HEIGHT_RATIO * 0.2))

    # Calculate total height needed
    total_height = PDF_MARGIN_TOP
    for flowable in flowables:
        total_height += flowable.wrapOn(None, PDF_PAGE_WIDTH - PDF_MARGIN_LEFT - PDF_MARGIN_RIGHT, 50000*mm)[1]

    total_height += PDF_MARGIN_TOP
    dynamic_page_height = max(total_height, 20 * mm)
    safety_margin = max(dynamic_page_height * SAFETY_MARGIN_PERCENTAGE, MIN_SAFETY_MARGIN)
    page_height_with_margin = dynamic_page_height + safety_margin

    logger.info(f"Calculated dynamic_page_height: {dynamic_page_height/mm} mm, "
                f"Applied Safety Margin: {safety_margin/mm} mm, "
                f"Total Page Height: {page_height_with_margin/mm} mm")

    doc = SimpleDocTemplate(
        pdf_path,
        pagesize=(PDF_PAGE_WIDTH, page_height_with_margin),
        leftMargin=PDF_MARGIN_LEFT,
        rightMargin=PDF_MARGIN_RIGHT,
        topMargin=PDF_MARGIN_TOP,
        bottomMargin=PDF_MARGIN_TOP
    )

    doc.build(flowables)
    return pdf_path


# --- Image Conversion and Resizing ---
def convert_pdf_to_image(pdf_path: str):
    """Converts PDF to PIL Image (first page only)."""
    images = convert_from_path(pdf_path, dpi=IMAGE_DPI)
    if not images:
        raise ValueError(f"No images converted from PDF: {pdf_path}")
    return images[0]


def resize_image_to_width(image):
    """Resizes image to max printer width."""
    width = image.size[0]
    if width > MAX_WIDTH:
        new_height = int((MAX_WIDTH / width) * image.size[1])
        resized_image = image.resize((MAX_WIDTH, new_height))
        logger.info(f"Image resized from {width}px to {MAX_WIDTH}px width.")
        return resized_image
    return image


# --- Printer Interaction ---
def print_image_receipt(printer: Usb, image):
    """Prints PIL Image on ESC/POS printer."""
    if printer:
        printer.image(image)
        logger.info("Receipt page printed.")
    else:
        logger.warning("Printer not initialized, cannot print receipt page.")


# --- Mealie API Integration ---
def fetch_shopping_list_from_mealie(api_url: str, api_token: str):
    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json"
    }
    try:
        response = requests.get(f"{api_url}/api/households/shopping/items", headers=headers)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching shopping list from Mealie: {e}")
        return None


def filter_unchecked_items(shopping_list: dict) -> list:
    """
    Filter the shopping list to only include unchecked items.
    
    Args:
        shopping_list (dict): The complete shopping list from Mealie API
        
    Returns:
        list: List of unchecked shopping items
    """
    if not shopping_list or 'items' not in shopping_list:
        logger.error("Invalid shopping list format or empty shopping list")
        return []
        
    # Filter only unchecked items
    # In Mealie, the checked status is determined by the 'checked' field
    unchecked_items = [item for item in shopping_list['items'] if not item.get('checked', False)]
    
    logger.info(f"Filtered {len(unchecked_items)} unchecked items from {len(shopping_list['items'])} total items")
    return unchecked_items


def categorize_shopping_list_with_openai(shopping_list: list, openai_api_key: str) -> dict:
    """
    Categorizes the shopping list by grocery store category using OpenAI's chat.completions.create API.
    Returns a JSON object containing categorized items.
    """
    # Define the prompt for categorizing the shopping list
    prompt = (
        "Categorize the following shopping list by grocery store category. "
        "Return the result as a JSON object in the following format." 
        "DO NOT RETURN ANYTHING EXCEPT A JSON OBJECT" "\n"
        "{\n"
        '  "receipt_items": [\n'
        "    {\n"
        '      "category": "Category Name",\n'
        '      "ingredients": [\n'
        '        "[ ] - Item 1",\n'
        '        "[ ] - Item 2"\n'
        "      ]\n"
        "    },\n"
        "    {\n"
        '      "category": "Another Category",\n'
        '      "ingredients": [\n'
        '        "[ ] - Item A",\n'
        '        "[ ] - Item B"\n'
        "      ]\n"
        "    }\n"
        "  ]\n"
        "}\n\n"
        "Shopping List:\n" + "\n".join(shopping_list)
    )

    try:
        # Initialize OpenAI client
        openai.api_key = openai_api_key

        # Call the chat.completions.create API
        response = openai.chat.completions.create(
            model="gpt-4o-mini",  # Use gpt-4o-mini or another model
            messages=[
                {"role": "system", "content": "You are an assistant that categorizes shopping lists."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=1000,
            temperature=0.7,
            top_p=1.0,
            frequency_penalty=0.0,
            presence_penalty=0.0
        )

        # Log the raw response for debugging
        logger.debug(f"Raw API response: {response}")

        # Extract the assistant's reply
        assistant_reply = response.choices[0].message.content

        # Log the assistant's reply for debugging
        logger.debug(f"Assistant reply: {assistant_reply}")

        # Parse the JSON response
        categorized_json = json.loads(assistant_reply.strip())
        return categorized_json

    except Exception as e:
        logger.error(f"Error categorizing shopping list with OpenAI: {e}")
        return {}


# --- Helper Functions ---
def _extract_text_from_payload(payload: dict) -> str:
    """Helper function to extract and format text from structured JSON payload."""
    if not isinstance(payload, dict):
        raise ValueError("Invalid payload format: expected dictionary")

    if 'receipt_items' not in payload:
        raise ValueError("JSON payload missing 'receipt_items' key")

    formatted_text = []

    for category_item in payload['receipt_items']:
        if not isinstance(category_item, dict):
            continue

        category_name = category_item.get('category', '').strip()
        if category_name:
            formatted_text.append(f"{category_name}:")

        ingredients = category_item.get('ingredients', [])
        if ingredients:
            for ingredient in ingredients:
                formatted_text.append(f"    {ingredient}")

        formatted_text.append('')

    return '\n'.join(formatted_text).strip()


# --- Main Execution ---
if __name__ == "__main__":
    printer = None  # Initialize printer as None
    try:
        config = load_config(CONFIG_FILE_PATH)

        # Printer Configuration
        PRINTER_VENDOR_ID = int(config['printer']['vendor_id'], 16)
        PRINTER_PRODUCT_ID = int(config['printer']['product_id'], 16)
        MAX_WIDTH = int(config['printer']['max_width'])

        # Fonts Configuration
        CUSTOM_FONT_PATH = config['fonts']['custom_font_path_shopping']
        PDF_FONT_SIZE = int(config['fonts']['font_size'])

        # Register the custom font
        register_custom_font(
            font_path=CUSTOM_FONT_PATH,
            font_name=PDF_FONT,
            font_size=PDF_FONT_SIZE,
            line_height_ratio=float(config['pdf_style']['line_height_ratio'])
        )

        # PDF Style Configuration
        PDF_MARGIN_LEFT = int(config['pdf_style']['margin_left']) * mm
        PDF_MARGIN_RIGHT = int(config['pdf_style']['margin_right']) * mm
        PDF_MARGIN_TOP = int(config['pdf_style']['margin_top']) * mm
        PDF_LINE_HEIGHT_RATIO = float(config['pdf_style']['line_height_ratio'])
        PDF_PARAGRAPH_SPACING = int(config['pdf_style']['paragraph_spacing']) * mm
        INGREDIENT_INDENT = int(config['pdf_style']['ingredient_indent']) * mm

        # Safety Margins Configuration
        SAFETY_MARGIN_PERCENTAGE = float(config['safety_margins']['percentage'])
        MIN_SAFETY_MARGIN = int(config['safety_margins']['minimum']) * mm

        # Page Dimensions Configuration
        PDF_PAGE_WIDTH = int(config['page_dimensions']['width']) * mm

        # Mealie API Configuration
        MEALIE_API_URL = config['mealie']['api_url']
        MEALIE_API_TOKEN = config['mealie']['api_token']

        # OpenAI API Configuration
        OPENAI_API_KEY = config['openai']['api_key']

        # Fetch Shopping List from Mealie
        shopping_list_data = fetch_shopping_list_from_mealie(MEALIE_API_URL, MEALIE_API_TOKEN)
        if not shopping_list_data:
            logger.error("Failed to fetch shopping list from Mealie.")
            exit(1)
            
        # Filter for unchecked items only
        unchecked_items = filter_unchecked_items(shopping_list_data)
        
        if not unchecked_items:
            logger.info("No unchecked items in the shopping list. Nothing to print.")
            exit(0)

        # Extract notes/display text from unchecked items only
        raw_items = [item.get('note', item.get('display', '')) for item in unchecked_items]
        logger.debug(f"Raw unchecked items extracted: {raw_items}")

        # Categorize Shopping List with OpenAI
        categorized_list = categorize_shopping_list_with_openai(raw_items, OPENAI_API_KEY)
        if not categorized_list:
            logger.error("Failed to categorize shopping list with OpenAI.")
            exit(1)

        # Create PDF receipt from categorized list
        text_payload = _extract_text_from_payload(categorized_list)
        pdf_path = create_pdf_receipt(text_payload)
        image = convert_pdf_to_image(pdf_path)
        logger.info("Converted PDF to image.")

        resized_image = resize_image_to_width(image)
        logger.info(f"Resized image width: {resized_image.size[0]}, height: {resized_image.size[1]}, MAX_WIDTH: {MAX_WIDTH}")

        # Print the receipt
        printer = Usb(PRINTER_VENDOR_ID, PRINTER_PRODUCT_ID, profile="TM-L90")
        logger.info("Printer initialized.")
        print_image_receipt(printer, resized_image)
        logger.info("Page printed.")

        if printer:
            printer.cut()
            logger.info("Receipt cut after printing.")

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
        if printer is not None:  # Ensure printer is closed only if initialized
            printer.close()
            logger.info("Printer connection closed.")