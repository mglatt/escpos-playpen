from flask import Flask, request, jsonify
import subprocess
import os
import yaml

# Load configuration from config.yaml
with open("config.yaml", "r") as config_file:
    config = yaml.safe_load(config_file)

# Configuration
SCRIPT_PATH = config["paths"]["script"]  # Path to the Python script to execute
VENV_PYTHON_PATH = config["paths"]["venv_python"]  # Path to the Python executable in the virtual environment
EXPECTED_PAYLOAD = config["payload"]["expected"]  # Expected payload value

# Initialize Flask app
app = Flask(__name__)

@app.route('/run-script', methods=['POST'])
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
        if not os.path.exists(SCRIPT_PATH):
            return jsonify({
                "success": False,
                "error": f"Script not found at '{SCRIPT_PATH}'."
            }), 404

        if not os.path.exists(VENV_PYTHON_PATH):
            return jsonify({
                "success": False,
                "error": f"Virtual environment Python not found at '{VENV_PYTHON_PATH}'."
            }), 404

        # Run the script using the virtual environment's Python interpreter
        result = subprocess.run([VENV_PYTHON_PATH, SCRIPT_PATH], capture_output=True, text=True)

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