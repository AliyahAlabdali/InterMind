from typing import TypedDict

from langgraph.graph import END, START, StateGraph


class State(TypedDict):
    score: int
    result: str


def evaluate(state: State) -> dict:
    if state["score"] >= 70:
        return {"result": "good"}
    return {"result": "needs_follow_up"}


def good_path(state: State) -> dict:
    return {"result": "Good answer!"}


def follow_up_path(state: State) -> dict:
    return {"result": "Ask a follow-up question."}


def decide_next_step(state: State) -> str:
    return state["result"]


builder = StateGraph(State)

builder.add_node("evaluate", evaluate)
builder.add_node("good_path", good_path)
builder.add_node("follow_up_path", follow_up_path)

builder.add_edge(START, "evaluate")

builder.add_conditional_edges(
    "evaluate",
    decide_next_step,
    {
        "good": "good_path",
        "needs_follow_up": "follow_up_path",
    },
)

builder.add_edge("good_path", END)
builder.add_edge("follow_up_path", END)

graph = builder.compile()


result = graph.invoke({"score": 50, "result": ""})

print(result)