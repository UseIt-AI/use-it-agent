"""
AgentNodeHandler L2 drive script —— no frontend, no real LLM.

做什么
------
1. 用 fake `NodeContext` + 假 `FlowProcessor` 直接调 `AgentNodeHandler.execute()`
2. 用 monkey-patch 替换 `OfficePlanner.plan_streaming`，让它按脚本序列化吐
   预编好的 `PlannerOutput`
3. 把事件流逐条打印出来，并对关键不变量做 assert

覆盖的场景（case）
------------------
- A. engine tool：Planner 选 `ppt_add_slide` → handler 发 tool_call 挂起
     → 模拟 execution_result 回调 → Planner 选 `stop` → 节点完成
- B. inline tool：Planner 选 `tool_web_search`（vendor WebSearchTool 也打桩，
     不发网络） → handler 在进程内跑完 → Planner 再选 `stop` → 节点完成
- C. 未知 action：Planner 选 `foo_bar` → handler 记 error cua_end 并继续
     → 下一轮 Planner 选 `stop`

运行方式
--------
    cd useit-agent-internal
    python -m useit_ai_run.node_handler.agent_node.tests.test_handler_driver

如果缺 langchain_openai / PIL 这些底层依赖（旧 handler 链的同等要求），
会清楚地报出 ImportError；装上再跑即可。

退出码 0 表示 3 个 case 全通过；非 0 表示有 assert 失败。
"""

from __future__ import annotations

import asyncio
import sys
import traceback
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any, AsyncGenerator, Dict, List, Optional


# ---------------------------------------------------------------------------
# 0a. 先兜底：若 env 缺 langchain / PIL 等底层 LLM 链依赖，打最小占位 stub，
#     这样测试可以在任何 python env 里跑（包括 CI 没装第三方包的情形）。
#     真实环境装了依赖时此处 import 成功，下面 _install_stubs_if_missing 就什么都不做。
# ---------------------------------------------------------------------------


def _install_stubs_if_missing() -> None:
    import types as _types

    def _stub(name: str, **attrs: Any) -> None:
        if name in sys.modules:
            return
        m = _types.ModuleType(name)
        for k, v in attrs.items():
            setattr(m, k, v)
        sys.modules[name] = m

    try:
        import langchain_openai  # noqa: F401
    except ImportError:
        class _Dummy:  # 占位类，满足 `from ... import X` 语法
            def __init__(self, *a, **kw): ...

        _stub("langchain", )
        _stub("langchain_openai", ChatOpenAI=_Dummy, AzureChatOpenAI=_Dummy,
              OpenAIEmbeddings=_Dummy)
        _stub("langchain_anthropic", ChatAnthropic=_Dummy)
        _stub("langchain_core")
        _stub("langchain_core.messages",
              AIMessage=_Dummy, HumanMessage=_Dummy, SystemMessage=_Dummy,
              BaseMessage=_Dummy, ToolMessage=_Dummy)
        _stub("langchain_core.prompts",
              ChatPromptTemplate=_Dummy, MessagesPlaceholder=_Dummy)
        _stub("langchain_core.output_parsers", StrOutputParser=_Dummy)
        _stub("langchain_core.runnables",
              RunnablePassthrough=_Dummy, RunnableLambda=_Dummy)
        _stub("langchain_core.callbacks", BaseCallbackHandler=_Dummy)
        _stub("langchain_core.tools", BaseTool=_Dummy, tool=_Dummy)

    try:
        import PIL  # noqa: F401
    except ImportError:
        class _Img:
            def __init__(self, *a, **kw): ...

            @staticmethod
            def open(*a, **kw):
                return _Img()

            @staticmethod
            def new(*a, **kw):
                return _Img()

            def save(self, *a, **kw): ...

        _stub("PIL", Image=_Img, ImageDraw=_Img, ImageFont=_Img)
        _stub("PIL.Image", open=_Img.open, new=_Img.new)
        _stub("PIL.ImageDraw")
        _stub("PIL.ImageFont")

    try:
        import tiktoken  # noqa: F401
    except ImportError:
        class _Enc:
            def encode(self, s): return list(s.encode("utf-8"))
            def decode(self, toks): return bytes(toks).decode("utf-8", errors="ignore")

        def _encoding_for_model(_name): return _Enc()
        def _get_encoding(_name): return _Enc()
        _stub("tiktoken",
              encoding_for_model=_encoding_for_model,
              get_encoding=_get_encoding)


_install_stubs_if_missing()


# ---------------------------------------------------------------------------
# 0b. 在导入 handler 之前先把 vendor WebSearchTool 打桩，让 inline 路径不出网络
# ---------------------------------------------------------------------------

def _stub_vendor_web_search() -> None:
    """把真的 Tavily 调用屏蔽掉；返回一段固定文本。"""
    import types as _types

    module_path = (
        "useit_studio.ai_run.node_handler.functional_nodes.tool_use.tools.web_search.tool"
    )

    class _StubWebSearch:
        def __init__(self, api_key: str = "", openai_api_key: str = "") -> None:
            self.api_key = api_key

        async def invoke(self, query: str, max_results: int = 5):
            return {
                "query": query,
                "max_results": max_results,
                "results": [{"title": "fake-1", "snippet": "this is a stubbed result"}],
            }

    fake_mod = _types.ModuleType(module_path)
    fake_mod.WebSearchTool = _StubWebSearch
    sys.modules[module_path] = fake_mod


_stub_vendor_web_search()


# ---------------------------------------------------------------------------
# 1. 导入真实 handler（及其链上的 OfficePlanner 等）
# ---------------------------------------------------------------------------

from useit_studio.ai_run.node_handler.agent_node import AgentNodeHandler  # noqa: E402
from useit_studio.ai_run.node_handler.agent_node import handler as handler_mod  # noqa: E402
from useit_studio.ai_run.node_handler.agent_node.models import (  # noqa: E402
    PlannerOutput,
)


# ---------------------------------------------------------------------------
# 2. Planner 打桩 —— 按 case 提供一个 PlannerOutput 脚本
# ---------------------------------------------------------------------------


class _ScriptedPlanner:
    """模拟 OfficePlanner：按脚本序列化吐预编好的 plan，不起真实 LLM 连接。"""

    def __init__(self, *args, script: Optional[List[PlannerOutput]] = None, **kwargs):
        self.script = list(script or [])
        self._i = 0
        # Every ``context`` seen by ``plan_streaming`` — exposed so tests
        # can assert what last_execution_output the planner was shown
        # after a suspend/resume round-trip.
        self.contexts_seen: List[Any] = []

    async def plan_streaming(self, context, log_folder=None):
        self.contexts_seen.append(context)
        if self._i >= len(self.script):
            yield {"type": "error", "content": "script exhausted"}
            return
        plan = self.script[self._i]
        self._i += 1
        yield {"type": "reasoning_delta", "content": "<thinking>stub</thinking>"}
        yield {"type": "plan_complete", "content": plan.to_dict()}


class _StubPlannerConfig:
    def __init__(self, *args, **kwargs):
        self.__dict__.update(kwargs)


_LAST_SCRIPTED_PLANNER: Optional[_ScriptedPlanner] = None


def _install_planner_script(script: List[PlannerOutput]) -> None:
    """把 handler 模块里的 OfficePlanner / Config 名字指向脚本式 stub。

    注意两件事：
    1) 必须替换 handler 模块自己的名字绑定，不能只改 base_planner 模块，
       因为 handler 已经通过 `from ... import OfficePlanner` 把名字抓到本地了。
    2) 真实流程里 handler 每次 execute() 都会 new 一个 OfficePlanner；我们
       要让脚本状态跨实例持续，所以 factory 只构造一个 planner 并复用。
    """
    planner = _ScriptedPlanner(script=script)

    def _factory(*args, **kwargs):  # 每次"构造" OfficePlanner 都返回同一个 planner
        return planner

    handler_mod.OfficePlanner = _factory  # type: ignore[attr-defined]
    handler_mod.OfficePlannerConfig = _StubPlannerConfig  # type: ignore[attr-defined]

    global _LAST_SCRIPTED_PLANNER
    _LAST_SCRIPTED_PLANNER = planner


# ---------------------------------------------------------------------------
# 3. Fake FlowProcessor & NodeContext
# ---------------------------------------------------------------------------


@dataclass
class _FakeExecNode:
    step_count: int = 0


class _FakeRuntimeState:
    def __init__(self):
        self._nodes: Dict[str, _FakeExecNode] = {}

    @property
    def state(self):
        return self

    def get_node(self, node_id: str) -> _FakeExecNode:
        return self._nodes.setdefault(node_id, _FakeExecNode())


class _FakeFlowProcessor:
    def __init__(self):
        self.runtime_state = _FakeRuntimeState()
        self.node_states: Dict[str, Any] = {}
        self.graph_manager = SimpleNamespace(get_milestone_by_id=lambda _id: None)


def make_ctx(
    *,
    node_type: str = "agent",
    groups: Optional[List[str]] = None,
    instruction: str = "Open PowerPoint and add a title slide.",
    execution_result: Optional[Dict[str, Any]] = None,
    node_state: Optional[Dict[str, Any]] = None,
    planner_api_keys: Optional[Dict[str, str]] = None,
):
    from useit_studio.ai_run.node_handler.base_v2 import NodeContext

    fp = _FakeFlowProcessor()
    data: Dict[str, Any] = {
        "type": node_type,
        "instruction": instruction,
    }
    if groups is not None:
        data["groups"] = groups

    return NodeContext(
        flow_processor=fp,  # type: ignore[arg-type]
        node_id="agent_test_1",
        node_dict={"id": "agent_test_1", "data": data},
        node_state=node_state or {},
        node_type=node_type,
        screenshot_path="",
        query="Smoke test for agent node",
        log_folder="./logs",
        planner_api_keys=planner_api_keys or {"TAVILY_API_KEY": "stub"},
        execution_result=execution_result,
    )


# ---------------------------------------------------------------------------
# 4. 事件驱动器
# ---------------------------------------------------------------------------


async def drain(gen: AsyncGenerator[Dict[str, Any], None]) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    async for ev in gen:
        events.append(ev)
    return events


def _unwrap_complete(ev: Dict[str, Any]) -> Dict[str, Any]:
    """NodeCompleteEvent.to_dict() 把字段包在 content 里、handler_result 叫 vlm_plan。"""
    content = ev.get("content", {}) or {}
    return {
        "is_node_completed": content.get("is_node_completed"),
        "is_workflow_completed": content.get("is_workflow_completed"),
        "handler_result": content.get("vlm_plan", {}) or {},
        "action_summary": content.get("action_summary", ""),
        "node_completion_summary": content.get("node_completion_summary", ""),
        "raw": ev,
    }


def print_events(label: str, events: List[Dict[str, Any]]) -> None:
    print(f"\n--- events [{label}] ({len(events)}) ---")
    for ev in events:
        t = ev.get("type", "?")
        brief = {
            k: ev[k]
            for k in ("cuaId", "name", "target", "id", "status", "action", "error")
            if k in ev
        }
        extra = ""
        if t == "node_complete":
            c = _unwrap_complete(ev)
            hr = c["handler_result"]
            extra = (
                f"  completed={c['is_node_completed']}"
                f"  waiting={hr.get('waiting_for_execution')}"
                f"  last_tool={hr.get('last_tool')}"
            )
        print(f"  {t:20s} {brief}{extra}")


# ---------------------------------------------------------------------------
# 5. 三个场景
# ---------------------------------------------------------------------------


async def case_a_engine_roundtrip() -> None:
    """engine tool：ppt_add_slide → 挂起 → 回调 → stop。"""
    print("\n===== CASE A: engine tool (ppt_add_slide) round-trip =====")
    script = [
        PlannerOutput.from_dict(
            {
                "Action": "ppt_add_slide",
                "Title": "Add title slide",
                "Params": {"layout": "title"},
                "MilestoneCompleted": False,
            }
        ),
        PlannerOutput.from_dict(
            {
                "Action": "stop",
                "Title": "Done",
                "Params": {},
                "MilestoneCompleted": True,
                "node_completion_summary": "Title slide added.",
            }
        ),
    ]
    _install_planner_script(script)

    # Step 1：第一次调用，不带 execution_result
    ctx1 = make_ctx(
        groups=["ppt"],
        node_state={
            "snapshot": {"presentation_info": {"title": "x"}},  # 触发 ppt pack detect
        },
    )
    handler = AgentNodeHandler()
    ev1 = await drain(handler.execute(ctx1))
    print_events("A.step1", ev1)

    types1 = [e.get("type") for e in ev1]
    assert "tool_call" in types1, f"expect tool_call, got {types1}"
    tc = next(e for e in ev1 if e.get("type") == "tool_call")
    assert tc["target"] == "ppt", tc
    assert tc["name"] == "step", tc
    assert tc["args"]["actions"][0]["action"] == "add_slide", tc

    complete_raw = next(e for e in ev1 if e.get("type") == "node_complete")
    complete = _unwrap_complete(complete_raw)
    assert complete["is_node_completed"] is False, complete
    assert complete["handler_result"].get("waiting_for_execution") is True, complete
    prev_handler_result = complete["handler_result"]

    # Step 2：模拟 tool_call 执行成功后的回调
    ctx2 = make_ctx(
        groups=["ppt"],
        node_state={
            "handler_result": prev_handler_result,
            "_step_count": 1,
            "snapshot": {"presentation_info": {"title": "x"}},
        },
        execution_result={
            "success": True,
            "snapshot": {"slide_count": 2, "current_slide": 2},
        },
    )
    # 同一个 runtime_state 下 step_count 会 +1；这里为了简单直接换 ctx
    ev2 = await drain(handler.execute(ctx2))
    print_events("A.step2", ev2)

    complete2 = _unwrap_complete(
        next(e for e in ev2 if e.get("type") == "node_complete")
    )
    assert complete2["is_node_completed"] is True, complete2
    print(">>> CASE A OK")


async def case_b_inline_tool() -> None:
    """inline tool：tool_web_search → 再 stop。"""
    print("\n===== CASE B: inline tool (tool_web_search) =====")
    script = [
        PlannerOutput.from_dict(
            {
                "Action": "tool_web_search",
                "Title": "Search web",
                "Params": {"query": "langchain openai", "max_results": 3},
                "MilestoneCompleted": False,
            }
        ),
        PlannerOutput.from_dict(
            {
                "Action": "stop",
                "Title": "Done",
                "Params": {},
                "MilestoneCompleted": True,
                "node_completion_summary": "Search done.",
            }
        ),
    ]
    _install_planner_script(script)

    ctx = make_ctx(
        groups=[],  # 无软件白名单，不靠 snapshot；inline tool 不受 group 过滤
    )
    handler = AgentNodeHandler()
    evs = await drain(handler.execute(ctx))
    print_events("B", evs)

    types_ = [e.get("type") for e in evs]
    # inline 不应该发 tool_call
    assert "tool_call" not in types_, f"inline must NOT emit tool_call; got {types_}"
    # 但要有 cua_update with type=tool_web_search
    updates = [e for e in evs if e.get("type") == "cua_update"]
    assert any(
        (u.get("content", {}) or {}).get("type") == "tool_web_search" for u in updates
    ), updates
    complete = _unwrap_complete(
        next(e for e in evs if e.get("type") == "node_complete")
    )
    assert complete["is_node_completed"] is True, complete
    print(">>> CASE B OK")


async def case_c_unknown_action() -> None:
    """未知 action → error cua_end → 下一轮 stop。"""
    print("\n===== CASE C: unknown action (foo_bar) =====")
    script = [
        PlannerOutput.from_dict(
            {
                "Action": "foo_bar",
                "Title": "Impossible",
                "Params": {},
                "MilestoneCompleted": False,
            }
        ),
        PlannerOutput.from_dict(
            {
                "Action": "stop",
                "Title": "Done",
                "Params": {},
                "MilestoneCompleted": True,
                "node_completion_summary": "Stopped.",
            }
        ),
    ]
    _install_planner_script(script)

    ctx = make_ctx(groups=[])
    handler = AgentNodeHandler()
    evs = await drain(handler.execute(ctx))
    print_events("C", evs)

    error_cua_ends = [
        e for e in evs
        if e.get("type") == "cua_end" and e.get("status") == "error"
    ]
    assert len(error_cua_ends) >= 1, "expected at least one error cua_end"
    complete = _unwrap_complete(
        next(e for e in evs if e.get("type") == "node_complete")
    )
    assert complete["is_node_completed"] is True, complete
    print(">>> CASE C OK")


async def case_d_ask_user_roundtrip() -> None:
    """ask_user engine tool: planner pauses → user answers → resume with reply.

    Verifies:
    - Handler emits ``tool_call{target:"user", name:"ask_user"}`` with
      the normalised payload (yes_no → confirm, default Yes/No options
      filled in).
    - Suspends with ``handler_result.last_tool == "ask_user"``.
    - After the frontend replies via ``execution_result.user_response``,
      the re-planning round sees the reply rendered as
      ``"Previous ask_user answer: selected option `yes`."`` in the
      planner's context.
    """
    print("\n===== CASE D: ask_user engine round-trip =====")
    script = [
        PlannerOutput.from_dict(
            {
                "Action": "ask_user",
                "Title": "Confirm destructive delete",
                "Params": {
                    "prompt": "Delete all 42 slides? This cannot be undone.",
                    "kind": "yes_no",  # alias → confirm
                    # Intentionally omit options so the normaliser fills
                    # in Yes/No — verifies the check_permission →
                    # updated_params path.
                    "default_option_id": "no",
                },
                "MilestoneCompleted": False,
            }
        ),
        PlannerOutput.from_dict(
            {
                "Action": "stop",
                "Title": "Done",
                "Params": {},
                "MilestoneCompleted": True,
                "node_completion_summary": "User confirmed; proceeded.",
            }
        ),
    ]
    _install_planner_script(script)

    # Step 1: planner picks ask_user, handler suspends
    ctx1 = make_ctx(groups=[])
    handler = AgentNodeHandler()
    ev1 = await drain(handler.execute(ctx1))
    print_events("D.step1", ev1)

    types1 = [e.get("type") for e in ev1]
    assert "tool_call" in types1, f"expected tool_call, got {types1}"
    tc = next(e for e in ev1 if e.get("type") == "tool_call")
    assert tc["target"] == "user", tc
    assert tc["name"] == "ask_user", tc
    args = tc["args"]
    assert args["kind"] == "confirm", args                      # yes_no → confirm
    assert args["prompt"].startswith("Delete all 42 slides"), args
    option_ids = [o["id"] for o in args["options"]]
    assert option_ids == ["yes", "no"], args                   # default fill-in
    assert args["default_option_id"] == "no", args
    assert args["allow_free_text"] is False, args

    complete_raw = next(e for e in ev1 if e.get("type") == "node_complete")
    complete = _unwrap_complete(complete_raw)
    hr = complete["handler_result"]
    assert complete["is_node_completed"] is False, complete
    assert hr.get("waiting_for_execution") is True, hr
    assert hr.get("last_tool") == "ask_user", hr
    assert hr.get("last_target") == "user", hr
    prev_handler_result = hr

    # Step 2: frontend returns user's answer ("yes") via execution_result
    ctx2 = make_ctx(
        groups=[],
        node_state={
            "handler_result": prev_handler_result,
            "_step_count": 1,
        },
        execution_result={
            "success": True,
            "tool_call_id": hr.get("last_tool_call_id"),
            "user_response": {
                "selected_option_id": "yes",
                "free_text": "",
                "dismissed": False,
            },
        },
    )
    ev2 = await drain(handler.execute(ctx2))
    print_events("D.step2", ev2)

    complete2 = _unwrap_complete(
        next(e for e in ev2 if e.get("type") == "node_complete")
    )
    assert complete2["is_node_completed"] is True, complete2

    # The planner's 2nd invocation must have seen the user's answer
    # rendered into last_execution_output, not the generic
    # ``Payload keys: [...]`` blob.
    assert _LAST_SCRIPTED_PLANNER is not None
    assert len(_LAST_SCRIPTED_PLANNER.contexts_seen) == 2, (
        f"expected 2 planner calls, got {len(_LAST_SCRIPTED_PLANNER.contexts_seen)}"
    )
    second_ctx = _LAST_SCRIPTED_PLANNER.contexts_seen[1]
    leo = getattr(second_ctx, "last_execution_output", "") or ""
    assert "ask_user answer" in leo, f"expected rendered answer, got: {leo!r}"
    assert "selected option `yes`" in leo, f"missing option echo, got: {leo!r}"

    print(">>> CASE D OK")


# ---------------------------------------------------------------------------
# 6. main
# ---------------------------------------------------------------------------


async def main() -> int:
    failures = 0
    for case in (
        case_a_engine_roundtrip,
        case_b_inline_tool,
        case_c_unknown_action,
        case_d_ask_user_roundtrip,
    ):
        try:
            await case()
        except AssertionError as e:
            failures += 1
            print(f"\n!!! {case.__name__} FAILED: {e}")
            traceback.print_exc()
        except Exception as e:  # noqa: BLE001
            failures += 1
            print(f"\n!!! {case.__name__} crashed: {e}")
            traceback.print_exc()

    print("\n=========================================")
    if failures:
        print(f"{failures} case(s) FAILED")
        return 1
    print("All cases PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
