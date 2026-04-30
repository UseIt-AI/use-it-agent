"""Unit tests for PPT ``layout_inspector`` text-fit heuristics."""

from __future__ import annotations

import unittest

from useit_studio.ai_run.node_handler.agent_node.tools.ppt.layout_inspector import (
    inspect_snapshot,
)
from useit_studio.ai_run.node_handler.agent_node.handler import AgentNodeHandler
from useit_studio.ai_run.node_handler.agent_node.tests.test_handler_driver import make_ctx
from useit_studio.ai_run.node_handler.agent_node.tools.ppt.tools import PPTUpdateElement
from useit_studio.ai_run.node_handler.agent_node.models import (
    PlannerOutput,
)


class LayoutInspectorTextFitTests(unittest.TestCase):
    def test_nvda_ticker_narrow_and_tall(self) -> None:
        """Log 260424-181324: narrow ``w`` and tall ``h`` for 4-char ticker."""
        snap = {
            "presentation_info": {
                "slide_width": 648,
                "slide_height": 360,
            },
            "content": {
                "current_slide": {
                    "index": 1,
                    "width": 648,
                    "height": 360,
                    "elements": [
                        {
                            "handle_id": "ticker_text",
                            "type_name": "textbox",
                            "bounds": {
                                "x": 209.25,
                                "y": 100.8,
                                "w": 50,
                                "h": 45.25,
                            },
                            "text": "NVDA",
                            "font": {
                                "name": "Segoe UI",
                                "size": 18.67,
                                "bold": True,
                            },
                        }
                    ],
                }
            },
        }
        r = inspect_snapshot(snap, slide_index=1)
        kinds = {i.kind for i in r.issues}
        self.assertIn("text_fit", kinds)
        self.assertTrue(any("too narrow" in i.message for i in r.issues))
        self.assertTrue(any("likely wrapping" in i.message for i in r.issues))

    def test_single_line_healthy(self) -> None:
        snap = {
            "presentation_info": {"slide_width": 648, "slide_height": 360},
            "content": {
                "current_slide": {
                    "index": 1,
                    "width": 648,
                    "height": 360,
                    "elements": [
                        {
                            "handle_id": "ticker_text",
                            "type_name": "textbox",
                            "bounds": {"x": 200, "y": 100, "w": 120, "h": 24},
                            "text": "NVDA",
                            "font": {"size": 18.67, "bold": True},
                        }
                    ],
                }
            },
        }
        r = inspect_snapshot(snap, slide_index=1)
        self.assertEqual([], [i for i in r.issues if i.kind == "text_fit"])


class PPTUpdateElementBatchTests(unittest.TestCase):
    def test_per_handle_properties_expand(self) -> None:
        tool = PPTUpdateElement()
        po = PlannerOutput(next_action="ppt_update_element", is_milestone_completed=False)
        tc = tool.build_tool_call(
            {
                "slide": 1,
                "handle_ids": ["company_name", "divider"],
                "properties": {
                    "company_name": {"y": 166, "height": 12},
                    "divider": {"y": 180, "height": 0.75},
                },
            },
            po,
        )
        actions = tc.args["actions"]
        self.assertEqual(len(actions), 2)
        by_id = {a["handle_id"]: a["properties"] for a in actions}
        self.assertEqual(by_id["company_name"], {"y": 166, "height": 12})
        self.assertEqual(by_id["divider"], {"y": 180, "height": 0.75})


class ComposeLastExecutionOutputTests(unittest.TestCase):
    def test_does_not_append_stale_last_execution_output_chain(self) -> None:
        """Only ``inline_tail`` is merged, not the legacy chained blob."""
        ctx = make_ctx(
            execution_result={
                "success": True,
                "snapshot": {
                    "presentation_info": {
                        "slide_width": 648,
                        "slide_height": 360,
                    },
                    "content": {
                        "current_slide": {
                            "index": 1,
                            "width": 648,
                            "height": 360,
                            "elements": [],
                        }
                    },
                },
            },
        )
        h = AgentNodeHandler()
        handler_state = {
            "last_execution_output": "Previous tool_call result: STALE_BLOB_SHOULD_NOT_APPEAR",
            "inline_last_execution_output": "[tool_web_search] output:\nNVDA price",
        }
        out = h._compose_last_execution_output(
            ctx,
            handler_state,
            inline_tail=str(handler_state["inline_last_execution_output"]),
        )
        self.assertNotIn("STALE_BLOB_SHOULD_NOT_APPEAR", out)
        self.assertIn("[tool_web_search]", out)


if __name__ == "__main__":
    unittest.main()
