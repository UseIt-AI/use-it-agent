import os
import json
import sys
from typing import Dict, Any

# Set OPENAI_API_KEY
os.environ["OPENAI_API_KEY"] = "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"


# 将项目根目录添加到 python path
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
sys.path.append(project_root)

from llm.run_gpt import run_gpt

def separate_template(base_template_path: str, output_dir: str):
    """
    Reads a base_template.json and uses LLM to split it into component files.
    """
    
    # 1. Read the base template
    if not os.path.exists(base_template_path):
        print(f"Error: File not found {base_template_path}")
        return

    with open(base_template_path, 'r', encoding='utf-8') as f:
        base_data = json.load(f)

    # 2. Read the system prompt
    prompt_path = os.path.join(project_root, "prompt", "template_separation_prompt.md")
    with open(prompt_path, 'r', encoding='utf-8') as f:
        system_prompt = f.read()

    # 3. Prepare the user message
    # We serialize the input JSON to string
    input_json_str = json.dumps(base_data, ensure_ascii=False, indent=2)
    user_content = f"Here is the base_template.json content:\n\n```json\n{input_json_str}\n```\n\nPlease separate this into the component files as defined in the system prompt."

    print("Calling LLM to separate template components (this may take a moment)...")
    
    # 4. Call LLM
    # Using a model capable of handling larger context if possible, or standard o4-mini/gpt-5.1
    response = run_gpt(
        messages=[user_content],
        system=system_prompt,
        llm="gpt-5.1", # Use a capable model for complex JSON restructuring
        response_format={"type": "json_object"} # Force JSON output
    )

    # 5. Parse response
    try:
        # response might be (text, usage) tuple or just text depending on implementation
        if isinstance(response, tuple):
            content = response[0]
        else:
            content = response

        result_files = json.loads(content)
        
        # 6. Write output files
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        for filename, file_content in result_files.items():
            # Ensure filename ends with .json
            if not filename.endswith(".json"):
                filename += ".json"
            
            out_path = os.path.join(output_dir, filename)
            with open(out_path, 'w', encoding='utf-8') as f:
                json.dump(file_content, f, ensure_ascii=False, indent=2)
            print(f"✅ Created: {filename}")

        print(f"\nSeparation complete! Check directory: {output_dir}")

    except json.JSONDecodeError as e:
        print(f"Failed to parse LLM response as JSON: {e}")
        print("Raw response snippet:", content[:200])
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    # Default paths for testing
    base_path = os.path.join(project_root, "drawing", "u_channel_template", "cut_and_fill_canal", "base_template.json")
    out_dir = os.path.join(project_root, "drawing", "u_channel_template", "cut_and_fill_canal")
    
    separate_template(base_path, out_dir)

