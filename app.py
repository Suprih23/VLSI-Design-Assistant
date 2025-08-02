# app.py

import os
import json
import subprocess
import google.generativeai as genai
from flask import Flask, request, jsonify, render_template
from dotenv import load_dotenv
from PIL import Image
from graphviz import Source # Import for the new tool

# Load environment variables
load_dotenv()

# --- Tool Definitions ---

def save_code_to_file(filename: str, code: str):
    """Saves the given code content into a file with the specified filename."""
    print(f"--- TOOL: Saving code to {filename} ---")
    try:
        with open(filename, 'w') as f:
            f.write(code)
        return json.dumps({"status": "success", "message": f"File '{filename}' saved successfully."})
    except Exception as e:
        return json.dumps({"error": str(e)})

def run_verilog_simulation(testbench_file: str, design_files: str):
    """
    Compiles and runs a Verilog simulation using Icarus Verilog.
    Takes a single testbench filename and a space-separated string of design filenames.
    """
    print(f"--- TOOL: Running simulation for {testbench_file} ---")
    design_files_list = design_files.split()
    try:
        compile_command = ["iverilog", "-o", "simulation_output", testbench_file] + design_files_list
        subprocess.run(compile_command, capture_output=True, text=True, check=True, timeout=15)
        run_command = ["vvp", "simulation_output"]
        run_process = subprocess.run(run_command, capture_output=True, text=True, check=True, timeout=15)
        return json.dumps({"simulation_log": run_process.stdout})
    except FileNotFoundError:
        return json.dumps({"error": "Icarus Verilog not found. Please ensure it is installed and in your system's PATH."})
    except subprocess.CalledProcessError as e:
        return json.dumps({"error": "Simulation failed", "details": e.stderr})
    except subprocess.TimeoutExpired:
        return json.dumps({"error": "Simulation timed out. The testbench might have an infinite loop."})

def generate_circuit_diagram(dot_description: str):
    """
    Generates a circuit diagram image from a DOT language description.
    The DOT language describes the graph structure of the circuit.
    """
    print(f"--- TOOL: Generating diagram from DOT description ---")
    try:
        # Create a 'static' folder if it doesn't exist
        if not os.path.exists('static'):
            os.makedirs('static')
        
        # Renders the diagram and saves it as 'circuit.png' in the 'static' folder
        s = Source(dot_description, filename="circuit", format="png", directory="static")
        s.render(view=False) # view=False prevents it from opening the file automatically
        
        # The frontend can now access this image at the URL '/static/circuit.png'
        return json.dumps({"status": "success", "image_path": "/static/circuit.png"})
    except Exception as e:
        # This can happen if Graphviz software is not installed
        error_message = f"Diagram generation failed. Ensure Graphviz software is installed. Error: {e}"
        print(f"!!! TOOL ERROR: {error_message} !!!")
        return json.dumps({"error": error_message})


# --- API and Model Configuration ---
try:
    genai.configure(api_key=os.environ["GEMINI_API_KEY"])
except KeyError:
    print("FATAL ERROR: GEMINI_API_KEY not found. Please check your .env file.")
    exit()

# Updated System Prompt to include the new diagram tool
SYSTEM_INSTRUCTION = """You are an expert VLSI Design AGENT. Your primary function is to EXECUTE tasks for the user by calling your available tools. DO NOT provide tutorials. DO THE TASK.

Your workflow for a new design request is ALWAYS as follows:
1.  First, generate a description of the circuit's structure using the DOT graph language.
2.  Use the `generate_circuit_diagram` tool to create a visual schematic from the DOT description.
3.  Next, use the `save_code_to_file` tool to write the Verilog design file.
4.  Then, use `save_code_to_file` again to write the Verilog testbench file.
5.  Finally, use the `run_verilog_simulation` tool to execute the simulation.
6.  Analyze all the results and provide a complete summary to the user, including the path to the generated image and whether the simulation passed or failed."""

model = genai.GenerativeModel(
    model_name='gemini-1.5-pro',
    # Updated tools list
    tools=[save_code_to_file, run_verilog_simulation, generate_circuit_diagram],
    system_instruction=SYSTEM_INSTRUCTION
)

chat = model.start_chat(enable_automatic_function_calling=True)

# --- Flask Web Server ---
app = Flask(__name__)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/chat", methods=["POST"])
def handle_chat():
    user_message = request.form.get("message")
    image_file = request.files.get("image")

    if not user_message and not image_file:
        return jsonify({"error": "No message provided"}), 400

    content = []
    if user_message:
        content.append(user_message)
    if image_file:
        try:
            content.append(Image.open(image_file.stream))
        except Exception as e:
            return jsonify({"error": "Invalid image file"}), 400

    try:
        response = chat.send_message(content)
        return jsonify({"reply": response.text})
    except Exception as e:
        print(f"!!! APP ERROR: {e} !!!")
        return jsonify({"error": "An internal error occurred."}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001)
