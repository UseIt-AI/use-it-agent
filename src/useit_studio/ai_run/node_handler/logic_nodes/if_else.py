import os
import json
from typing import Dict, List, Optional, Tuple
from useit_studio.ai_run.node_handler.logic_nodes.base import BaseNodeHandler
from useit_studio.ai_run.node_handler.functional_nodes.computer_use.gui.prompt_templates.renderer import render_template
from useit_studio.ai_run.llm_utils import MessageBuilder

class IfElseNodeHandler(BaseNodeHandler):
    """Handler for if-else node type"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
    
    async def handle(
        self,
        planner,
        current_node: Dict,
        current_state: Dict,
        screenshot_path: Optional[str] = None,
        query: Optional[str] = None,
        **kwargs
    ) -> Dict:
        """Handle if-else node processing"""
        node_id = self._get_node_id(current_node)
        node_title = self._get_node_title(current_node)
        
        self.planner=planner
        self._log_info(f"Executing If-Else Node with LLM: {node_id} - {node_title} (Overall Query: {query})")
        
        node_data = current_node.get('data', {})
        if_else_condition = node_data.get('condition')
        
        branch_options, valid_branch_ids, error_state = self._prepare_if_else_branch_options(node_id)

        return await self._process_llm_decision(
            current_node,
            current_state,
            screenshot_path,
            if_else_condition,
            branch_options,
            valid_branch_ids,
            query,
        )

    def _prepare_if_else_branch_options(self, node_id: str) -> Tuple[List[Dict[str, str]], List[str], Optional[str]]:
        """Prepares branch options and identifies valid branch IDs for an if-else node."""
        
        branch_options = []
        valid_branch_ids = []
        
        outgoing_edges = self.graph_manager.adjacency_list.get(node_id, [])
        
        for edge in outgoing_edges:
            branch_id = edge.get('sourceHandle')
            target_node_id = edge.get('target')

            valid_branch_ids.append(branch_id)

            # Target node details for description
            target_node_dict = self.graph_manager.get_milestone_by_id(target_node_id)
            target_description = "No description available for this branch's destination."
            if target_node_dict:
                target_description = target_node_dict.get('description') or target_node_dict.get('title', target_description)
            
            branch_options.append({
                "id": branch_id,
                "target_description": target_description
            })
        
        if not branch_options:
            self._log_error(f"No valid branch options could be constructed for if-else node {node_id}.")
            return [], [], "error_no_valid_branches"
        
        return branch_options, valid_branch_ids, None 
    
    async def _process_llm_decision(
        self,
        current_node: Dict,
        current_state: Dict,
        screenshot_path: str,
        if_else_condition: str,
        branch_options: List[Dict],
        valid_branch_ids: List[str],
        query: Optional[str],
    ) -> Dict:
        """Process the LLM decision for if-else node"""
        node_id = self._get_node_id(current_node)
        
        branch_options_text_list = [
            f"- Branch ID: '{opt['id']}', Leads to next node: \\\"{opt['target_description']}\\\"" for opt in branch_options
        ]
        branch_options_text = "\\n".join(branch_options_text_list)

        full_user_prompt_for_if_else = render_template(
            "node_if_else/user_prompt.txt",
            overall_task_context=query,
            if_else_condition=if_else_condition,
            branch_options_text=branch_options_text,
        )

        # 构建 interleave list 消息
        message_content = [full_user_prompt_for_if_else]
        if screenshot_path:
            message_content.append(screenshot_path)

        # 获取 system_prompt
        system_prompt = render_template("node_if_else/system_prompt.txt")

        # 使用 MessageBuilder 构建统一消息
        messages = MessageBuilder.from_interleave_list(
            message_content,
            system_prompt=system_prompt
        )

        chosen_branch_id = None
        observation_text = ""
        reasoning_text = ""
        action_text = ""
        token_usage = None

        try:
            # 获取 planner 的 llm_client
            llm_client = self.planner.llm_client

            # 非流式调用
            response = await llm_client.call(messages, system_prompt)

            llm_response = response.content
            token_usage = response.token_usage
            
            if llm_response is None:
                raise ValueError("LLM call returned None")
            
            # Parse JSON response
            response_data = json.loads(llm_response.strip())
            self.logger.log_json(response_data, f"if_else_decision_{node_id}_response.json", self.logging_dir)
            
            observation_text = response_data.get('Observation', 'No observation provided.')
            reasoning_text = response_data.get('Reasoning', 'No reasoning provided.')
            llm_chosen_id = response_data.get('Action', '').strip()
            
            if llm_chosen_id in valid_branch_ids:
                chosen_branch_id = llm_chosen_id
                action_text = f"Proceeding with branch '{chosen_branch_id}'."
                self._log_info(f"LLM chose branch '{chosen_branch_id}'. Valid: {valid_branch_ids}")
            else:
                self._log_warning(f"LLM for if-else node {node_id} returned invalid branch_id: '{llm_chosen_id}'. Valid: {valid_branch_ids}. Defaulting.")
                raise ValueError(f"Invalid branch ID: {llm_chosen_id}")
        
        except Exception as e:
            # Handle all errors with a single fallback
            error_msg = f"Error processing if-else node {node_id}: {e}"
            self._log_warning(error_msg)
            chosen_branch_id = valid_branch_ids[0] if valid_branch_ids else "false"
            observation_text = observation_text or "Could not process LLM response properly."
            reasoning_text = f"Error occurred during processing. Defaulted to branch '{chosen_branch_id}'. Error: {str(e)}."
            action_text = f"Proceeding with default branch '{chosen_branch_id}'."
        
        updated_state = current_state.copy()
        updated_state[f"{node_id}_evaluated_branch"] = chosen_branch_id
        
        node_completion_summary = f"Go with branch '{chosen_branch_id}' with the following reasoning: {reasoning_text}"
        
        return self.build_success_result({
            "Observation": observation_text,
            "Reasoning": reasoning_text,
            "Action": action_text,
            "is_node_completed": True,
            "current_state": updated_state,  # This state now contains the chosen branch
            "chosen_branch_id": chosen_branch_id,
            "node_completion_summary": node_completion_summary,
            "token_usage": {
                "total_tokens": token_usage.total_tokens if token_usage else 0,
                "input_tokens": token_usage.input_tokens if token_usage else 0,
                "output_tokens": token_usage.output_tokens if token_usage else 0,
                "model": self.planner.model
            }
        })
