# ESCPOS-based Thermal Printing Experiments

A Python-based thermal printing system that provides REST API endpoints for printing shopping lists, drink labels, and pantry labels using EPSON thermal printers. The system integrates with Mealie for shopping list management and OpenAI for intelligent categorization.

## Features

- **Shopping Lists**: Fetches unchecked items from Mealie, categorizes them using OpenAI, and prints organized shopping lists
- **Drink Labels**: Prints stylized drink order labels with optional customer images
- **Pantry Labels**: Prints food storage labels with descriptions and dates
- **Multi-Printer Support**: Supports multiple printers with different paper types and configurations
- **REST API**: Flask-based web server for remote printing requests

## System Requirements

- Python 3.7+
- EPSON thermal printers (tested with TM-L90 and TM-T88V)
- USB connection to printers
- Linux-based system (recommended)

## Installation

### 1. Clone Repository

```bash
git clone <repository-url>
cd thermal-printer-system
```

### 2. Create Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install flask pyyaml python-escpos pillow requests openai pyusb
```

### 4. System Dependencies

For USB printer communication, install system dependencies:

**Ubuntu/Debian:**
```bash
sudo apt-get update
sudo apt-get install libusb-1.0-0-dev libudev-dev
```

**CentOS/RHEL:**
```bash
sudo yum install libusb1-devel systemd-devel
```

### 5. USB Permissions

Probably best to follow instructions here: https://python-escpos.readthedocs.io/en/latest/user/installation.html#setup-udev-for-usb-printers


## Configuration

### 1. Copy Configuration Template

Create a config.yaml file in the project root directory. You can use the existing config.yaml as a reference, but make sure to update it with your specific values.

### 2. Configure Printers

Edit `config.yaml` to match your printer setup:

```yaml
printers:
  shared:
    vendor_id: "0x04b8"  # EPSON vendor ID
    product_id: "0x0202"  # Your printer product ID
    max_width: 576
  
  sticky_paper:
    serial_number: "YOUR_STICKY_PRINTER_SERIAL"
    name: "Sticky Paper Printer"
    profile: "TM-L90"
    scripts: ["drinks", "pantry"] # specify which scripts to use for each printer
    
  receipt_paper:
    serial_number: "YOUR_RECEIPT_PRINTER_SERIAL"
    name: "Receipt Paper Printer"
    profile: "TM-T88V"
    scripts: ["shopping", "tasks"] # here too, make sure you choose which scripts are to be used by each printer!
```

### 3. Configure API Keys

Set up your external service credentials:

```yaml
mealie:
  api_url: "http://your-mealie-instance.com"
  api_token: "your-mealie-api-token"

openai:
  api_key: "your-openai-api-key"
```

### 4. Configure Paths

Update paths to match your system:

```yaml
paths:
  shopping_script: "/path/to/print.py"
  drink_script: "/path/to/drink_label.py"
  pantry_script: "/path/to/pantry_label.py"
  venv_python: "/path/to/venv/bin/python"

payload:
  expected: "print shopping list"
```

### 5. Flask Configuration

Configure the web server:

```yaml
flask:
  host: "0.0.0.0"  # Listen on all interfaces
  port: 5000       # Port number
```

## Project Structure

```
thermal-printer-system/
├── rest_server.py          # Flask web server with API endpoints
├── print.py               # Shopping list printing script
├── drink_label.py         # Drink label printing script
├── pantry_label.py        # Pantry label printing script
├── config.yaml           # Configuration file (create from template)
├── drink_images/          # Customer images for drink labels (optional)
│   ├── rick.bmp
│   └── ...
├── .gitignore
├── LICENSE.txt
└── README.md
```

## Usage

### Starting the Server

Simple to do this in a screen session for development.

```bash
source venv/bin/activate
python rest_server.py
```

The server will start on the configured host and port (default: http://0.0.0.0:5000).

### API Endpoints

#### 1. Shopping List

**Endpoint:** `POST /process-shopping-list`

**Payload:**
```json
{
  "payload": "print shopping list"
}
```

**Description:** Fetches unchecked items from Mealie, categorizes them using OpenAI, and prints an organized shopping list.

#### 2. Drink Labels

**Endpoint:** `POST /process-drink-order`

**Payload:**
```json
{
  "customer_name": "Rick",
  "date_time": "July 06 2025 12:40 PM",
  "drink_name": "Large Coffee",
  "modifiers": ["Extra Shot", "Oat Milk"]
}
```

**Description:** Prints a stylized drink label. If a customer image exists in `drink_images/customername.bmp`, it will be printed above the text.

#### 3. Pantry Labels

**Endpoint:** `POST /process-pantry-label`

**Payload:**
```json
{
  "description": "Homemade Soup",
  "date": "2025-01-15"
}
```

**Description:** Prints a food storage label with description and date.

### Customer Images for Drink Labels

Place customer images in the `drink_images/` directory:

- Format: BMP (recommended for thermal printers)
- Naming: Use lowercase customer name without spaces
- Example: "John Smith" → `johnsmith.bmp`

## Script Usage (Standalone)

Each script can also be run independently:

### Shopping List
```bash
python print.py
```

### Drink Label
```bash
python drink_label.py '{"customer_name": "Rick", "date_time": "July 06 2025 12:40 PM", "drink_name": "Large Coffee", "modifiers": ["Extra Shot", "Oat Milk"]}'
```

### Pantry Label
```bash
python pantry_label.py '{"description": "Homemade Soup", "date": "2025-01-15"}'
```

## Troubleshooting

### Printer Not Found

1. Check USB connection
2. Verify printer serial numbers: `lsusb -v`
3. Ensure proper udev rules and permissions
4. Confirm vendor_id and product_id in config

### Print Quality Issues

1. Check printer paper and ribbon/thermal paper
2. Verify printer profile matches your printer model
3. Adjust safety margins in configuration

### API Connection Issues

1. Verify Mealie API URL and token
2. Check OpenAI API key validity
3. Ensure network connectivity to external services

### Permission Errors

1. Check udev rules are properly configured
2. Verify virtual environment Python path in config

## Dependencies

### Python Packages
- `flask` - Web framework for REST API
- `pyyaml` - YAML configuration file parsing
- `python-escpos` - Thermal printer communication
- `pillow` - Image processing for customer photos
- `requests` - HTTP client for Mealie API
- `openai` - OpenAI API client for categorization
- `pyusb` - USB device communication

### External Services
- **Mealie** - Recipe and shopping list management
- **OpenAI** - AI-powered shopping list categorization

## Configuration Reference

### Printer Profiles
- `TM-L90` - Sticky label printer
- `TM-T88V` - Receipt printer
- Additional profiles available in python-escpos documentation

### Safety Margins
- `percentage` - Dynamic margin as percentage of total height
- `minimum` - Minimum margin in millimeters

### Page Dimensions
- `width` - Page width in millimeters (typically 80mm for thermal printers)

## License

Check out LICESNSE.txt

## Contributing

- PRs welcome!