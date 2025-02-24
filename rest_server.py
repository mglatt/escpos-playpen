from flask import Flask, request, jsonify
import subprocess
import os
import yaml
import json

# Load configuration from config.yaml
with open("config.yaml", "r") as config_file:
    config = yaml.safe_load(config_file)

# Configuration
SHOPPING_SCRIPT_PATH = config["paths"]["shopping_script"]  # Path to the Python script to execute
DRINK_SCRIPT_PATH = config["paths"]["drink_script"]  # Path to the Python script to execute

VENV_PYTHON_PATH = config["paths"]["venv_python"]  # Path to the Python executable in the virtual environment
EXPECTED_PAYLOAD = config["payload"]["expected"]  # Expected payload value

# Initialize Flask app
app = Flask(__name__)

    
# Drink order endpoint  
@app.route('/process-drink-order', methods=['POST'])
def process_drink_order():
    try:
        # Get the JSON payload from the POST request
        order_json = request.json

        # Validate the payload
        if not order_json:
            return jsonify({
                "success": False,
                "error": "No JSON payload provided."
            }), 400

        # Ensure the script and virtual environment paths exist
        if not os.path.exists(DRINK_SCRIPT_PATH):
            return jsonify({
                "success": False,
                "error": f"Script not found at '{DRINK_SCRIPT_PATH}'."
            }), 404

        if not os.path.exists(VENV_PYTHON_PATH):
            return jsonify({
                "success": False,
                "error": f"Virtual environment Python not found at '{VENV_PYTHON_PATH}'."
            }), 404

        # Convert the JSON payload to a string
        order_json_str = json.dumps(order_json)

        # Run the script using the virtual environment's Python interpreter
        result = subprocess.run([VENV_PYTHON_PATH, DRINK_SCRIPT_PATH, order_json_str], capture_output=True, text=True)

        # Return the script output
        return jsonify({
            "success": True,
            "output": result.stdout,
            "error": result.stderr
        }), 200
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

# Shopping list endpoint
@app.route('/process-shopping-list', methods=['POST'])
def run_script():
    try:
        # Get the payload from the POST request
        payload = request.json.get("payload", "").strip().lower()

        # Validate the payload
        if payload != EXPECTED_PAYLOAD:
            return jsonify({
                "success": False,
                "error": f"Invalid payload. Expected '{EXPECTED_PAYLOAD}'."
            }), 400

        # Ensure the script and virtual environment paths exist
        if not os.path.exists(SHOPPING_SCRIPT_PATH):  # Use SHOPPING_SCRIPT_PATH here
            return jsonify({
                "success": False,
                "error": f"Script not found at '{SHOPPING_SCRIPT_PATH}'."
            }), 404

        if not os.path.exists(VENV_PYTHON_PATH):
            return jsonify({
                "success": False,
                "error": f"Virtual environment Python not found at '{VENV_PYTHON_PATH}'."
            }), 404

        # Run the script using the virtual environment's Python interpreter
        result = subprocess.run([VENV_PYTHON_PATH, SHOPPING_SCRIPT_PATH], capture_output=True, text=True)

        # Return the script output
        return jsonify({
            "success": True,
            "output": result.stdout,
            "error": result.stderr
        }), 200
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

if __name__ == '__main__':
    # Get host and port from configuration
    host = config["flask"]["host"]
    port = config["flask"]["port"]
    app.run(host=host, port=port)
