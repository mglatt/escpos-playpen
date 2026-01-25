# CLAUDE.md - AI Assistant Guide for escpos-playpen

## Project Overview

This is an **ESCPOS-based Thermal Printing System** - a Python application that provides REST API endpoints for printing various types of labels and lists using EPSON thermal printers. The system integrates with Mealie (recipe/shopping list management) and OpenAI (intelligent categorization).

**Primary Use Cases:**
- Printing organized shopping lists (fetched from Mealie, categorized by OpenAI)
- Printing stylized drink order labels (with optional customer images)
- Printing food storage/pantry labels with descriptions and dates

## Codebase Structure

```
escpos-playpen/
├── rest_server.py      # Flask REST API server (main entry point for API access)
├── print.py            # Shopping list printing script (standalone or via API)
├── drink_label.py      # Drink label printing script (standalone or via API)
├── pantry_label.py     # Pantry label printing script (standalone or via API)
├── sample_config.yaml  # Configuration template (copy to config.yaml)
├── drink_images/       # Customer BMP images for drink labels (optional)
│   └── rick.bmp        # Example customer image
├── README.md           # User documentation
├── LICENSE.txt         # MIT License
└── .gitignore          # Excludes config.yaml, logs, fonts, drink_images/**
```

## Key Files and Their Purposes

| File | Purpose | Lines |
|------|---------|-------|
| `rest_server.py` | Flask server with 3 POST endpoints, orchestrates script execution | ~172 |
| `print.py` | Fetches Mealie items, uses OpenAI for categorization, prints formatted shopping list | ~374 |
| `drink_label.py` | Parses drink order JSON, optionally prints customer image, prints styled label | ~348 |
| `pantry_label.py` | Parses pantry label JSON, prints description and date label | ~278 |

## Development Setup

### Prerequisites
- Python 3.7+
- EPSON thermal printers (tested: TM-L90, TM-T88V)
- Linux-based system (recommended)
- USB connection to printers

### Installation
```bash
python3 -m venv venv
source venv/bin/activate
pip install flask pyyaml python-escpos pillow requests openai pyusb

# System dependencies (Ubuntu/Debian)
sudo apt-get install libusb-1.0-0-dev libudev-dev
```

### Configuration
1. Copy `sample_config.yaml` to `config.yaml`
2. Update printer serial numbers (find via `lsusb -v`)
3. Add Mealie API URL and token
4. Add OpenAI API key
5. Set script paths and venv Python path

**Important:** `config.yaml` is gitignored - never commit it.

## Running the Application

### REST API Server
```bash
source venv/bin/activate
python rest_server.py
```

### Standalone Script Execution
```bash
# Shopping list (no arguments)
python print.py

# Drink label (JSON argument required)
python drink_label.py '{"customer_name": "Rick", "date_time": "July 06 2025 12:40 PM", "drink_name": "Large Coffee", "modifiers": ["Extra Shot", "Oat Milk"]}'

# Pantry label (JSON argument required)
python pantry_label.py '{"description": "Homemade Soup", "date": "2025-01-15"}'
```

### API Endpoints
- `POST /process-shopping-list` - Payload: `{"payload": "print shopping list"}`
- `POST /process-drink-order` - Payload: drink order JSON
- `POST /process-pantry-label` - Payload: `{"description": "...", "date": "YYYY-MM-DD"}`

## Code Conventions and Patterns

### Printer Initialization Pattern
All print scripts use the same printer detection pattern:
```python
def getPrinterWithSerial(serial):
    """Custom USB match function for serial number filtering"""
    # Uses pyusb's custom_match parameter

def initialize_printer_by_serial(vendor_id, product_id, serial_number, profile):
    """Returns Usb object from escpos.printer library"""
```

### Configuration Loading
```python
def load_config():
    with open('config.yaml', 'r') as f:
        return yaml.safe_load(f)
```

### ESC/POS Raw Commands
The codebase uses raw ESC/POS commands for precise formatting:
```python
# Initialize printer
printer._raw(b'\x1b@')

# Text formatting
printer._raw(b'\x1b!\x30')  # Double width + height
printer._raw(b'\x1b!\x20')  # Double width only
printer._raw(b'\x1b!\x00')  # Reset size

# Bold
printer._raw(b'\x1bE\x01')  # Bold on
printer._raw(b'\x1bE\x00')  # Bold off

# Inverted text
printer._raw(b'\x1dB\x01')  # Inverted on
printer._raw(b'\x1dB\x00')  # Inverted off

# Alignment
printer._raw(b'\x1ba\x01')  # Center align
```

### Logging Convention
All scripts use standardized logging:
```python
import logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(handler)
```

### Error Handling
- Wrap printer operations in try-except blocks
- Log errors with `logger.error()` and include traceback
- Provide graceful fallbacks (e.g., simple text if formatting fails)
- Return JSON error responses from REST endpoints

### Timing Delays
Use time delays between printer commands for stability:
```python
time.sleep(0.1)  # Short delay
time.sleep(0.3)  # Longer delay for complex operations
```

## External Integrations

### Mealie API
- **Endpoint:** `/api/households/shopping/items`
- **Auth:** Bearer token
- **Purpose:** Fetch unchecked shopping list items

### OpenAI API
- **Model:** `gpt-4o-mini`
- **Purpose:** Categorize shopping items by grocery store section
- **Parameters:** `temperature=0.7, max_tokens=1000`

## Important Development Notes

### Adding New Print Scripts
1. Create new script following the pattern of existing scripts
2. Include `getPrinterWithSerial()` and `initialize_printer_by_serial()` functions
3. Add configuration for script-to-printer mapping in `sample_config.yaml`
4. Add new endpoint in `rest_server.py` if API access needed
5. Accept JSON via `sys.argv[1]` for command-line invocation

### Multi-Printer Support
The system supports multiple printers with different paper types:
- `sticky_paper`: For labels (TM-L90) - used by drinks, pantry scripts
- `receipt_paper`: For receipts (TM-T88V) - used by shopping, tasks scripts

Script-to-printer mapping is configured in `config.yaml` under each printer's `scripts` array.

### Customer Images for Drink Labels
- Place in `drink_images/` directory
- Format: BMP (recommended for thermal printers)
- Naming: lowercase, no spaces (e.g., "John Smith" -> `johnsmith.bmp`)
- Images are looked up automatically by customer name

### Files to Never Commit
- `config.yaml` (contains API keys and secrets)
- `rest_server.log`
- Font files (`.ttf`)
- Customer images in `drink_images/`

## Testing

Currently no automated test suite. Manual testing approach:
1. Run standalone scripts with test JSON payloads
2. Use curl to test REST endpoints
3. Check printer output and console logs

## Common Tasks

### Find printer serial numbers
```bash
lsusb -v 2>/dev/null | grep -A 10 "EPSON"
```

### Debug printer connection issues
1. Check USB connection: `lsusb`
2. Verify udev rules
3. Check vendor_id/product_id in config
4. Run script with DEBUG logging enabled

### Add a new label type
1. Create new `{type}_label.py` following `pantry_label.py` pattern
2. Add config section for script path
3. Add REST endpoint in `rest_server.py`
4. Update printer `scripts` array in config

## Architecture Notes

- **REST server is a thin wrapper**: Scripts can run standalone or via API
- **Subprocess-based execution**: REST server calls scripts via subprocess with venv Python
- **Config-driven**: Most behavior controlled via YAML config
- **Separate image and text printing**: `drink_label.py` uses two separate printer connections for reliability
