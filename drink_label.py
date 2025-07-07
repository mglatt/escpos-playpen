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
from PIL import Image

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

def print_image_simple(image_file: str, config: dict):
    """Print image using the exact same method as the working simple script."""
    try:
        # Get printer settings - use exact same approach as simple script
        vendor_id = int(config['printers']['shared']['vendor_id'], 16)
        product_id = int(config['printers']['shared']['product_id'], 16)
        printer_config = get_printer_for_script('drinks', config)
        serial_number = printer_config['serial_number']
        profile = printer_config['profile']
        
        # Initialize printer - exact same way as simple script
        usb_args = {'custom_match': getPrinterWithSerial(serial_number)}
        printer = Usb(vendor_id, product_id, usb_args, profile=profile)
        
        # Set center alignment for image
        printer._raw(b'\x1ba\x01')  # Center align
        time.sleep(0.1)
        
        # Load and print image - exact same way as simple script
        img = Image.open(image_file)
        printer.image(img)
        
        # Don't cut - let the text portion handle the cut
        # printer.cut()  # Removed this line
        
        # Close connection - exact same way as simple script
        printer.close()
        
        logger.info(f"Image {image_file} printed successfully (centered, no cut)")
        return True
        
    except Exception as e:
        logger.error(f"Simple image print failed: {e}")
        return False

def find_customer_image(customer_name: str) -> str:
    """Look for customer's image in drink_images folder in the same directory as the script."""
    try:
        # Get the script directory
        script_dir = os.path.dirname(os.path.abspath(__file__))
        logger.info(f"Script directory: {script_dir}")
        
        # Look for drink_images folder in the same directory as the script
        drink_images_dir = os.path.join(script_dir, 'drink_images')
        logger.info(f"Looking for drink_images directory at: {drink_images_dir}")
        
        # Check if drink_images directory exists
        if not os.path.exists(drink_images_dir):
            logger.warning(f"drink_images directory does not exist: {drink_images_dir}")
            return None
        
        # Clean up customer name for filename (remove spaces, convert to lowercase)
        clean_name = customer_name.lower().replace(' ', '').replace("'", "")
        logger.info(f"Cleaned customer name: '{customer_name}' -> '{clean_name}'")
        
        # Look for the image file
        image_file = os.path.join(drink_images_dir, f"{clean_name}.bmp")
        logger.info(f"Looking for image file: {image_file}")
        
        if os.path.exists(image_file):
            logger.info(f"Found customer image: {image_file}")
            return image_file
        else:
            logger.info(f"No image found for customer '{customer_name}' (looked for: {image_file})")
            
            # List what files are actually in the directory for debugging
            try:
                files_in_dir = os.listdir(drink_images_dir)
                logger.info(f"Files in drink_images directory: {files_in_dir}")
            except:
                logger.warning("Could not list files in drink_images directory")
            
            return None
            
    except Exception as e:
        logger.warning(f"Error looking for customer image: {e}")
        return None
def print_stylized_drink_label(printer: Usb, order: dict):
    """Prints a visually appealing drink label (text only) with center alignment."""
    if not printer:
        logger.warning("Printer not initialized, cannot print")
        return
    
    try:
        # IMPORTANT: Reset printer state completely at start (for TM-L90 compatibility)
        printer._raw(b'\x1b@')  # Initialize printer (reset all settings)
        time.sleep(0.2)
        printer._raw(b'\x1b!\x00')  # Reset font/size
        printer._raw(b'\x1dB\x00')  # Turn off inverted
        printer._raw(b'\x1bE\x00')  # Turn off bold
        printer._raw(b'\x1b-\x00')  # Turn off underline
        printer._raw(b'\x1ba\x01')  # Center align
        time.sleep(0.2)
        
        # Add whitespace padding after image
        printer.text('\n\n\n')  # Three lines of spacing
        
        # Top decorative header with coffee theme - centered
        printer.text('* * *  DRINK ORDER  * * *\n')
        printer.text('▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄\n')
        printer.text('\n')
        
        # Customer name - use inverted + double both with timing for TM-L90 compatibility
        customer_name = order.get('customer_name', 'Customer')
        
        # Add delay for TM-L90 compatibility
        time.sleep(0.1)
        printer._raw(b'\x1dB\x01')  # Inverted (white on black) on
        time.sleep(0.1) 
        printer._raw(b'\x1b!\x30')  # ESC ! 48 (double width + double height)
        time.sleep(0.1)
        printer.text(customer_name)
        time.sleep(0.1)
        printer._raw(b'\x1b!\x00')  # Reset size first
        time.sleep(0.1)
        printer._raw(b'\x1dB\x00')  # Inverted off
        printer.text('\n\n')
        
        # Decorative separator with dots - centered
        printer.text('• • • • • • • • • • • • • • • •\n\n')
        
        # Date and time formatting (normal size) - centered
        try:
            date_obj = datetime.strptime(order['date_time'], "%B %d %Y %I:%M %p")
            date_str = date_obj.strftime("%b %d, %Y")
            time_str = date_obj.strftime("%I:%M %p")
            
            printer.text(f"{date_str}\n")
            printer.text(f"{time_str}\n")
        except Exception as e:
            logger.warning(f"Date formatting error: {e}")
            printer.text("Date/Time error\n")
        
        # Double line separator - centered
        printer.text('\n')
        printer.text('═══════════════════════════════\n')
        printer.text('═══════════════════════════════\n')
        printer.text('\n')
        
        # Drink name - use direct ESC/POS for double width - centered
        drink_name = order.get('drink_name', 'Drink')
        printer._raw(b'\x1b!\x20')  # ESC ! 32 (double width only)
        printer.text(drink_name)
        printer._raw(b'\x1b!\x00')  # ESC ! 0 (reset to normal)
        printer.text('\n\n')
        
        # Modifiers - centered
        if 'modifiers' in order and order['modifiers']:
            for modifier in order['modifiers']:
                mod_text = modifier[:30]  # Truncate if too long
                printer.text(f'+ {mod_text}\n')
        
        # Simple bottom line - centered
        printer.text('\n')
        printer.text('▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄\n')
        
        # IMPORTANT: Final cleanup and proper cut (for TM-L90)
        printer._raw(b'\x1b!\x00')  # Reset font/size
        printer._raw(b'\x1dB\x00')  # Turn off inverted
        printer._raw(b'\x1ba\x00')  # Reset to left align
        time.sleep(0.3)  # Wait before cutting
        printer.text('\n\n')  # Extra spacing
        printer.cut()
        time.sleep(0.3)  # Wait after cutting
        
        logger.info("Stylized centered drink label printed successfully")
        
    except Exception as e:
        logger.error(f"Error printing stylized label: {e}")
        # Ultra-simple fallback
        printer.text("DRINK LABEL\n")
        printer.text("=" * 20 + "\n")
        printer.text(f"{order.get('customer_name', 'Customer')}\n")
        printer.text(f"{order.get('drink_name', 'Drink')}\n")
        printer.text("=" * 20 + "\n")
        printer.cut()

def process_drink_order(order_json: str, config: dict):
    """Processes a drink order using stylized text formatting with automatic customer image lookup."""
    try:
        logger.info("TESTING - process_drink_order function called")
        
        # Parse the JSON payload
        order = json.loads(order_json)
        customer_name = order.get('customer_name', 'Customer')

        logger.info(f"Processing drink order for {customer_name}")

        # Automatically look for customer's image
        logger.info("Looking for customer image...")
        customer_image = find_customer_image(customer_name)

        # Print image first if found (using exact simple script method)
        if customer_image:
            logger.info(f"Printing customer image: {customer_image}")
            image_success = print_image_simple(customer_image, config)
            if image_success:
                logger.info("Customer image printed successfully, waiting before text...")
                time.sleep(2)  # Give printer time to reset
            else:
                logger.warning("Customer image printing failed, continuing with text only")
        else:
            logger.info("No customer image found, printing text only")

        # Print text portion
        logger.info("Printing drink label text...")
        
        # Get printer configuration for drinks script
        vendor_id = int(config['printers']['shared']['vendor_id'], 16)
        product_id = int(config['printers']['shared']['product_id'], 16)
        printer_config = get_printer_for_script('drinks', config)
        
        if not printer_config:
            logger.error("No printer configured for drinks script")
            return
        
        logger.info(f"Using {printer_config['name']} for text (Serial: {printer_config['serial_number']})")

        # Initialize the printer for text
        printer = initialize_printer_by_serial(
            vendor_id, 
            product_id, 
            printer_config['serial_number'], 
            printer_config['profile']
        )
        
        if printer:
            print_stylized_drink_label(printer, order)
            printer.close()
            logger.info("Text portion completed successfully")
        else:
            logger.error(f"Failed to initialize printer for text")

        logger.info("Complete drink order processing finished")

    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON payload: {e}")
    except Exception as e:
        logger.error(f"Error processing drink order: {e}", exc_info=True)

# --- Main Execution ---
if __name__ == "__main__":
    try:
        config = load_config(CONFIG_FILE_PATH)

        if len(sys.argv) < 2:
            logger.error("Usage: python drink_label.py '{\"customer_name\": \"Chessie\", \"date_time\": \"July 06 2025 12:40 PM\", \"drink_name\": \"Large Coffee\", \"modifiers\": [\"Extra Shot\", \"Oat Milk\"]}'")
            logger.info("Customer images will be automatically loaded from ../drink_images/customername.bmp")
            exit(1)

        order_json = sys.argv[1]
        
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