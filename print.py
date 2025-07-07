import yaml
from escpos.printer import Usb
import os
import logging
import json
import requests
import openai
import usb.util
import usb.core
import time

# --- Constants ---
CONFIG_FILE_PATH = 'config.yaml'

# --- Logging Setup ---
root = logging.getLogger()
root.setLevel(logging.DEBUG)
if not root.handlers:
    sh = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    sh.setFormatter(formatter)
    root.addHandler(sh)
logger = logging.getLogger(__name__)

# --- Printer Detection Functions ---
def getPrinterWithSerial(serial):
    """Returns a custom match function for finding a printer with a specific serial number."""
    def isPrinter(dev):
        try:
            hasDeviceClass = dev.bDeviceClass == 0
            if not hasDeviceClass:
                for cfg in dev:
                    if usb.util.find_descriptor(cfg, bInterfaceClass=0) is not None:
                        hasDeviceClass = True
            
            if not hasDeviceClass:
                return False

            serialNumber = usb.util.get_string(dev, dev.iSerialNumber)
            if serialNumber is None:
                return False

            return serialNumber == serial
        except:
            return False
    return isPrinter

def initialize_printer_by_serial(vendor_id: int, product_id: int, serial_number: str, profile: str, timeout: int = 60):
    """Initialize a printer using its serial number."""
    try:
        usb_args = {}
        usb_args['custom_match'] = getPrinterWithSerial(serial_number)
        printer = Usb(vendor_id, product_id, usb_args, timeout=timeout, profile=profile)
        logger.info(f"Successfully initialized printer with serial number: {serial_number}")
        return printer
    except Exception as e:
        logger.error(f"Failed to initialize printer with serial number {serial_number}: {e}")
        return None

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
        return config
    except yaml.YAMLError as e:
        raise ValueError(f"YAML configuration error in {config_file_path}: {e}")

def get_printer_for_script(script_name: str, config: dict):
    """Returns the printer configuration for a given script name."""
    for printer_role, printer_config in config['printers'].items():
        if printer_role == 'shared':
            continue
        if 'scripts' in printer_config and script_name in printer_config['scripts']:
            return printer_config
    
    logger.error(f"No printer configured for script: {script_name}")
    return None

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
    """Filter the shopping list to only include unchecked items."""
    if not shopping_list or 'items' not in shopping_list:
        logger.error("Invalid shopping list format or empty shopping list")
        return []
        
    # Filter only unchecked items
    unchecked_items = [item for item in shopping_list['items'] if not item.get('checked', False)]
    
    logger.info(f"Filtered {len(unchecked_items)} unchecked items from {len(shopping_list['items'])} total items")
    return unchecked_items

def categorize_shopping_list_with_openai(shopping_list: list, openai_api_key: str) -> dict:
    """Categorizes the shopping list by grocery store category using OpenAI's chat.completions.create API."""
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
        '        "Item 1",\n'
        '        "Item 2"\n'
        "      ]\n"
        "    },\n"
        "    {\n"
        '      "category": "Another Category",\n'
        '      "ingredients": [\n'
        '        "Item A",\n'
        '        "Item B"\n'
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

        # Extract the assistant's reply
        assistant_reply = response.choices[0].message.content

        # Parse the JSON response
        categorized_json = json.loads(assistant_reply.strip())
        return categorized_json

    except Exception as e:
        logger.error(f"Error categorizing shopping list with OpenAI: {e}")
        return {}

def print_shopping_list(printer: Usb, categorized_list: dict):
    """Prints a shopping list using clean text formatting with clear hierarchy."""
    if not printer:
        logger.warning("Printer not initialized, cannot print")
        return
    
    try:
        # IMPORTANT: Reset printer state completely at start
        printer._raw(b'\x1b@')  # Initialize printer (reset all settings)
        time.sleep(0.2)
        printer._raw(b'\x1b!\x00')  # Reset font/size
        printer._raw(b'\x1dB\x00')  # Turn off inverted
        printer._raw(b'\x1bE\x00')  # Turn off bold
        printer._raw(b'\x1b-\x00')  # Turn off underline
        time.sleep(0.2)
        
        # Main header - large and prominent
        printer.text('  ')
        time.sleep(0.1)
        printer._raw(b'\x1b!\x30')  # Double width + double height
        time.sleep(0.1)
        printer.text('SHOPPING LIST')
        time.sleep(0.1)
        printer._raw(b'\x1b!\x00')  # Reset size
        printer.text('\n\n')
        
        # Date/time stamp
        from datetime import datetime
        current_time = datetime.now().strftime("%b %d, %Y at %I:%M %p")
        printer.text(f"Generated: {current_time}\n")
        
        # Simple separator
        printer.text('▄' * 40 + '\n\n')
        
        # Process each category
        if 'receipt_items' in categorized_list:
            for category_item in categorized_list['receipt_items']:
                category_name = category_item.get('category', '').strip()
                ingredients = category_item.get('ingredients', [])
                
                if not category_name or not ingredients:
                    continue
                
                # Category header - double width for emphasis
                time.sleep(0.1)
                printer._raw(b'\x1b!\x20')  # Double width only
                time.sleep(0.1)
                printer.text(category_name.upper())
                time.sleep(0.1)
                printer._raw(b'\x1b!\x00')  # Reset size
                printer.text('\n')
                
                # Category separator line
                printer.text('-' * len(category_name.upper()) + '\n')
                
                # Items in this category with checkboxes - smart word wrapping
                for ingredient in ingredients:
                    if ingredient.strip():
                        # Clean up the ingredient text (remove any existing brackets)
                        clean_ingredient = ingredient.strip().replace('[ ]', '').replace('[x]', '').replace('- ', '').strip()
                        
                        # Smart word wrapping for long ingredients
                        # Account for the "[ ] " prefix (4 characters)
                        max_chars_per_line = 36  # Adjust based on your printer width
                        prefix_chars = 4  # "[ ] "
                        available_chars = max_chars_per_line - prefix_chars
                        
                        if len(clean_ingredient) <= available_chars:
                            # Short ingredient - print normally
                            printer.text(f'[ ] {clean_ingredient}\n')
                        else:
                            # Long ingredient - wrap at word boundaries
                            words = clean_ingredient.split()
                            lines = []
                            current_line = []
                            current_length = 0
                            
                            for word in words:
                                word_length = len(word)
                                space_length = 1 if current_line else 0  # Space before word
                                
                                if current_length + space_length + word_length <= available_chars:
                                    # Word fits on current line
                                    current_line.append(word)
                                    current_length += space_length + word_length
                                else:
                                    # Word doesn't fit, start new line
                                    if current_line:  # Don't add empty lines
                                        lines.append(' '.join(current_line))
                                    current_line = [word]
                                    current_length = word_length
                            
                            # Don't forget the last line
                            if current_line:
                                lines.append(' '.join(current_line))
                            
                            # Print the first line with checkbox
                            if lines:
                                printer.text(f'[ ] {lines[0]}\n')
                                
                                # Print continuation lines with indentation
                                for line in lines[1:]:
                                    printer.text(f'    {line}\n')  # 4 spaces to align with text after checkbox
                
                # Space between categories
                printer.text('\n')
        
        # Bottom separator
        printer.text('▄' * 40 + '\n')
        printer.text('Happy Shopping!\n')
        
        # IMPORTANT: Final cleanup and proper cut
        printer._raw(b'\x1b!\x00')  # Reset font/size
        printer._raw(b'\x1dB\x00')  # Turn off inverted
        time.sleep(0.3)  # Wait before cutting
        printer.text('\n\n')  # Extra spacing
        printer.cut()
        time.sleep(0.3)  # Wait after cutting
        
        logger.info("Shopping list printed successfully")
        
    except Exception as e:
        logger.error(f"Error printing shopping list: {e}")
        # Simple fallback
        printer.text("SHOPPING LIST\n")
        printer.text("=" * 30 + "\n")
        printer.text("Error occurred during formatting\n")
        printer.text("=" * 30 + "\n")
        printer.cut()

def process_shopping_list(config: dict):
    """Processes and prints the shopping list using text formatting."""
    try:
        # Get printer configuration for shopping script
        vendor_id = int(config['printers']['shared']['vendor_id'], 16)
        product_id = int(config['printers']['shared']['product_id'], 16)
        printer_config = get_printer_for_script('shopping', config)
        
        if not printer_config:
            logger.error("No printer configured for shopping script")
            return
        
        logger.info(f"Using {printer_config['name']} for shopping list (Serial: {printer_config['serial_number']})")

        # Mealie API Configuration
        MEALIE_API_URL = config['mealie']['api_url']
        MEALIE_API_TOKEN = config['mealie']['api_token']

        # OpenAI API Configuration
        OPENAI_API_KEY = config['openai']['api_key']

        # Fetch Shopping List from Mealie
        shopping_list_data = fetch_shopping_list_from_mealie(MEALIE_API_URL, MEALIE_API_TOKEN)
        if not shopping_list_data:
            logger.error("Failed to fetch shopping list from Mealie.")
            return
            
        # Filter for unchecked items only
        unchecked_items = filter_unchecked_items(shopping_list_data)
        
        if not unchecked_items:
            logger.info("No unchecked items in the shopping list. Nothing to print.")
            return

        # Extract notes/display text from unchecked items only
        raw_items = [item.get('note', item.get('display', '')) for item in unchecked_items]
        logger.debug(f"Raw unchecked items extracted: {raw_items}")

        # Categorize Shopping List with OpenAI
        categorized_list = categorize_shopping_list_with_openai(raw_items, OPENAI_API_KEY)
        if not categorized_list:
            logger.error("Failed to categorize shopping list with OpenAI.")
            return

        # Initialize the printer
        printer = initialize_printer_by_serial(
            vendor_id, 
            product_id, 
            printer_config['serial_number'], 
            printer_config['profile']
        )
        
        if printer:
            print_shopping_list(printer, categorized_list)
            printer.close()
            logger.info("Print job completed successfully")
        else:
            logger.error(f"Failed to initialize printer")

    except Exception as e:
        logger.error(f"Error processing shopping list: {e}", exc_info=True)

# --- Main Execution ---
if __name__ == "__main__":
    try:
        config = load_config(CONFIG_FILE_PATH)
        process_shopping_list(config)

    except FileNotFoundError as e:
        logger.error(f"Configuration File Error: {e}")
        exit(1)
    except ValueError as e:
        logger.error(f"Configuration Error: {e}")
        exit(1)
    except Exception as e:
        logger.error(f"Main application error: {e}", exc_info=True)
        exit(1)