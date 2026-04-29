#!/usr/bin/env python
"""
AutoCAD V2 API Test

Tests:
- GET  /api/v1/autocad/v2/status
- POST /api/v1/autocad/v2/open
- POST /api/v1/autocad/v2/close
- POST /api/v1/autocad/v2/new
- GET  /api/v1/autocad/v2/snapshot
- POST /api/v1/autocad/v2/step
- GET  /api/v1/autocad/v2/standard_parts
- POST /api/v1/autocad/v2/standard_parts/{type}/draw

Usage:
    python -m controllers.autocad_v2.test_api
    python controllers/autocad_v2/test_api.py [mode]
    
Modes:
    demo          - Full demo with all operations (default)
    basic         - Status check only
    snapshot      - Snapshot test only
    draw_json     - Test draw_from_json action
    python_com    - Test execute_python_com action
    standard_part - Test standard part drawing
    all_actions   - Test all action types
    multi_doc     - Test multi-document switching
"""

import requests
import base64
import sys
import time
import io
import json
import argparse
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime

# Windows encoding fix
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Config
BASE_URL = "http://localhost:8324"
API_PREFIX = "/api/v1/autocad/v2"
ACTION_DELAY = 1.0
DEFAULT_TEST_DWG = Path(__file__).parent / "test.dwg"

# Session (no proxy)
SESSION = requests.Session()
SESSION.trust_env = False

# Output directory for current run
OUTPUT_ROOT = Path(__file__).parent / "output"
CURRENT_RUN_DIR: Optional[Path] = None
STEP_COUNTER = 0


# ==================== Helpers ====================

def init_output_dir() -> Path:
    """Initialize output directory for this test run"""
    global CURRENT_RUN_DIR, STEP_COUNTER
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    CURRENT_RUN_DIR = OUTPUT_ROOT / timestamp
    CURRENT_RUN_DIR.mkdir(parents=True, exist_ok=True)
    STEP_COUNTER = 0
    print(f"  Output: {CURRENT_RUN_DIR}")
    return CURRENT_RUN_DIR


def get_step_dir(name: str) -> Path:
    """Get step output directory"""
    global STEP_COUNTER
    STEP_COUNTER += 1
    step_dir = CURRENT_RUN_DIR / f"{STEP_COUNTER:02d}_{name}"
    step_dir.mkdir(parents=True, exist_ok=True)
    return step_dir


def save_json(data: Any, filepath: Path, exclude_keys: List[str] = None):
    """Save JSON (optionally excluding keys like screenshots)"""
    def _filter(obj):
        if isinstance(obj, dict):
            return {k: _filter(v) for k, v in obj.items() if not exclude_keys or k not in exclude_keys}
        elif isinstance(obj, list):
            return [_filter(item) for item in obj]
        return obj
    
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(_filter(data) if exclude_keys else data, f, ensure_ascii=False, indent=2)


def save_screenshot(data: str, step_dir: Path, filename: str = "screenshot.png") -> str:
    """Save base64 screenshot"""
    filepath = step_dir / filename
    with open(filepath, "wb") as f:
        f.write(base64.b64decode(data))
    print(f"      Screenshot: {filepath.name}")
    return str(filepath)


def save_step_data(step_dir: Path, name: str, request: Dict, response: Dict, success: bool, notes: str = ""):
    """Save all step data to disk"""
    # Request
    save_json(request, step_dir / "request.json")
    
    # Response (without screenshot)
    save_json(response, step_dir / "response.json", exclude_keys=["screenshot"])
    
    # Extract and save screenshot from various response structures
    screenshot = None
    
    # Try different paths to find screenshot
    if isinstance(response, dict):
        # Direct response
        if "screenshot" in response:
            screenshot = response["screenshot"]
        
        # Nested in data
        data = response.get("data", {})
        if isinstance(data, dict):
            if "screenshot" in data:
                screenshot = data["screenshot"]
            
            # In snapshot
            snapshot = data.get("snapshot", {})
            if isinstance(snapshot, dict) and "screenshot" in snapshot:
                screenshot = snapshot["screenshot"]
    
    if screenshot:
        save_screenshot(screenshot, step_dir)
    
    # Extract and save content
    content = None
    if isinstance(response, dict):
        data = response.get("data", {})
        if isinstance(data, dict):
            content = data.get("content")
            if not content:
                snapshot = data.get("snapshot", {})
                if isinstance(snapshot, dict):
                    content = snapshot.get("content")
    
    if content:
        save_json(content, step_dir / "content.json")
    
    # Result summary
    with open(step_dir / "result.txt", "w", encoding="utf-8") as f:
        f.write(f"Step: {name}\nTime: {datetime.now()}\nSuccess: {success}\n\n{notes}")
    
    # Save code if present
    if "code" in request:
        with open(step_dir / "code.py", "w", encoding="utf-8") as f:
            f.write(request["code"])
    
    if "command" in request:
        with open(step_dir / "command.txt", "w", encoding="utf-8") as f:
            f.write(request["command"])
    
    if "data" in request and request["data"]:
        save_json(request["data"], step_dir / "drawing_data.json")


def api_get(endpoint: str, timeout: float = 30) -> Dict:
    """GET request"""
    try:
        resp = SESSION.get(f"{BASE_URL}{API_PREFIX}{endpoint}", timeout=timeout)
        return {"status": resp.status_code, "data": resp.json()}
    except Exception as e:
        return {"status": -1, "error": str(e)}


def api_post(endpoint: str, data: Dict = None, timeout: float = 60) -> Dict:
    """POST request"""
    try:
        resp = SESSION.post(f"{BASE_URL}{API_PREFIX}{endpoint}", json=data or {}, timeout=timeout)
        return {"status": resp.status_code, "data": resp.json()}
    except Exception as e:
        return {"status": -1, "error": str(e)}


def print_header(title: str):
    print(f"\n{'='*60}\n  {title}\n{'='*60}")


def print_result(success: bool, msg: str):
    print(f"      {'[OK]' if success else '[FAIL]'} {msg}")


def wait(seconds: float = None):
    time.sleep(seconds or ACTION_DELAY)


# ==================== API Operations ====================

def new_drawing(template: str = None) -> bool:
    """Create new drawing via API"""
    print(f"\n  Creating new drawing...")
    
    result = api_post("/new", {"template": template})
    
    if result["status"] == 200 and result["data"].get("success"):
        info = result["data"].get("document_info", {})
        print(f"  [OK] Created: {info.get('name')}")
        return True
    
    print(f"  [FAIL] {result.get('error') or result.get('data', {}).get('detail')}")
    return False


def open_drawing(path: Path = None, read_only: bool = False) -> bool:
    """Open drawing via API"""
    path = path or DEFAULT_TEST_DWG
    print(f"\n  Opening: {path}")
    
    if not path.exists():
        print(f"  [WARN] File not found: {path}, will create new drawing")
        return new_drawing()
    
    result = api_post("/open", {"file_path": str(path.absolute()), "read_only": read_only})
    
    if result["status"] == 200 and result["data"].get("success"):
        info = result["data"].get("document_info", {})
        print(f"  [OK] Opened: {info.get('name')}, Entities: {info.get('entity_count')}")
        return True
    
    print(f"  [FAIL] {result.get('error') or result.get('data', {}).get('detail')}")
    return False


def close_drawing(save: bool = False) -> bool:
    """Close drawing via API"""
    print(f"\n  Closing (save={save})...")
    result = api_post("/close", {"save": save})
    
    if result["status"] == 200 and result["data"].get("success"):
        print(f"  [OK] Closed: {result['data'].get('closed_document')}")
        return True
    
    print(f"  [FAIL] {result.get('error')}")
    return False


# ==================== Tests ====================

def test_status() -> bool:
    """Test GET /status"""
    print_header("Test: GET /status")
    step_dir = get_step_dir("status")
    request_data = {"endpoint": "/status", "method": "GET"}
    
    result = api_get("/status")
    
    if result["status"] == 200:
        data = result["data"]
        running = data.get("running", False)
        has_doc = data.get("has_document", False)
        doc_count = data.get("document_count", 0)
        documents = data.get("documents", [])
        
        print_result(running, f"AutoCAD running: {running}")
        print_result(has_doc, f"Has document: {has_doc}")
        
        notes = ""
        if has_doc:
            info = data.get("document_info", {})
            print(f"         Active: {info.get('name')}")
            print(f"         Entities: {info.get('entity_count')}")
            print(f"         Layers: {info.get('layer_count')}")
            
            # 显示所有打开的文档
            if doc_count > 0:
                print(f"         Open documents ({doc_count}):")
                for doc in documents:
                    active_mark = " [ACTIVE]" if doc.get("is_active") else ""
                    saved_mark = "" if doc.get("saved") else " *"
                    print(f"           [{doc.get('index')}] {doc.get('name')}{saved_mark}{active_mark}")
            
            notes = f"Document: {info.get('name')}, Entities: {info.get('entity_count')}, Total docs: {doc_count}"
        
        success = running
        save_step_data(step_dir, "status", request_data, result, success, notes)
        return success
    
    print_result(False, f"Request failed: {result}")
    save_step_data(step_dir, "status", request_data, result, False)
    return False


def test_activate_drawing(name: str = None, index: int = None) -> bool:
    """Test POST /activate"""
    target = name if name else f"index {index}"
    print_header(f"Test: POST /activate - Switch to {target}")
    
    step_dir = get_step_dir(f"activate_{name or index}")
    request_data = {"name": name, "index": index}
    
    result = api_post("/activate", request_data)
    
    if result["status"] == 200:
        data = result["data"]
        success = data.get("success", False)
        
        if success:
            print_result(True, f"Activated: {data.get('activated_document')}")
            info = data.get("document_info", {})
            print(f"         Entities: {info.get('entity_count')}")
        else:
            print_result(False, f"Failed: {data.get('error')}")
        
        save_step_data(step_dir, f"activate_{name or index}", request_data, result, success)
        return success
    
    print_result(False, f"Request failed: {result}")
    save_step_data(step_dir, f"activate_{name or index}", request_data, result, False)
    return False


def test_snapshot(only_visible: bool = False) -> bool:
    """Test GET /snapshot"""
    mode = "visible only" if only_visible else "all entities"
    print_header(f"Test: GET /snapshot ({mode})")
    
    step_dir = get_step_dir("snapshot" if not only_visible else "snapshot_visible")
    request_data = {
        "include_content": True,
        "include_screenshot": True,
        "only_visible": only_visible
    }
    
    result = api_get(f"/snapshot?include_content=true&include_screenshot=true&only_visible={str(only_visible).lower()}")
    
    if result["status"] == 200:
        data = result["data"]
        info = data.get("document_info", {})
        content = data.get("content", {})
        
        print_result(True, f"Document: {info.get('name')}")
        print(f"         Entities: {info.get('entity_count')}, Layers: {info.get('layer_count')}")
        
        notes = ""
        if content:
            summary = content.get("summary", {})
            total = summary.get("total_count", 0)
            by_type = summary.get("by_type", {})
            print(f"         Content: {total} entities")
            for etype, count in by_type.items():
                print(f"           - {etype}: {count}")
            notes = f"Entities: {total}, Types: {by_type}"
        
        save_step_data(step_dir, f"snapshot_{mode.replace(' ', '_')}", request_data, result, True, notes)
        return True
    
    print_result(False, f"Request failed: {result}")
    save_step_data(step_dir, "snapshot", request_data, result, False)
    return False


def test_step_draw_json(name: str, drawing_data: Dict, desc: str = "") -> bool:
    """Test POST /step with draw_from_json action"""
    print_header(f"Test: POST /step (draw_from_json) - {desc or name}")
    
    step_dir = get_step_dir(name)
    request_data = {
        "action": "draw_from_json",
        "data": drawing_data,
        "timeout": 30,
        "return_screenshot": True
    }
    
    result = api_post("/step", request_data)
    
    if result["status"] == 200:
        data = result["data"]
        execution = data.get("execution", {})
        success = execution.get("success", False)
        
        if success:
            print_result(True, "Drawing executed")
            created = execution.get("entities_created", 0)
            print(f"         Created: {created} entities")
        else:
            print_result(False, f"Drawing failed: {execution.get('error', 'Unknown')}")
        
        # Show snapshot info
        snapshot = data.get("snapshot", {})
        if snapshot:
            info = snapshot.get("document_info", {})
            print(f"         Total entities: {info.get('entity_count')}")
        
        save_step_data(step_dir, name, request_data, result, success, desc)
        return success
    
    print_result(False, f"Request failed: {result}")
    save_step_data(step_dir, name, request_data, result, False)
    return False


def test_step_send_command(name: str, command: str, desc: str = "") -> bool:
    """Test POST /step with execute_python_com action (SendCommand)"""
    print_header(f"Test: POST /step (SendCommand) - {desc or name}")
    
    # Wrap command in doc.SendCommand() via execute_python_com
    escaped_cmd = command.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    code = f'doc.SendCommand("{escaped_cmd}")\nprint("Executed: {escaped_cmd[:60]}")'
    
    step_dir = get_step_dir(name)
    request_data = {
        "action": "execute_python_com",
        "code": code,
        "timeout": 30,
        "return_screenshot": True
    }
    
    result = api_post("/step", request_data)
    
    if result["status"] == 200:
        data = result["data"]
        execution = data.get("execution", {})
        success = execution.get("success", False)
        
        if success:
            print_result(True, "Command executed")
            output = execution.get("output", "").strip()
            if output:
                print(f"         Output: {output[:100]}")
        else:
            print_result(False, f"Command failed: {execution.get('error', 'Unknown')}")
        
        save_step_data(step_dir, name, request_data, result, success, desc)
        return success
    
    print_result(False, f"Request failed: {result}")
    save_step_data(step_dir, name, request_data, result, False)
    return False


def test_step_python_com(name: str, code: str, desc: str = "") -> bool:
    """Test POST /step with execute_python_com action"""
    print_header(f"Test: POST /step (execute_python_com) - {desc or name}")
    
    step_dir = get_step_dir(name)
    request_data = {
        "action": "execute_python_com",
        "code": code,
        "timeout": 30,
        "return_screenshot": True
    }
    
    result = api_post("/step", request_data)
    
    if result["status"] == 200:
        data = result["data"]
        execution = data.get("execution", {})
        success = execution.get("success", False)
        
        if success:
            print_result(True, "Python code executed")
            output = execution.get("output", "").strip()
            if output:
                print(f"         Output: {output[:200]}")
            created = execution.get("entities_created", 0)
            if created:
                print(f"         Created: {created} entities")
        else:
            print_result(False, f"Code failed: {execution.get('error', 'Unknown')[:200]}")
        
        save_step_data(step_dir, name, request_data, result, success, desc)
        return success
    
    print_result(False, f"Request failed: {result}")
    save_step_data(step_dir, name, request_data, result, False)
    return False


def test_standard_parts_list() -> bool:
    """Test GET /standard_parts"""
    print_header("Test: GET /standard_parts")
    
    step_dir = get_step_dir("standard_parts_list")
    request_data = {"endpoint": "/standard_parts", "method": "GET"}
    
    result = api_get("/standard_parts")
    
    if result["status"] == 200:
        data = result["data"]
        parts = data.get("parts", [])
        
        print_result(True, f"Found {len(parts)} standard parts")
        for part in parts:
            presets = part.get("presets", [])
            print(f"         - {part.get('type')}: {part.get('description')} ({len(presets)} presets)")
        
        save_step_data(step_dir, "standard_parts_list", request_data, result, True)
        return True
    
    print_result(False, f"Request failed: {result}")
    save_step_data(step_dir, "standard_parts_list", request_data, result, False)
    return False


def test_draw_standard_part(part_type: str, preset: str = None, params: Dict = None) -> bool:
    """Test POST /standard_parts/{type}/draw"""
    desc = f"{part_type} ({preset or 'custom'})"
    print_header(f"Test: POST /standard_parts/{part_type}/draw - {desc}")
    
    step_dir = get_step_dir(f"draw_{part_type}_{preset or 'custom'}")
    request_data = {
        "preset": preset,
        "parameters": params,
        "position": [0, 0]
    }
    
    result = api_post(f"/standard_parts/{part_type}/draw", request_data)
    
    if result["status"] == 200:
        data = result["data"]
        success = data.get("success", False)
        
        if success:
            print_result(True, f"Drew {part_type}")
            created = data.get("entities_created", 0)
            print(f"         Created: {created} entities")
            params_used = data.get("parameters_used", {})
            print(f"         Parameters: {json.dumps(params_used, ensure_ascii=False)[:100]}")
        else:
            print_result(False, f"Draw failed: {data.get('error', 'Unknown')}")
        
        save_step_data(step_dir, f"draw_{part_type}", request_data, result, success, desc)
        return success
    
    print_result(False, f"Request failed: {result}")
    save_step_data(step_dir, f"draw_{part_type}", request_data, result, False)
    return False


# ==================== Drawing Data Templates ====================

DRAWING_SIMPLE_LINES = {
    "layer_colors": {
        "测试图层": 1  # 红色
    },
    "elements": {
        "lines": [
            {"start": [0, 0, 0], "end": [100, 0, 0], "layer": "测试图层", "color": 256},
            {"start": [100, 0, 0], "end": [100, 100, 0], "layer": "测试图层", "color": 256},
            {"start": [100, 100, 0], "end": [0, 100, 0], "layer": "测试图层", "color": 256},
            {"start": [0, 100, 0], "end": [0, 0, 0], "layer": "测试图层", "color": 256}
        ]
    }
}

DRAWING_MIXED_SHAPES = {
    "layer_colors": {
        "轮廓": 7,
        "圆": 3,
        "文字": 5
    },
    "elements": {
        "lines": [
            {"start": [200, 0, 0], "end": [300, 0, 0], "layer": "轮廓"},
            {"start": [300, 0, 0], "end": [300, 100, 0], "layer": "轮廓"},
            {"start": [300, 100, 0], "end": [200, 100, 0], "layer": "轮廓"},
            {"start": [200, 100, 0], "end": [200, 0, 0], "layer": "轮廓"}
        ],
        "circles": [
            {"center": [250, 50, 0], "radius": 30, "layer": "圆"}
        ],
        "texts": [
            {"text": "AI Test", "position": [220, 120, 0], "height": 10, "layer": "文字"}
        ]
    }
}

DRAWING_WITH_DIMENSIONS = {
    "layer_colors": {
        "轮廓": 7,
        "标注": 2
    },
    "elements": {
        "lines": [
            {"start": [400, 0, 0], "end": [500, 0, 0], "layer": "轮廓"},
            {"start": [500, 0, 0], "end": [500, 80, 0], "layer": "轮廓"},
            {"start": [500, 80, 0], "end": [400, 80, 0], "layer": "轮廓"},
            {"start": [400, 80, 0], "end": [400, 0, 0], "layer": "轮廓"}
        ],
        "dimensions": [
            {
                "type": "AcDbAlignedDimension",
                "ext_line1_point": [400, 0, 0],
                "ext_line2_point": [500, 0, 0],
                "text_position": [450, -15, 0],
                "measurement": 100,
                "layer": "标注"
            },
            {
                "type": "AcDbAlignedDimension",
                "ext_line1_point": [500, 0, 0],
                "ext_line2_point": [500, 80, 0],
                "text_position": [515, 40, 0],
                "measurement": 80,
                "layer": "标注"
            }
        ]
    }
}


# ==================== Code Templates ====================

CODE_PYTHON_DRAW_LINE = '''
# 绘制一条对角线
line = ms.AddLine(vtPoint(0, 200, 0), vtPoint(100, 300, 0))
line.Color = 1  # 红色
print(f"Drew line: {line.Handle}")
'''

CODE_PYTHON_DRAW_CIRCLE = '''
# 绘制一个圆
circle = ms.AddCircle(vtPoint(150, 250, 0), 40)
circle.Color = 3  # 绿色
print(f"Drew circle: {circle.Handle}")
'''

CODE_PYTHON_DRAW_TEXT = '''
# 添加文字
text = ms.AddText("Python COM Test", vtPoint(0, 350, 0), 15)
text.Color = 5  # 蓝色
print(f"Drew text: {text.Handle}")
'''

CODE_PYTHON_QUERY_ENTITIES = '''
# 查询所有实体
count = ms.Count
print(f"Total entities: {count}")

# 统计类型
types = {}
for i in range(count):
    entity = ms.Item(i)
    etype = entity.ObjectName
    types[etype] = types.get(etype, 0) + 1

for etype, cnt in types.items():
    print(f"  {etype}: {cnt}")
'''

CODE_PYTHON_MODIFY_ENTITY = '''
# 修改最后一个实体的颜色
if ms.Count > 0:
    last = ms.Item(ms.Count - 1)
    old_color = last.Color
    last.Color = 6  # 洋红色
    print(f"Changed entity {last.Handle} color: {old_color} -> 6")
else:
    print("No entities to modify")
'''


# ==================== AutoLISP Commands ====================

CMD_ZOOM_EXTENTS = "ZOOM E\n"
CMD_ZOOM_ALL = "ZOOM A\n"
CMD_REGEN = "REGEN\n"
CMD_REDRAW = "REDRAW\n"
CMD_LAYER_LIST = "-LAYER\n\n"


# ==================== Run Modes ====================

def run_demo(auto_open: bool = True, dwg_path: Path = None) -> List[Tuple[str, bool]]:
    """Run full demo"""
    print_header("AutoCAD V2 API Demo")
    init_output_dir()
    
    results = []
    
    # Ensure AutoCAD has a document
    if auto_open:
        if dwg_path and dwg_path.exists():
            if not open_drawing(dwg_path):
                print("\n  [WARN] Could not open test file, creating new...")
                new_drawing()
        else:
            new_drawing()
    
    wait(2)
    
    # Status
    if not test_status():
        print("\n  [FAIL] AutoCAD not available")
        return [("status", False)]
    results.append(("status", True))
    wait()
    
    # Snapshot
    results.append(("snapshot", test_snapshot(only_visible=False)))
    wait()
    
    # Draw JSON - Simple lines
    results.append(("draw_json_lines", test_step_draw_json(
        "draw_lines", DRAWING_SIMPLE_LINES, "Draw simple rectangle"
    )))
    wait()
    
    # AutoLISP - Zoom
    results.append(("autolisp_zoom", test_step_send_command(
        "zoom_extents", CMD_ZOOM_EXTENTS, "Zoom to extents"
    )))
    wait()
    
    # Draw JSON - Mixed shapes
    results.append(("draw_json_mixed", test_step_draw_json(
        "draw_mixed", DRAWING_MIXED_SHAPES, "Draw mixed shapes"
    )))
    wait()
    
    # Python COM - Draw line
    results.append(("python_draw_line", test_step_python_com(
        "python_line", CODE_PYTHON_DRAW_LINE, "Draw line via Python"
    )))
    wait()
    
    # Python COM - Draw circle
    results.append(("python_draw_circle", test_step_python_com(
        "python_circle", CODE_PYTHON_DRAW_CIRCLE, "Draw circle via Python"
    )))
    wait()
    
    # Python COM - Query entities
    results.append(("python_query", test_step_python_com(
        "python_query", CODE_PYTHON_QUERY_ENTITIES, "Query entities"
    )))
    wait()
    
    # AutoLISP - Zoom again
    results.append(("autolisp_zoom2", test_step_send_command(
        "zoom_all", CMD_ZOOM_ALL, "Zoom all"
    )))
    wait()
    
    # Final snapshot
    results.append(("snapshot_final", test_snapshot(only_visible=False)))
    
    return results


def run_all_actions() -> List[Tuple[str, bool]]:
    """Test all action types"""
    print_header("Test All Action Types")
    init_output_dir()
    
    results = []
    
    # Ensure document
    new_drawing()
    wait(2)
    
    # Status
    results.append(("status", test_status()))
    wait()
    
    # 1. draw_from_json
    print_header("Action Type 1: draw_from_json")
    results.append(("draw_from_json", test_step_draw_json(
        "action_draw_json", DRAWING_WITH_DIMENSIONS, "Draw with dimensions"
    )))
    wait()
    
    # 2. execute_python_com
    print_header("Action Type 2: execute_python_com")
    results.append(("execute_python_com", test_step_python_com(
        "action_python", CODE_PYTHON_DRAW_TEXT, "Draw text via Python"
    )))
    wait()
    
    # 3. execute_python_com (SendCommand)
    print_header("Action Type 2b: execute_python_com (SendCommand)")
    results.append(("send_command", test_step_send_command(
        "action_send_command", CMD_ZOOM_EXTENTS, "Zoom extents via SendCommand"
    )))
    wait()
    
    # Final snapshot
    results.append(("final_snapshot", test_snapshot()))
    
    return results


def run_standard_parts_test() -> List[Tuple[str, bool]]:
    """Test standard parts"""
    print_header("Standard Parts Test")
    init_output_dir()
    
    results = []
    
    # Ensure document
    new_drawing()
    wait(2)
    
    # List parts
    results.append(("list_parts", test_standard_parts_list()))
    wait()
    
    # Draw flange DN100
    results.append(("flange_dn100", test_draw_standard_part("flange", preset="DN100")))
    wait()
    
    # Zoom
    test_step_send_command("zoom", CMD_ZOOM_EXTENTS, "Zoom")
    wait()
    
    # Draw bolt M12
    results.append(("bolt_m12", test_draw_standard_part("bolt", preset="M12")))
    wait()
    
    # Draw U-channel U50
    results.append(("u_channel_u50", test_draw_standard_part("u_channel", preset="U50")))
    wait()
    
    # Final zoom and snapshot
    test_step_send_command("zoom_final", CMD_ZOOM_ALL, "Zoom all")
    wait()
    
    results.append(("final_snapshot", test_snapshot()))
    
    return results


def run_multi_document_test() -> List[Tuple[str, bool]]:
    """Test multi-document management and switching"""
    print_header("Multi-Document Test")
    init_output_dir()
    
    results = []
    
    # Create first document
    print("\n  Creating Document 1...")
    new_drawing()
    wait(2)
    
    # Draw something in doc 1
    results.append(("doc1_draw", test_step_draw_json(
        "doc1_draw", DRAWING_SIMPLE_LINES, "Draw in Document 1"
    )))
    wait()
    
    # Create second document
    print("\n  Creating Document 2...")
    new_drawing()
    wait(2)
    
    # Draw something different in doc 2
    results.append(("doc2_draw", test_step_draw_json(
        "doc2_draw", DRAWING_MIXED_SHAPES, "Draw in Document 2"
    )))
    wait()
    
    # Create third document
    print("\n  Creating Document 3...")
    new_drawing()
    wait(2)
    
    # Draw in doc 3
    results.append(("doc3_draw", test_step_python_com(
        "doc3_draw", CODE_PYTHON_DRAW_CIRCLE, "Draw in Document 3"
    )))
    wait()
    
    # Check status - should show 3 documents
    results.append(("status_3docs", test_status()))
    wait()
    
    # Switch to first document by index
    results.append(("switch_to_doc0", test_activate_drawing(index=0)))
    wait()
    
    # Take snapshot of doc 1
    results.append(("doc1_snapshot", test_snapshot()))
    wait()
    
    # Switch to second document by index
    results.append(("switch_to_doc1", test_activate_drawing(index=1)))
    wait()
    
    # Take snapshot of doc 2
    results.append(("doc2_snapshot", test_snapshot()))
    wait()
    
    # Final status
    results.append(("final_status", test_status()))
    
    return results


def run_template_test() -> List[Tuple[str, bool]]:
    """Test drawing from _templates JSON files"""
    print_header("Template Drawing Test")
    init_output_dir()
    
    results = []
    
    # Template directory
    template_dir = Path(__file__).resolve().parents[2] / "_templates"
    
    # Ensure document
    new_drawing()
    wait(2)
    
    # Status
    results.append(("status", test_status()))
    wait()
    
    # Test 1: default/drawing.json
    default_json = template_dir / "default" / "drawing.json"
    if default_json.exists():
        with open(default_json, "r", encoding="utf-8") as f:
            data = json.load(f)
        results.append(("default_drawing", test_step_draw_json(
            "default_drawing", data, "Draw default template"
        )))
        wait()
    
    # Zoom to see
    results.append(("zoom1", test_step_send_command("zoom1", CMD_ZOOM_EXTENTS, "Zoom extents")))
    wait()
    
    # Snapshot
    results.append(("snapshot1", test_snapshot()))
    wait()
    
    # Test 2: u_channel_main_structure_specs/r_100_1-10.json (in new drawing)
    new_drawing()
    wait(2)
    
    u_channel_json = template_dir / "u_channel_main_structure_specs" / "r_100_1-10.json"
    if u_channel_json.exists():
        with open(u_channel_json, "r", encoding="utf-8") as f:
            data = json.load(f)
        results.append(("u_channel_r100", test_step_draw_json(
            "u_channel_r100", data, "Draw U-channel R100 1:10"
        )))
        wait()
    
    # Zoom
    results.append(("zoom2", test_step_send_command("zoom2", CMD_ZOOM_EXTENTS, "Zoom extents")))
    wait()
    
    # Snapshot
    results.append(("snapshot2", test_snapshot()))
    wait()
    
    # Test 3: cut_and_fill_canal (all 6 parts in new drawing)
    new_drawing()
    wait(2)
    
    canal_dir = template_dir / "cut_and_fill_canal"
    canal_files = [
        "1_title_and_scale.json",
        "2_ground_line.json",
        "3_main_structure.json",
        "4_slopes.json",
        "5_elevations.json",
        "6_dimensions.json"
    ]
    
    for fname in canal_files:
        fpath = canal_dir / fname
        if fpath.exists():
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
            short_name = fname.replace(".json", "")
            results.append((f"canal_{short_name}", test_step_draw_json(
                f"canal_{short_name}", data, f"Draw {short_name}"
            )))
            wait(0.5)
    
    # Final zoom and snapshot
    results.append(("zoom3", test_step_send_command("zoom3", CMD_ZOOM_EXTENTS, "Zoom extents")))
    wait()
    
    results.append(("final_snapshot", test_snapshot()))
    
    return results


def save_summary(results: List[Tuple[str, bool]]):
    """Save test summary"""
    if not CURRENT_RUN_DIR:
        return
    
    passed = sum(1 for _, r in results if r)
    total = len(results)
    
    summary = {
        "time": datetime.now().isoformat(),
        "server": BASE_URL,
        "passed": passed,
        "total": total,
        "results": [{"name": n, "success": s} for n, s in results]
    }
    save_json(summary, CURRENT_RUN_DIR / "summary.json")
    
    with open(CURRENT_RUN_DIR / "summary.txt", "w", encoding="utf-8") as f:
        f.write(f"AutoCAD V2 API Test Summary\n")
        f.write(f"Time: {datetime.now()}\n")
        f.write(f"Results: {passed}/{total} passed\n\n")
        for name, success in results:
            f.write(f"  [{'PASS' if success else 'FAIL'}] {name}\n")
    
    print(f"\n  Summary saved: {CURRENT_RUN_DIR / 'summary.txt'}")


def main():
    global BASE_URL, ACTION_DELAY
    
    parser = argparse.ArgumentParser(description="AutoCAD V2 API Test")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", default="8324")
    parser.add_argument("--delay", type=float, default=1.0)
    parser.add_argument("--no-auto-open", action="store_true")
    parser.add_argument("--dwg", type=str, default=None)
    parser.add_argument("mode", nargs="?", default="demo",
                       choices=["demo", "basic", "snapshot", "draw_json",
                               "python_com", "standard_part", "all_actions", "multi_doc", "template"])
    args = parser.parse_args()
    
    BASE_URL = f"http://{args.host}:{args.port}"
    ACTION_DELAY = args.delay
    
    print("=" * 60)
    print("  AutoCAD V2 API Test")
    print("=" * 60)
    print(f"  Server: {BASE_URL}")
    print(f"  Mode: {args.mode}")
    
    # Check service
    try:
        resp = SESSION.get(f"{BASE_URL}/health", timeout=5)
        if resp.status_code != 200:
            print("  [FAIL] Service not running")
            return 1
        print("  [OK] Service running")
    except Exception as e:
        print(f"  [FAIL] Cannot connect: {e}")
        return 1
    
    dwg_path = Path(args.dwg) if args.dwg else None
    auto_open = not args.no_auto_open
    
    # Run tests
    if args.mode == "demo":
        results = run_demo(auto_open, dwg_path)
    elif args.mode == "basic":
        init_output_dir()
        if auto_open:
            new_drawing()
            wait(2)
        results = [("status", test_status())]
    elif args.mode == "snapshot":
        init_output_dir()
        if auto_open:
            new_drawing()
            wait(2)
        results = [("snapshot", test_snapshot())]
    elif args.mode == "draw_json":
        init_output_dir()
        if auto_open:
            new_drawing()
            wait(2)
        results = [
            ("status", test_status()),
            ("draw_json", test_step_draw_json("draw_test", DRAWING_MIXED_SHAPES, "Draw mixed shapes"))
        ]
    elif args.mode == "python_com":
        init_output_dir()
        if auto_open:
            new_drawing()
            wait(2)
        results = [
            ("status", test_status()),
            ("python_com", test_step_python_com("python_test", CODE_PYTHON_DRAW_LINE, "Draw line"))
        ]
    elif args.mode == "standard_part":
        results = run_standard_parts_test()
    elif args.mode == "all_actions":
        results = run_all_actions()
    elif args.mode == "multi_doc":
        results = run_multi_document_test()
    elif args.mode == "template":
        results = run_template_test()
    else:
        print(f"Unknown mode: {args.mode}")
        return 1
    
    # Summary
    print_header("Results")
    passed = sum(1 for _, r in results if r)
    total = len(results)
    print(f"  Passed: {passed}/{total}\n")
    
    for name, success in results:
        print(f"    [{'OK' if success else 'FAIL'}] {name}")
    
    save_summary(results)
    
    if CURRENT_RUN_DIR:
        print(f"\n  Output: {CURRENT_RUN_DIR}")
    
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
