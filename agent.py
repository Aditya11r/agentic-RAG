"""
agent.py  –  Max Hospital Billing Agent (Streamlit-compatible backend)
"""

from __future__ import annotations

import os
import re
import uuid
import requests
import functools
from typing import Optional, Literal, List

from dotenv import load_dotenv
from pydantic import BaseModel

from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
from langchain_core.tools import tool
from langchain_community.vectorstores import FAISS
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode, tools_condition
import sqlite3
from langgraph.checkpoint.sqlite import SqliteSaver
from typing_extensions import TypedDict
from duckduckgo_search import DDGS

load_dotenv()

# Maximum tool-call iterations before forcing a final answer (prevents infinite loops)
MAX_TOOL_ITERATIONS = 4


# ─────────────────────────────────────────────────────────────
# LLM
# ─────────────────────────────────────────────────────────────
def _make_model() -> ChatOpenAI:
    return ChatOpenAI(
        model="arcee-ai/trinity-large-preview:free",
        api_key=os.getenv("OPENAI_API_KEY"),
        base_url=os.getenv("OPENAI_BASE_URL"),
        temperature=0.3,
    )


# ─────────────────────────────────────────────────────────────
# STATE
# ─────────────────────────────────────────────────────────────
class AgentState(TypedDict):
    query:            str
    intent:           Optional[Literal["billing","general"]]
    response:         Optional[str]
    email_required:   Optional[bool]
    draft_version:    int
    escalate:         Optional[bool]
    email_draft:      Optional[str]
    review_status:    Optional[Literal["approved", "revise"]]
    feedback_history: List[str]
    messages:         List[BaseMessage]
    tool_iterations:  int          # guards against infinite tool loops


# ─────────────────────────────────────────────────────────────
# RAG  (built once, reused across requests)
# ─────────────────────────────────────────────────────────────
@functools.lru_cache(maxsize=1)
def _build_retriever(pdf_path: str):
    loader = PyPDFLoader(pdf_path)
    docs   = loader.load()
    chunks = RecursiveCharacterTextSplitter(
        chunk_size=800, chunk_overlap=100          # smaller chunks = faster retrieval
    ).split_documents(docs)
    emb = HuggingFaceEmbeddings(
        model_name="sentence-transformers/all-MiniLM-L6-v2",
        model_kwargs={"device": "cpu"},
        encode_kwargs={"batch_size": 32},
    )
    vs = FAISS.from_documents(chunks, emb)
    return vs.as_retriever(search_type="similarity", search_kwargs={"k": 3})  # k=3 not 5


# ─────────────────────────────────────────────────────────────
# TOOLS
# ─────────────────────────────────────────────────────────────
@tool
def rag_tool(query: str) -> str:
    """Retrieve billing policy from the hospital PDF. Use for any question about
    charges, fees, OPD, IPD, room tariff, advances, refunds, invoices."""
    try:
        pdf = os.getenv("PDF_PATH", "max_hospital.pdf")
        retriever = _build_retriever(pdf)
        results   = retriever.invoke(query)
        if not results:
            return "No relevant billing information found for this query."
        # Return plain string — free models handle str tool results more reliably
        return "\n\n".join(d.page_content for d in results)
    except Exception as e:
        return f"Could not retrieve billing information: {e}"


@tool
def search(query: str) -> str:
    """Search the web for news or general knowledge."""
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, region="us-en", max_results=5))
        if not results:
            return "No results found."
        return "\n".join(
            f"- {r.get('title', '')}: {r.get('body', '')}" for r in results
        )
    except Exception as e:
        return f"Search failed: {e}"


@tool
def cal(num1: float, num2: float, operation: str) -> str:
    """Arithmetic: add, sub, mul, div."""
    ops = {
        "add": lambda a, b: a + b,
        "sub": lambda a, b: a - b,
        "mul": lambda a, b: a * b,
        "div": lambda a, b: a / b if b != 0 else None,
    }
    if operation not in ops:
        return f"Unknown operation '{operation}'. Use: add, sub, mul, div."
    result = ops[operation](num1, num2)
    if result is None:
        return "Error: division by zero."
    return str(result)


@tool
def get_stock(symbol: str) -> str:
    """Get current stock price for a ticker symbol (e.g. AAPL, TSLA)."""
    try:
        url = (
            "https://www.alphavantage.co/query"
            f"?function=GLOBAL_QUOTE&symbol={symbol.upper()}"
            f"&apikey={os.getenv('ALPHA_VANTAGE_KEY', 'demo')}"
        )
        data  = requests.get(url, timeout=8).json()
        quote = data.get("Global Quote", {})
        price = quote.get("05. price")
        if not price:
            return f"Could not fetch price for {symbol}. The ticker may be invalid."
        return f"{symbol.upper()} current price: ${float(price):.2f}"
    except Exception as e:
        return f"Stock lookup failed: {e}"


billing_tools = [rag_tool]
general_tools = [search, cal, get_stock]


# ─────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────
def _text(result) -> str:
    """Extract clean plain text from an LLM response."""
    content = getattr(result, "content", result)
    if isinstance(content, list):
        parts = [
            (block.get("text", "") if isinstance(block, dict) else str(block))
            for block in content
        ]
        raw = " ".join(p for p in parts if p)
    elif isinstance(content, str):
        raw = content
    else:
        raw = ""
    # Clean up escaped newlines, extra whitespace, tool-call JSON leakage
    raw = raw.replace("\\n", "\n").replace("\\t", " ")
    raw = re.sub(r"<tool_call>.*?</tool_call>", "", raw, flags=re.DOTALL)
    raw = re.sub(r"\n{3,}", "\n\n", raw)
    return raw.strip()


def _has_tool_calls(msg) -> bool:
    return bool(getattr(msg, "tool_calls", None))


def _count_tool_iters(messages: list) -> int:
    """Count how many ToolMessage rounds are already in the message list."""
    from langchain_core.messages import ToolMessage
    return sum(1 for m in messages if isinstance(m, ToolMessage))


# ─────────────────────────────────────────────────────────────
# NODE FACTORIES
# ─────────────────────────────────────────────────────────────
def _make_nodes(model: ChatOpenAI):

    router_llm  = model.with_structured_output(_RouterOutput)
    bill_llm    = model.bind_tools(billing_tools)
    general_llm = model.bind_tools(general_tools)

    # ── Router ──────────────────────────────────────────────
    def router_node(state: AgentState):
        query    = state["query"]
        messages = list(state.get("messages", []))

        if not messages or not (
            isinstance(messages[-1], HumanMessage)
            and messages[-1].content == query
        ):
            messages.append(HumanMessage(content=query))

        prompt = (
            "You are a support query classifier for a HOSPITAL billing system.\n\n"
            "Classify into ONE category:\n\n"
            "billing → charges, fees, costs, payments, refunds, invoices, advances, "
            "OPD/IPD rates, room tariffs, doctor fees, registration charges\n\n"
            "general → everything else: greetings, math, news, stocks, health info\n\n"
            "Return only the category name.\n\n"
            f"Query: {query}"
        )
        try:
            result = router_llm.invoke(prompt)
            intent = result.intent
        except Exception:
            intent = "general"

        return {"intent": intent, "messages": messages, "tool_iterations": 0}

    # ── Billing ─────────────────────────────────────────────
    def billing_query_node(state: AgentState):
        query      = state["query"]
        messages   = list(state.get("messages", []))
        iterations = state.get("tool_iterations", 0)

        # Direct escalation — skip RAG entirely
        escalation_phrases = [
            "write a mail", "send a mail", "send an email", "write an email",
            "contact billing", "email billing", "mail to billing", "escalate",
            "raise a complaint", "file a complaint", "speak to billing",
            "talk to billing", "reach billing",
        ]
        if any(p in query.lower() for p in escalation_phrases):
            text = (
               "I'll escalate this to the billing team on your behalf. "
                "Please review the draft email below before it's sent."
            )
            messages.append(AIMessage(content=text))
            return {"response": text, "email_required": True, "messages": messages}

        # Guard: if we've already looped too many times, force a final answer
        if iterations >= MAX_TOOL_ITERATIONS:
            fallback = (
                "Based on the hospital billing policy, I was unable to find a "
                "precise answer. Please contact the billing desk directly."
            )
            messages.append(AIMessage(content=fallback))
            return {"response": fallback, "email_required": False, "messages": messages}

        prompt = f"""
        You are a billing support assistant.

        If the user asks about billing policies like refund, payment failure,
        subscription rules, invoices etc, you MUST use the rag_tool to retrieve
        relevant information from the billing documents.

        If the issue requires manual intervention (duplicate charge, refund processing,
        account correction, or investigation), clearly state that the issue requires
        ESCALATION.

        IMPORTANT:
        When escalation is required only then, include one of the following phrases in your response:
        - escalate to billing team
        - manual review required
        - duplicate charge investigation required
        - investigation required by billing team

        These phrases help the system trigger escalation.

        Customer Query:
        {query}"""
        
        try:
            result = bill_llm.invoke([SystemMessage(content=prompt)] + messages)
        except Exception as e:
            err = f"Billing lookup failed: {e}"
            messages.append(AIMessage(content=err))
            return {"response": err, "email_required": False, "messages": messages}

        messages.append(result)

        if _has_tool_calls(result):
            return {"messages": messages, "tool_iterations": iterations + 1}

        text = _text(result)
        if not text:
            text = (
                "I couldn't find specific information for that query. "
                "Please contact our billing desk directly."
            )

        keywords = ["escalate", "billing team", "manual review",
                    "duplicate charge", "investigation"]
        email_required = any(k in text.lower() for k in keywords)

        return {"response": text, "email_required": email_required, "messages": messages}

    # ── General ─────────────────────────────────────────────
    def general_query_node(state: AgentState):
        query      = state["query"]
        messages   = list(state.get("messages", []))
        iterations = state.get("tool_iterations", 0)

        # Guard against infinite tool loops
        if iterations >= MAX_TOOL_ITERATIONS:
            fallback = "I'm sorry, I couldn't complete that request. Please try rephrasing."
            messages.append(AIMessage(content=fallback))
            return {"response": fallback, "messages": messages}

        prompt = (
            "You are a friendly assistant for Max Hospital, Dehradun.\n\n"
            "Available tools:\n"
            "  • search    – web search (news, knowledge)\n"
            "  • cal       – arithmetic: add/sub/mul/div on two numbers\n"
            "  • get_stock – live stock price by ticker\n\n"
            "Rules:\n"
            "  - Math questions → use cal tool (extract the two numbers and operation)\n"
            "  - News / facts   → use search tool\n"
            "  - Stock prices   → use get_stock tool\n"
            "  - Greetings      → reply directly, no tool\n"
            "  - Anything else  → answer from your knowledge\n\n"
            f"User: {query}"
        )
        try:
            result = general_llm.invoke([SystemMessage(content=prompt)] + messages)
        except Exception as e:
            err = f"Could not process request: {e}"
            messages.append(AIMessage(content=err))
            return {"response": err, "messages": messages}

        messages.append(result)

        if _has_tool_calls(result):
            return {"messages": messages, "tool_iterations": iterations + 1}

        text = _text(result)
        if not text:
            text = "I'm here to help! Could you please rephrase your question?"

        return {"response": text, "messages": messages}

    # ── Billing email router passthrough ────────────────────
    def billing_email_router_node(state: AgentState):
        return {}

    # ── Human escalation (INTERRUPT) ────────────────────────
    def human_escalation_node(state: AgentState):
        return {}

    # ── Draft email ─────────────────────────────────────────
    def draft_email_node(state: AgentState):
        query            = state["query"]
        response         = state.get("response", "")
        feedback_history = state.get("feedback_history", [])
        previous_draft   = state.get("email_draft")
        version          = state.get("draft_version", 0) + 1
        messages         = list(state.get("messages", []))

        base_format = (
            "Subject: <summary>\n\n"
            "Dear Billing Team,\n\n"
            "<2-3 sentences explaining the customer issue clearly>\n\n"
            "Relevant Details:\n"
            f"- Customer Query: {query}\n"
            f"- System Response: {response}\n\n"
            "Requested Action:\n"
            "<specific action needed from the billing team>\n\n"
            "Thank you,\nCustomer Support Assistant\nMax Hospital, Dehradun"
        )

        if previous_draft and feedback_history:
            feedback_text = "\n".join(f"{i+1}. {f}" for i, f in enumerate(feedback_history))
            prompt = (
                f"Rewrite this email incorporating ALL reviewer feedback.\n\n"
                f"Previous draft:\n{previous_draft}\n\n"
                f"Feedback:\n{feedback_text}\n\n"
                f"Use this format:\n{base_format}"
            )
        else:
            prompt = f"Write a professional escalation email.\n\nFormat:\n{base_format}"

        try:
            result = model.invoke(prompt)
            draft  = _text(result)
        except Exception as e:
            draft = f"(Draft generation failed: {e})"

        messages.append(AIMessage(content=draft))
        return {"email_draft": draft, "draft_version": version, "messages": messages}

    # ── Review (INTERRUPT) ──────────────────────────────────
    def review_node(state: AgentState):
        return {}

    # ── Send ────────────────────────────────────────────────
    def send_email_node(state: AgentState):
        # Wire up smtplib / SendGrid here in production
        return {"email_sent": True}

    return (
        router_node, billing_query_node, general_query_node,
        billing_email_router_node, human_escalation_node,
        draft_email_node, review_node, send_email_node,
    )


# ─────────────────────────────────────────────────────────────
# ROUTER SCHEMA
# ─────────────────────────────────────────────────────────────
class _RouterOutput(BaseModel):
    intent: Literal["billing", "general"]


# ─────────────────────────────────────────────────────────────
# ROUTING FUNCTIONS
# ─────────────────────────────────────────────────────────────
def _route_intent(state: AgentState):
    return state.get("intent", "general")

def _billing_email_router1(state: AgentState):
    return "human_escalation" if state.get("email_required") else "__end__"

def _escalation_router(state: AgentState):
    return "draft" if state.get("escalate") else "__end__"

def _review_router(state: AgentState):
    return "send" if state.get("review_status") == "approved" else "draft"

def _general_tools_condition(state: AgentState):
    msgs = state.get("messages", [])
    if msgs and _has_tool_calls(msgs[-1]):
        return "general_tools"
    return "__end__"


# ─────────────────────────────────────────────────────────────
# GRAPH
# ─────────────────────────────────────────────────────────────
def build_workflow(db_path: str = "hospital_chat.db"):
    model = _make_model()
    (
        router_node, billing_query_node, general_query_node,
        billing_email_router_node, human_escalation_node,
        draft_email_node, review_node, send_email_node,
    ) = _make_nodes(model)

    bill_tool_node    = ToolNode(billing_tools)
    general_tool_node = ToolNode(general_tools)

    b = StateGraph(AgentState)

    b.add_node("router",               router_node)
    b.add_node("billing_query",        billing_query_node)
    b.add_node("billing_tools",        bill_tool_node)
    b.add_node("billing_email_router", billing_email_router_node)
    b.add_node("human_escalation",     human_escalation_node)
    b.add_node("draft",                draft_email_node)
    b.add_node("review",               review_node)
    b.add_node("send",                 send_email_node)
    b.add_node("general_query",        general_query_node)
    b.add_node("general_tools",        general_tool_node)

    b.add_edge(START, "router")

    b.add_conditional_edges("router", _route_intent, {
        "billing": "billing_query",
        "general": "general_query",
    })

    b.add_conditional_edges("general_query", _general_tools_condition, {
        "general_tools": "general_tools",
        "__end__":       END,
    })
    b.add_edge("general_tools", "general_query")

    b.add_conditional_edges("billing_query", tools_condition, {
        "tools":   "billing_tools",
        "__end__": "billing_email_router",
    })
    b.add_edge("billing_tools", "billing_query")

    b.add_conditional_edges("billing_email_router", _billing_email_router1, {
        "human_escalation": "human_escalation",
        "__end__":          END,
    })

    b.add_conditional_edges("human_escalation", _escalation_router, {
        "draft":   "draft",
        "__end__": END,
    })

    b.add_edge("draft", "review")

    b.add_conditional_edges("review", _review_router, {
        "send":  "send",
        "draft": "draft",
    })

    b.add_edge("send", END)

    conn         = sqlite3.connect(db_path, check_same_thread=False)
    checkpointer = SqliteSaver(conn)
    return b.compile(
        checkpointer=checkpointer,
        interrupt_before=["human_escalation", "review"],
    )


@functools.lru_cache(maxsize=1)
def get_workflow(db_path: str = "hospital_chat.db"):
    return build_workflow(db_path)


# ─────────────────────────────────────────────────────────────
# PUBLIC API
# ─────────────────────────────────────────────────────────────
def new_thread_id() -> str:
    return str(uuid.uuid4())


# Minimal labels — only the nodes users actually care about seeing
NODE_LABELS = {
    "router":               ("🔀", "Classifying"),
    "billing_query":        ("💳", "Checking billing policy"),
    "billing_tools":        ("📄", "Reading documents"),
    "billing_email_router": ("📬", "Checking escalation"),
    "general_query":        ("🤖", "Processing"),
    "general_tools":        ("🔧", "Using tools"),
    "human_escalation":     ("⚠️",  "Escalation pending"),
    "draft":                ("✍️",  "Drafting email"),
    "review":               ("👁️",  "Review pending"),
    "send":                 ("📤", "Sending email"),
}

# Nodes to HIDE from the status bar (internal plumbing, not useful to users)
_HIDDEN_NODES = {"billing_email_router"}


def stream_turn(workflow, thread_id: str, query: str):
    """
    Streams graph execution events.

    Yields:
      {"type": "node_start",  "node": str, "icon": str, "label": str}
      {"type": "token",       "token": str}
      {"type": "node_end",    "node": str}
      {"type": "done",        "state": dict}
      {"type": "interrupt",   "node": str, "state": dict}
      {"type": "error",       "message": str}
    """
    config = {"configurable": {"thread_id": thread_id}}

    snap = workflow.get_state(config)
    has_existing = snap and snap.values

    init_state = (
        {"query": query, "tool_iterations": 0}
        if has_existing
        else {
            "query":            query,
            "draft_version":    0,
            "messages":         [],
            "feedback_history": [],
            "tool_iterations":  0,
        }
    )

    try:
        for chunk in workflow.stream(init_state, config=config, stream_mode="updates"):
            for node_name, patch in chunk.items():
                if node_name in _HIDDEN_NODES:
                    continue

                icon, label = NODE_LABELS.get(node_name, ("⚙️", node_name))
                yield {"type": "node_start", "node": node_name,
                       "icon": icon, "label": label}

                response_text = (patch or {}).get("response", "")
                if response_text:
                    for word in response_text.split(" "):
                        yield {"type": "token", "token": word + " "}

                yield {"type": "node_end", "node": node_name}

        snap        = workflow.get_state(config)
        final_state = snap.values if snap else {}

        if snap and snap.next:
            yield {"type": "interrupt", "node": snap.next[0], "state": final_state}
        else:
            yield {"type": "done", "state": final_state}

    except Exception as e:
        yield {"type": "error", "message": str(e)}


def resume_escalation(workflow, thread_id: str, escalate: bool) -> dict:
    config = {"configurable": {"thread_id": thread_id}}
    workflow.update_state(config, {"escalate": escalate}, as_node="human_escalation")
    result = workflow.invoke(None, config=config)
    return result if isinstance(result, dict) else {}


def resume_review(workflow, thread_id: str, approved: bool, feedback: str = "") -> dict:
    config = {"configurable": {"thread_id": thread_id}}
    if approved:
        workflow.update_state(config, {"review_status": "approved"}, as_node="review")
    else:
        snap    = workflow.get_state(config)
        history = list((snap.values or {}).get("feedback_history", []))
        history.append(feedback)
        workflow.update_state(
            config,
            {"review_status": "revise", "feedback_history": history},
            as_node="review",
        )
    result = workflow.invoke(None, config=config)
    return result if isinstance(result, dict) else {}


def get_state(workflow, thread_id: str) -> dict:
    config = {"configurable": {"thread_id": thread_id}}
    snap   = workflow.get_state(config)
    return snap.values if snap else {}


def pending_interrupt(workflow, thread_id: str) -> Optional[str]:
    config = {"configurable": {"thread_id": thread_id}}
    snap   = workflow.get_state(config)
    return snap.next[0] if (snap and snap.next) else None