"""
Skill Prompts - 可复用的 Skill 相关 Prompt 片段

所有 handler（Excel / Word / PPT）共享的 skill action 描述、
决策步骤、用户 prompt 片段等。

通过 {reference_name} 参数适配不同应用：
- Excel: "PowerShell Excel COM API reference"
- Word:  "Word COM API reference"
- PPT:   "PowerPoint COM API reference"

用法：
    from useit_studio.ai_run.skills.skill_prompts import (
        skill_system_actions,
        skill_decision_steps,
        skill_user_fragments,
    )

    # 在各 app 的 prompts.py 中组装
    actions = skill_system_actions("PowerShell Excel COM API reference")
    steps = skill_decision_steps("PowerShell Excel COM API reference")
    fragments = skill_user_fragments("Excel COM API reference")
"""


# ============================================================================
# System Prompt 片段
# ============================================================================


def skill_system_actions(reference_name: str = "API reference") -> str:
    """
    系统 prompt 的 "Available Actions" 中 skill 相关部分。

    包含 read_default_reference / read_file / execute_script 三个 action 的描述。
    各 app 的 prompts.py 在此之后追加自己的 execute_code / stop 等描述。

    Args:
        reference_name: 默认参考文档名称

    Returns:
        格式化的 action 描述字符串
    """
    return f"""### 1. read_default_reference
Load the default {reference_name} (lazy loaded to save tokens).

**When to use**:
- First time you need to write code and haven't seen the reference yet
- When you need to refresh your knowledge of the {reference_name}

**Example**:
```json
{{
  "Action": "read_default_reference",
  "Title": "Load reference"
}}
```

### 2. read_file
Read a file from the loaded skills (e.g., scripts, documentation, examples).

**When to use**:
- When a skill mentions reference files (e.g., "see scripts/chart_examples.py")
- When you need detailed code templates before implementing

**Example**:
```json
{{
  "Action": "read_file",
  "Title": "Read chart examples",
  "FilePath": "scripts/chart_examples.py"
}}
```

**Note**: FilePath is relative to the skill's base directory shown in the skills section.

### 3. execute_script
Execute a pre-written script from skills with parameters (Mode 2: Script-based).

**When to use**:
- When a skill provides ready-to-use scripts (e.g., create_column_chart.ps1)
- For complex, tested operations that benefit from centralized script management
- When you want to use proven, version-controlled code

**Example**:
```json
{{
  "Action": "execute_script",
  "Title": "Create column chart",
  "ScriptPath": "scripts/create_column_chart.ps1",
  "Parameters": {{
    "DataRange": "A1:B10",
    "ChartTitle": "Monthly Sales",
    "ChartLeft": 200,
    "ChartTop": 50
  }}
}}
```

**Note**: The backend will fetch the script content from skills and send it to the frontend with your parameters."""


def skill_decision_steps(reference_name: str = "API reference") -> str:
    """
    Decision Strategy 中 skill 相关的步骤。

    各 app 可以在此基础上追加 app 特有步骤。

    Args:
        reference_name: 默认参考文档名称

    Returns:
        格式化的决策步骤字符串
    """
    return f"""1. **First action**: If you haven't seen the {reference_name} yet and need to write code, use `read_default_reference`
2. **Need examples**: If a skill mentions helpful scripts/docs, use `read_file` to read them
3. **Execute**: Choose between `execute_code` (simple/custom) or `execute_script` (complex/reusable)
4. **Complete**: When the state matches the goal, use `stop` with MilestoneCompleted=true"""


# ============================================================================
# User Prompt 片段
# ============================================================================


def skill_user_fragments(reference_name: str = "API reference") -> dict:
    """
    User prompt 中 skill 相关片段，返回 dict 按需取用。

    Keys:
        thinking_checks - <thinking> 块中的 skill 检查步骤
        json_fields     - JSON 响应格式中 skill 相关字段
        action_types    - Action 类型说明列表
        critical_rules  - skill action 的关键规则

    Args:
        reference_name: 默认参考文档名称

    Returns:
        包含 4 个 prompt 片段的字典
    """
    return {
        # ---- <thinking> 块中的检查步骤 ----
        "thinking_checks": f"""3. **Check if you need more information**:
   - Need {reference_name}? → read_default_reference
   - Need skill examples/scripts? → read_file""",

        # ---- JSON 响应格式中的 skill 字段 ----
        "json_fields": """
  // If Action is "read_file":
  "FilePath": "relative/path/from/skill/base_dir",

  // If Action is "execute_script":
  "ScriptPath": "scripts/script_name.ps1",
  "Parameters": {{"param1": "value1", "param2": "value2"}},""",

        # ---- Action 类型说明 ----
        "action_types": f"""**read_default_reference** - Load the default {reference_name} (lazy loaded)
**read_file** - Read a file from loaded skills (scripts, docs, examples)
**execute_script** - Execute a pre-written script from skills with parameters (for complex/reusable operations)""",

        # ---- 关键规则（action-specific requirements）----
        "critical_rules": """- `read_default_reference`: No additional fields needed
- `read_file`: Must provide FilePath (relative to skill base_dir)
- `execute_script`: Must provide ScriptPath and Parameters (as object)""",
    }
