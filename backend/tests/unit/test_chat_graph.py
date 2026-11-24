"""Graph wiring with stub nodes: routing, the plan/act loop and the step backstop."""

import pytest
from langgraph.errors import GraphRecursionError

from app.domain.agent import ToolCall
from app.workflows.chat_graph import Outcome, build_chat_graph, recursion_limit


class StubNodes:
    def __init__(self, intent="compare", plans=None, route_outcome=None) -> None:
        self.intent = intent
        self.plans = list(plans or [])
        self.route_outcome = route_outcome
        self.visited: list[str] = []

    def route(self, state, context):
        self.visited.append("route")
        update = {"intent": self.intent}
        if self.route_outcome:
            update["outcome"] = self.route_outcome
        return update

    def answer_qa(self, state, context):
        self.visited.append("answer_qa")
        return {"outcome": Outcome("answered", f"qa:{context}")}

    def plan(self, state, context):
        self.visited.append("plan")
        return self.plans.pop(0) if self.plans else {"stop_reason": "finished"}

    def act(self, state, context):
        self.visited.append("act")
        return {"pending": None, "searches": state.get("searches", 0) + 1}

    def synthesize(self, state, context):
        self.visited.append("synthesize")
        return {"outcome": Outcome("answered", f"searches={state.get('searches', 0)}")}


def run(nodes: StubNodes, limit: int = 20):
    return build_chat_graph(nodes).invoke({}, context="ctx", config={"recursion_limit": limit})


def test_qa_intent_skips_the_agent_and_receives_context() -> None:
    nodes = StubNodes(intent="qa")
    state = run(nodes)
    assert nodes.visited == ["route", "answer_qa"]
    assert state["outcome"].answer == "qa:ctx"


def test_route_outcome_ends_the_graph() -> None:
    nodes = StubNodes(route_outcome=Outcome("clarification", "need two documents"))
    state = run(nodes)
    assert nodes.visited == ["route"]
    assert state["outcome"].status == "clarification"


def test_compare_loops_plan_and_act_until_stop() -> None:
    search = {"pending": ToolCall("search", query="q")}
    rejected = {"pending": None}  # a rejected step re-plans without acting
    nodes = StubNodes(plans=[search, rejected, search])
    state = run(nodes)
    assert nodes.visited == [
        "route",
        "plan",
        "act",
        "plan",
        "plan",
        "act",
        "plan",
        "synthesize",
    ]
    assert state["outcome"].answer == "searches=2"


def test_recursion_backstop_stops_a_runaway_planner() -> None:
    nodes = StubNodes(plans=[{"pending": ToolCall("list_documents")}] * 100)
    with pytest.raises(GraphRecursionError):
        run(nodes, limit=recursion_limit(2))
    assert nodes.visited.count("plan") <= 6


def test_node_exceptions_propagate() -> None:
    class Boom(StubNodes):
        def plan(self, state, context):
            raise TimeoutError("provider")

    with pytest.raises(TimeoutError):
        run(Boom())
