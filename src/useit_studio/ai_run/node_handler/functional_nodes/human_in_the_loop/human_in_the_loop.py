import json
from typing import Dict, Optional

from useit_studio.ai_run.node_handler.logic_nodes.base import BaseNodeHandler
# from useit_studio.ai_run.node_handler.functional_nodes.computer_use.gui.planner.tool_planner import FunctionalToolPlanner
# from useit_studio.ai_run.node_handler.functional_nodes.computer_use.gui.prompt_templates.renderer import render_template


class HumanInTheLoopNodeHandler(BaseNodeHandler):
    """Handler that asks an LLM whether human intervention is needed at this step.

    The node JSON should provide a check query in `data.hitl_check_query` describing
    what to evaluate (e.g., login requires human to type password). 
    Optionally includes `data.context_note` to provide context.

    Expects the LLM to return JSON with keys:
      - Observation: short notes
      - Reasoning: brief reasoning
      - NeedHuman: boolean (true if human action required now)
      - HumanTask: short instruction for the human (required if NeedHuman)
      - AutoInstruction: suggested automated next instruction if no human required
    """

    def handle(
        self,
        planner: None,
        current_node: Dict,
        current_state: Dict,
        screenshot_path: Optional[str] = None,
        query: Optional[str] = None,
        history_md: Optional[str] = None,
        **kwargs,
    ) -> Dict:
        node_id = self._get_node_id(current_node)
        node_title = self._get_node_title(current_node)

        self._log_info(
            f"Evaluating Human-In-The-Loop need: {node_id} - {node_title} (Overall Query: {query})"
        )

        node_data = current_node.get("data", {})
        hitl_check_query = node_data.get("hitl_check_query", "No hitl_check_query provided in node data.")

        if not hitl_check_query:
            error_message = "No hitl_check_query provided in node data."
            self._log_error(f"{error_message} Node: {node_id}")
            return self.build_error_result(
                current_state=current_state,
                error_message=error_message,
                observation="Missing HITL check query",
            )

        system_prompt = render_template("node_hitl/system_prompt.txt")
        user_prompt = render_template(
            "node_hitl/user_prompt.txt",
            overall_task_query=query,
            history_md=history_md,
            hitl_check_query=hitl_check_query,
        )

        user_messages = [
            {
                "role": "user",
                "content": [
                    user_prompt,
                    f"{screenshot_path}" if screenshot_path else "",
                ],
            }
        ]

        try:
            llm_response, token_usage = planner.call_llm(
                messages=user_messages,
                system_prompt=system_prompt,
                llm_model=planner.model,
                log_base_name=f"hitl_node_{node_id}",
                logging_dir=self.logging_dir,
            )

            if llm_response is None:
                raise ValueError("LLM call returned None")

            response_data = json.loads(llm_response.strip())
            self.logger.log_json(
                response_data, f"hitl_node_{node_id}_response.json", self.logging_dir
            )

            observation = response_data.get("Observation", "")
            reasoning = response_data.get("Reasoning", "")
            
            need_human_flag = bool(response_data.get("NeedHuman", False))
            human_task = response_data.get("HumanTask", "")
            auto_instruction = response_data.get("AutoInstruction", "")

            if need_human_flag and not human_task:
                human_task = "Human intervention required, but no task provided."

            hitl_instruction = (
                f"HITL_REQUIRED: {human_task}" if need_human_flag else auto_instruction or "Proceed."
            )

            updated_state = current_state.copy()
            updated_state[f"{node_id}_need_human"] = need_human_flag
            if human_task:
                updated_state[f"{node_id}_human_task"] = human_task

            node_summary = (
                f"Human needed: {human_task}" if need_human_flag else f"No human needed. {auto_instruction}"
            )

            return self.build_success_result({
                "Observation": observation or "",
                "Reasoning": reasoning or "",
                "Instruction": hitl_instruction,
                "is_node_completed": True,
                "current_state": updated_state,
                "node_completion_summary": node_summary,
                "token_usage": token_usage or {},
                # HITL-specific explicit fields
                "need_human_flag": need_human_flag,  # explicit flag for API consumers
                "human_task": human_task,  # guidance for the human
                "auto_instruction": auto_instruction,
            })

        except Exception as e:
            error_msg = f"Error processing Human-In-The-Loop node {node_id}: {e}"
            self._log_warning(error_msg)
            return self.build_error_result(
                current_state=current_state,
                error_message=error_msg,
                observation="Error during HITL node processing",
                extra={
                    "need_human_flag": False,
                    "human_task": "",
                    "auto_instruction": "",
                },
            )
