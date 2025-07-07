import yaml
from escpos.printer import Usb
import os
import logging
import json
import sys
import usb.util
import usb.core
import time
from datetime import datetime

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

def print_pantry_label(printer: Usb, label_data: dict):
    """Prints a pantry label using text formatting."""
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
        
        # Item description - use "double both" with smart text wrapping
        description = label_data.get('description', 'Item')
        
        # Smart text wrapping for double-width text
        # For double-width text, we can fit about 15-16 characters per line
        max_chars_per_line = 15
        
        if len(description) <= max_chars_per_line:
            # Short description - center it with size then bold
            printer.text('    ')  # Indentation
            time.sleep(0.1)
            printer._raw(b'\x1b!\x30')  # Size first (double width + double height)
            time.sleep(0.1)
            printer._raw(b'\x1bE\x01')  # Then bold
            time.sleep(0.1)
            printer.text(description)
            time.sleep(0.1)
            printer._raw(b'\x1bE\x00')  # Bold off first
            printer._raw(b'\x1b!\x00')  # Then reset size
            printer.text('\n\n')
        else:
            # Long description - wrap at word boundaries
            words = description.split()
            lines = []
            current_line = []
            current_length = 0
            
            for word in words:
                # Check if adding this word would exceed the line length
                word_length = len(word)
                space_length = 1 if current_line else 0  # Space before word (except first word)
                
                if current_length + space_length + word_length <= max_chars_per_line:
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
            
            # Print each line with size then bold formatting
            for line in lines:
                printer.text('    ')  # Indentation for centering
                time.sleep(0.1)
                printer._raw(b'\x1b!\x30')  # Size first (double width + double height)
                time.sleep(0.1)
                printer._raw(b'\x1bE\x01')  # Then bold
                time.sleep(0.1)
                printer.text(line)
                time.sleep(0.1)
                printer._raw(b'\x1bE\x00')  # Bold off first
                printer._raw(b'\x1b!\x00')  # Then reset size
                printer.text('\n')
            
            printer.text('\n')  # Extra spacing after description
        
        # Extended solid separator between description and date
        printer.text('▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄\n\n')
        
        # Date - use double width for emphasis
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
                    formatted_date = f"{month_name} {int(day)}, {year}"
                else:
                    formatted_date = date_text
            except:
                formatted_date = date_text
        else:
            formatted_date = date_text
        
        # Print formatted date with double width - better centered
        printer.text('      ')  # More indentation for better centering
        time.sleep(0.1)
        printer._raw(b'\x1b!\x20')  # ESC ! 32 (double width only)
        time.sleep(0.1)
        printer.text(formatted_date)
        time.sleep(0.1)
        printer._raw(b'\x1b!\x00')  # Reset to normal
        printer.text('\n\n')
        
        # Extended bottom decorative line
        printer.text('▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄\n')
        
        # IMPORTANT: Final cleanup and proper cut
        printer._raw(b'\x1b!\x00')  # Reset font/size
        printer._raw(b'\x1dB\x00')  # Turn off inverted
        time.sleep(0.3)  # Wait before cutting
        printer.text('\n\n')  # Extra spacing
        printer.cut()
        time.sleep(0.3)  # Wait after cutting
        
        logger.info("Pantry label printed successfully")
        
    except Exception as e:
        logger.error(f"Error printing pantry label: {e}")
        # Simple fallback
        printer.text("PANTRY LABEL\n")
        printer.text("=" * 20 + "\n")
        printer.text(f"{label_data.get('description', 'Item')}\n")
        printer.text(f"{label_data.get('date', 'Date')}\n")
        printer.text("=" * 20 + "\n")
        printer.cut()

def process_pantry_label(label_json: str, config: dict):
    """Processes a pantry label using text formatting."""
    try:
        # Parse the JSON payload
        label_data = json.loads(label_json)

        # Get printer configuration for pantry script
        vendor_id = int(config['printers']['shared']['vendor_id'], 16)
        product_id = int(config['printers']['shared']['product_id'], 16)
        printer_config = get_printer_for_script('pantry', config)
        
        if not printer_config:
            logger.error("No printer configured for pantry script")
            return
        
        logger.info(f"Using {printer_config['name']} for pantry labels (Serial: {printer_config['serial_number']})")

        # Initialize the printer
        printer = initialize_printer_by_serial(
            vendor_id, 
            product_id, 
            printer_config['serial_number'], 
            printer_config['profile']
        )
        
        if printer:
            print_pantry_label(printer, label_data)
            printer.close()
            logger.info("Print job completed successfully")
        else:
            logger.error(f"Failed to initialize printer")

    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON payload: {e}")
    except Exception as e:
        logger.error(f"Error processing pantry label: {e}", exc_info=True)

# --- Main Execution ---
if __name__ == "__main__":
    try:
        config = load_config(CONFIG_FILE_PATH)

        if len(sys.argv) < 2:
            logger.error("Usage: python pantry_label.py '{\"description\": \"Homemade Soup\", \"date\": \"2025-01-15\"}'")
            exit(1)

        label_json = sys.argv[1]
        process_pantry_label(label_json, config)

    except FileNotFoundError as e:
        logger.error(f"Configuration File Error: {e}")
        exit(1)
    except ValueError as e:
        logger.error(f"Configuration Error: {e}")
    except Exception as e:
        logger.error(f"Main application error: {e}", exc_info=True)
        exit(1)