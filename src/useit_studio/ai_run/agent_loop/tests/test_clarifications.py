"""Tests for the cross-layer Clarifications channel.

Covers the plumbing that delivers ``ask_user`` answers from the
orchestrator (and from earlier agent nodes) to every agent_node
planner in a workflow run:

  OrchestratorContext.conversation
    └─ extract_clarifications()  ──┐
                                   ▼
                         AgentLoop._handle_workflow_step
                                   │
                                   ▼
                         FlowProcessor.step(clarifications=…)
                                   │
                                   ▼
                         NodeContext.clarifications
                                   │
                                   ▼
                         PlannerAgentContext.clarifications
                                   │
                                   ▼
               AgentContext.to_prompt() renders
               "## User Clarifications" section

Separate from ``test_ask_user_driver.py`` which focuses on the
orchestrator's own ``ask_user`` round-trip.  This file is all about
what happens *after* the user answered.
"""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from useit_studio.ai_run.agent_loop.action_models import (
    Clarification,
    ConversationTurn,
    OrchestratorContext,
    _parse_free_text,
    _parse_selected_option,
)


# ---------------------------------------------------------------------------
# OrchestratorContext.extract_clarifications()
# ---------------------------------------------------------------------------


class ExtractClarificationsTests(unittest.TestCase):
    def _seed_ask_user_turn(
        self, ctx: OrchestratorContext, tc_id: str, prompt: str,
        options=None,
    ):
        ctx.add_assistant_tool_call([
            {
                "id": tc_id,
                "name": "ask_user",
                "args": {
                    "prompt": prompt,
                    "kind": "confirm",
                    "options": options or [
                        {"id": "yes", "label": "Yes"},
                        {"id": "no", "label": "No"},
                    ],
                },
            }
        ])

    def test_confirm_answer_extracts_option_id_and_label(self):
        ctx = OrchestratorContext(task_id="t1")
        ctx.add_user_message("Use this PPT?")
        self._seed_ask_user_turn(
            ctx, "call_1",
            prompt="Use tmp40liu0sx.pptx or USEIT-BP-天使轮_v4.pptx?",
            options=[
                {"id": "tmp", "label": "tmp40liu0sx.pptx"},
                {"id": "bp", "label": "USEIT-BP-天使轮_v4.pptx"},
            ],
        )
        ctx.add_tool_result(
            tool_call_id="call_1",
            name="ask_user",
            content="User selected option `tmp` (`tmp40liu0sx.pptx`).",
        )

        out = ctx.extract_clarifications()
        self.assertEqual(len(out), 1)
        clar = out[0]
        self.assertEqual(clar.source, "orchestrator")
        self.assertEqual(clar.selected_option_id, "tmp")
        self.assertEqual(clar.selected_option_label, "tmp40liu0sx.pptx")
        self.assertIsNone(clar.free_text)
        # Question rendered from the original ask_user tool args.
        self.assertIn("tmp40liu0sx.pptx", clar.question)

    def test_free_text_answer_populates_free_text_field(self):
        ctx = OrchestratorContext(task_id="t2")
        self._seed_ask_user_turn(
            ctx, "call_1", prompt="What title?", options=[],
        )
        ctx.add_tool_result(
            tool_call_id="call_1",
            name="ask_user",
            content="User free-text reply: Q3 Results",
        )

        out = ctx.extract_clarifications()
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].free_text, "Q3 Results")
        self.assertIsNone(out[0].selected_option_id)

    def test_dismissed_answer_still_produces_clarification(self):
        # Dismissing is itself information — downstream nodes need to
        # know the user declined to disambiguate so they pick a safe
        # default rather than loop on the same prompt.
        ctx = OrchestratorContext(task_id="t3")
        self._seed_ask_user_turn(ctx, "call_1", prompt="Delete all?")
        ctx.add_tool_result(
            tool_call_id="call_1",
            name="ask_user",
            content="User dismissed the question without answering.",
        )

        out = ctx.extract_clarifications()
        self.assertEqual(len(out), 1)
        self.assertIn("dismissed", out[0].answer.lower())

    def test_multiple_ask_user_round_trips_accumulate(self):
        ctx = OrchestratorContext(task_id="t4")
        self._seed_ask_user_turn(ctx, "call_1", prompt="Q1?")
        ctx.add_tool_result(
            "call_1", "ask_user",
            "User selected option `yes` (`Yes`).",
        )
        self._seed_ask_user_turn(ctx, "call_2", prompt="Q2?")
        ctx.add_tool_result(
            "call_2", "ask_user",
            "User free-text reply: my answer",
        )

        out = ctx.extract_clarifications()
        self.assertEqual(len(out), 2)
        self.assertEqual(out[0].selected_option_id, "yes")
        self.assertEqual(out[1].free_text, "my answer")

    def test_question_fallback_when_assistant_turn_missing(self):
        # Defensive: if the state was rehydrated and the assistant turn
        # got dropped somehow, we still produce a Clarification so
        # downstream planners see something.
        ctx = OrchestratorContext(task_id="t5")
        ctx.add_tool_result(
            "orphan_id", "ask_user",
            "User selected option `yes`.",
        )
        out = ctx.extract_clarifications()
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].question, "(question unavailable)")
        self.assertEqual(out[0].selected_option_id, "yes")


class ParseHelpersTests(unittest.TestCase):
    """Both render formats must be accepted — orchestrator and agent_node
    go through different render paths."""

    def test_orchestrator_format_selected_option(self):
        sid, label = _parse_selected_option(
            "User selected option `no` (`Cancel`).",
            [{"id": "yes", "label": "Yes"}, {"id": "no", "label": "Cancel"}],
        )
        self.assertEqual(sid, "no")
        self.assertEqual(label, "Cancel")

    def test_agent_node_format_selected_option(self):
        sid, label = _parse_selected_option(
            "Previous ask_user answer: selected option `use_existing`.",
            [{"id": "use_existing", "label": "Use existing"}],
        )
        self.assertEqual(sid, "use_existing")
        # Label was omitted from the rendered string but we can fall
        # back to the options list.
        self.assertEqual(label, "Use existing")

    def test_free_text_extraction(self):
        self.assertEqual(
            _parse_free_text("User free-text reply: hello world"),
            "hello world",
        )
        self.assertIsNone(_parse_free_text("User selected option `yes`."))


# ---------------------------------------------------------------------------
# AgentContext.to_prompt() clarifications rendering
# ---------------------------------------------------------------------------


class AgentContextRenderTests(unittest.TestCase):
    def _ctx(self, **overrides):
        from useit_studio.ai_run.node_handler.functional_nodes.computer_use.office_agent.models import (
            AgentContext,
        )
        defaults = dict(
            user_goal="the overall goal",
            node_instruction="the current node",
            desktop_snapshot="## Desktop Environment\nwindows: foo",
        )
        defaults.update(overrides)
        return AgentContext(**defaults)

    def test_omitted_section_when_clarifications_empty(self):
        ctx = self._ctx(clarifications=[])
        prompt = ctx.to_prompt()
        self.assertNotIn("## User Clarifications", prompt)

    def test_section_renders_structured_option_answer(self):
        clar = Clarification(
            question="Use tmp40liu0sx.pptx or USEIT-BP-天使轮_v4.pptx?",
            answer="User selected option `tmp` (`tmp40liu0sx.pptx`).",
            selected_option_id="tmp",
            selected_option_label="tmp40liu0sx.pptx",
        )
        ctx = self._ctx(clarifications=[clar])
        prompt = ctx.to_prompt()
        self.assertIn("## User Clarifications", prompt)
        self.assertIn("Use tmp40liu0sx.pptx", prompt)
        self.assertIn("option `tmp`", prompt)
        self.assertIn("tmp40liu0sx.pptx", prompt)
        # "Do not re-ask" nudge must survive minor edits.
        self.assertIn("fixed commitment", prompt.lower())

    def test_section_renders_free_text_answer(self):
        clar = Clarification(
            question="What title?",
            answer="User free-text reply: Q3 Results",
            free_text="Q3 Results",
        )
        ctx = self._ctx(clarifications=[clar])
        prompt = ctx.to_prompt()
        self.assertIn("free-text: Q3 Results", prompt)

    def test_section_placed_between_node_instruction_and_desktop(self):
        # Ordering is load-bearing: the user's intent must be read
        # BEFORE the desktop snapshot, otherwise a candidate list from
        # open_windows can outvote the user's explicit pick.
        clar = Clarification(
            question="Which PPT?",
            answer="User selected option `tmp`.",
            selected_option_id="tmp",
        )
        ctx = self._ctx(clarifications=[clar])
        prompt = ctx.to_prompt()
        i_node = prompt.find("## Current Node Instruction")
        i_clar = prompt.find("## User Clarifications")
        i_desk = prompt.find("## Desktop Environment")
        self.assertTrue(0 <= i_node < i_clar < i_desk, prompt)

    def test_section_renders_multiple_sources(self):
        orch = Clarification(
            question="Which file?",
            answer="User selected option `a`.",
            selected_option_id="a", source="orchestrator",
        )
        node = Clarification(
            question="Overwrite section 3?",
            answer="User selected option `yes`.",
            selected_option_id="yes",
            source="agent_node", source_node_id="node_word_edit",
        )
        ctx = self._ctx(clarifications=[orch, node])
        prompt = ctx.to_prompt()
        self.assertIn("(orchestrator)", prompt)
        self.assertIn("(agent_node:node_word_edit)", prompt)

    def test_accepts_plain_dict_entries(self):
        # Future-proofing: persisted state may rehydrate as dicts.
        ctx = self._ctx(clarifications=[
            {
                "question": "Confirm?",
                "answer": "User selected option `yes`.",
                "selected_option_id": "yes",
                "source": "orchestrator",
            }
        ])
        prompt = ctx.to_prompt()
        self.assertIn("Confirm?", prompt)
        self.assertIn("option `yes`", prompt)


# ---------------------------------------------------------------------------
# FlowProcessor.add_node_clarification() — multi-node accumulation
# ---------------------------------------------------------------------------


class FlowProcessorClarificationsTests(unittest.TestCase):
    def _make_fp(self):
        # Build a FlowProcessor with a barebones GraphManager stub —
        # we only exercise add_node_clarification / node_clarifications,
        # which don't touch the graph.
        from useit_studio.ai_run.agent_loop.workflow.flow_processor import FlowProcessor

        gm = MagicMock(name="GraphManager")
        return FlowProcessor(graph_manager=gm, workflow_id="wf-1", task_id="task-1")

    def test_add_node_clarification_accumulates(self):
        fp = self._make_fp()
        c1 = Clarification(question="Q1", answer="A1")
        c2 = Clarification(question="Q2", answer="A2", source="agent_node",
                           source_node_id="node_x")
        fp.add_node_clarification(c1)
        fp.add_node_clarification(c2)
        self.assertEqual(fp.node_clarifications, [c1, c2])

    def test_node_clarifications_is_copy(self):
        # Mutating the returned list must not leak back into the fp.
        fp = self._make_fp()
        fp.add_node_clarification(Clarification(question="Q", answer="A"))
        snapshot = fp.node_clarifications
        snapshot.clear()
        self.assertEqual(len(fp.node_clarifications), 1)


# ---------------------------------------------------------------------------
# agent_node handler: _maybe_record_ask_user_clarification
# ---------------------------------------------------------------------------


class AgentNodeClarificationPromotionTests(unittest.TestCase):
    """The handler must promote a just-received ask_user answer to a
    cross-node Clarification so *later* nodes see it in their prompt.
    The same-node planner already sees it via ``last_execution_output``."""

    def _make_handler_and_ctx(self, execution_result, handler_state):
        from useit_studio.ai_run.node_handler.agent_node.handler import (
            AgentNodeHandler,
        )
        from useit_studio.ai_run.node_handler.base_v2 import NodeContext

        handler = AgentNodeHandler()
        fp = MagicMock()
        fp.add_node_clarification = MagicMock()
        ctx = NodeContext(
            flow_processor=fp,
            node_id="node_test",
            node_dict={},
            node_state={},
            node_type="agent-node",
            execution_result=execution_result,
        )
        return handler, ctx, fp, handler_state

    def test_records_clarification_on_ask_user_reply(self):
        handler, ctx, fp, hs = self._make_handler_and_ctx(
            execution_result={
                "success": True,
                "user_response": {
                    "selected_option_id": "overwrite",
                    "free_text": "",
                    "dismissed": False,
                },
            },
            handler_state={
                "last_tool": "ask_user",
                "last_ask_user_args": {
                    "prompt": "Overwrite existing section?",
                    "options": [
                        {"id": "overwrite", "label": "Overwrite"},
                        {"id": "append", "label": "Append"},
                    ],
                },
            },
        )
        handler._maybe_record_ask_user_clarification(ctx, hs)
        fp.add_node_clarification.assert_called_once()
        clar = fp.add_node_clarification.call_args[0][0]
        self.assertEqual(clar.source, "agent_node")
        self.assertEqual(clar.source_node_id, "node_test")
        self.assertEqual(clar.selected_option_id, "overwrite")
        self.assertIn("Overwrite existing section", clar.question)

    def test_no_op_when_last_tool_is_not_ask_user(self):
        handler, ctx, fp, hs = self._make_handler_and_ctx(
            execution_result={"success": True, "snapshot": {"slides": []}},
            handler_state={"last_tool": "ppt_snapshot"},
        )
        handler._maybe_record_ask_user_clarification(ctx, hs)
        fp.add_node_clarification.assert_not_called()

    def test_no_op_when_execution_result_empty(self):
        handler, ctx, fp, hs = self._make_handler_and_ctx(
            execution_result=None,
            handler_state={"last_tool": "ask_user"},
        )
        handler._maybe_record_ask_user_clarification(ctx, hs)
        fp.add_node_clarification.assert_not_called()


if __name__ == "__main__":
    unittest.main()
