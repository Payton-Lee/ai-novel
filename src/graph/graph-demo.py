from typing import TypedDict

from docutils.nodes import bullet_list
from langchain_community.graphs.rdf_graph import cls_query_rdf
from langchain_core.runnables.graph_mermaid import draw_mermaid_png
from langgraph.constants import END, START
from langgraph.graph import StateGraph


class InputState(TypedDict):
    user_input: str


class OutputState(TypedDict):
    graph_output: str


class OverallState(TypedDict):
    foo: str
    user_input: str
    graph_output: str


class PrivateState(TypedDict):
    bar: str


def node_1(state: InputState) -> OverallState:
    return {"foo": state["user_input"] + "> 学院"}

def node_2(state: OverallState) -> PrivateState:
    return {"bar": state["foo"] + "> 非常"}

def node_3(state: PrivateState) -> OutputState:
    return {"graph_output": state["bar"] + "> 靠谱"}
# 构建图
builder = StateGraph(OverallState, input_schema=InputState, output_schema=OutputState)
# 添加node
builder.add_node("node_1", node_1)
builder.add_node("node_2", node_2)
builder.add_node("node_3", node_3)
# 添加edge
builder.add_edge(START, "node_1")
builder.add_edge("node_1", "node_2")
builder.add_edge("node_2", "node_3")
builder.add_edge("node_3", END)
# 编译图
graph_demo = builder.compile()
