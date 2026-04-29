"""
Diff tools for applying Search & Replace blocks to JSON template files.

Rationale:
AI models struggle with counting lines and maintaining precise context line counts required by Unified Diff.
Search & Replace blocks rely on exact content matching, which is much more robust for LLMs.

Format:
path/to/file.json
<<<<<<< SEARCH
<original content to find>
=======
<new content to replace with>
>>>>>>> REPLACE

Usage:
from tools.diff_tools import apply_search_replace_blocks
patched_files = apply_search_replace_blocks(response_text, project_root)
"""

from __future__ import annotations

from typing import List, Optional
import os
import re


def _find_file_by_basename(project_root: str, basename: str) -> Optional[str]:
    """
    Helper: Find file by basename in project_root if exact path fails.
    """
    matches: List[str] = []
    for root, _dirs, files in os.walk(project_root):
        if basename in files:
            matches.append(os.path.join(root, basename))
    if len(matches) == 1:
        return matches[0]
    return None


def apply_search_replace_blocks(response_text: str, project_root: Optional[str] = None) -> List[str]:
    """
    Parse and apply Search & Replace blocks from the LLM response.
    
    Block Format:
    
    relative/path/to/file.ext
    <<<<<<< SEARCH
    original lines
    to match
    =======
    new lines
    to replace
    >>>>>>> REPLACE
    
    Args:
        response_text: The full text response from LLM containing one or more blocks.
        project_root: Root of the project.
        
    Returns:
        List of successfully modified file paths.
    """
    if project_root is None:
        project_root = os.path.dirname(os.path.dirname(__file__))
        
    patched_files = []
    
    # Regex to find blocks
    # Group 1: Filename (optional, might be on previous line)
    # Group 2: Search content
    # Group 3: Replace content
    # We use a fairly loose regex to capture the blocks
    
    # Split by the start marker to handle multiple blocks
    # Note: exact syntax is:
    # File path (optional, but recommended)
    # <<<<<<< SEARCH
    # ...
    # =======
    # ...
    # >>>>>>> REPLACE
    
    pattern = re.compile(
        r'(?:^|\n)(?P<path>[\w\./\\-]+)?\s*\n?<<<<<<< SEARCH\n(?P<search>[\s\S]*?)\n=======\n(?P<replace>[\s\S]*?)\n>>>>>>> REPLACE',
        re.MULTILINE
    )
    
    matches = list(pattern.finditer(response_text))
    
    if not matches:
        # Try a fallback pattern where filename might be inside a code block or formatted differently
        # But usually, if the prompt is followed, the above works.
        # Let's just log if no matches found might be useful debug info
        print("[Diff Tools] No SEARCH/REPLACE blocks found in response.")
        return []

    for match in matches:
        raw_path = match.group('path')
        search_block = match.group('search')
        replace_block = match.group('replace')
        
        # Determine file path
        # If path is not explicitly captured immediately before SEARCH, 
        # we might need to look at the context or rely on the prompt enforcing it.
        # For now, assume prompt enforces "Path:\n<<<<<<< SEARCH"
        
        target_path = None
        
        if raw_path and raw_path.strip():
            target_path = raw_path.strip()
        else:
            # Fallback: Look backwards from the match start to find a likely filename
            # This is risky but helps if there's extra whitespace
            pass

        if not target_path:
            print(f"[Diff Tools] Skipping block: No file path specified.")
            continue
            
        # Resolve absolute path
        abs_path = os.path.join(project_root, target_path)
        
        if not os.path.isfile(abs_path):
            # Try fuzzy find by basename
            if os.sep not in target_path and "/" not in target_path:
                found = _find_file_by_basename(project_root, target_path)
                if found:
                    abs_path = found
                    target_path = os.path.relpath(found, project_root)
                else:
                    print(f"[Diff Tools] File not found: {target_path}")
                    continue
            else:
                print(f"[Diff Tools] File not found: {target_path}")
                continue
        
        # Apply patch
        try:
            with open(abs_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Exact string replacement
            # We need to be careful about newlines. 
            # The regex groups usually exclude the trailing newline of the separator,
            # but the blocks themselves might be whitespace sensitive.
            
            if search_block in content:
                new_content = content.replace(search_block, replace_block, 1)
                
                with open(abs_path, 'w', encoding='utf-8') as f:
                    f.write(new_content)
                
                if target_path not in patched_files:
                    patched_files.append(target_path)
                # print(f"[Diff Tools] Successfully patched {target_path}")
                
            else:
                # Retry with relaxed whitespace (strip ends)
                if search_block.strip() in content:
                    new_content = content.replace(search_block.strip(), replace_block.strip(), 1)
                    # This is risky if search_block matches multiple places, but standard for this approach
                    with open(abs_path, 'w', encoding='utf-8') as f:
                        f.write(new_content)
                    if target_path not in patched_files:
                        patched_files.append(target_path)
                else:
                    # Try line-by-line matching (ignoring indentation differences? No, JSON indentation matters)
                    # Let's just report failure for now.
                    print(f"[Diff Tools] SEARCH block not found in {target_path}. \nSearch block:\n---\n{search_block}\n---")
                    
        except Exception as e:
            print(f"[Diff Tools] Error patching {target_path}: {e}")
            continue
            
    return patched_files

# Backwards compatibility alias if needed, though we should update caller
apply_unified_diff = apply_search_replace_blocks
