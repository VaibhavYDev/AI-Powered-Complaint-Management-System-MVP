"""The co-pilot workflow as a LangGraph state machine.

    START -> route -+-> log -----> assess_risk -> END
                    +-> extract -> assess_risk -> END
                    +-> edit ----(touches risk-relevant sections?)--> assess_risk -> END
                                 \\-> END
"""

from langgraph.graph import END, START, StateGraph

from . import nodes
from .nodes import GraphState

RISK_SECTIONS = {"complaint", "patient"}


def _dispatch(state: GraphState) -> str:
    return state["intent"].value.lower()


def _after_edit(state: GraphState) -> str:
    return "assess_risk" if RISK_SECTIONS & state["patch"].keys() else END


def build_graph():
    g = StateGraph(GraphState)
    g.add_node("route", nodes.route)
    g.add_node("log", nodes.log_complaint)
    g.add_node("edit", nodes.edit_complaint)
    g.add_node("extract", nodes.extract_complaint)
    g.add_node("assess_risk", nodes.assess_risk)

    g.add_edge(START, "route")
    g.add_conditional_edges("route", _dispatch, {"log": "log", "edit": "edit", "extract": "extract"})
    g.add_edge("log", "assess_risk")
    g.add_edge("extract", "assess_risk")
    g.add_conditional_edges("edit", _after_edit, {"assess_risk": "assess_risk", END: END})
    g.add_edge("assess_risk", END)
    return g.compile()


graph = build_graph()


def run_copilot(text: str, source: str, existing: dict | None = None) -> GraphState:
    return graph.invoke({"text": text, "source": source, "existing": existing})
