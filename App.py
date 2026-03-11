"""
app.py  –  Max Hospital AI Assistant  |  Streamlit Frontend
"""

import html as html_lib
import streamlit as st
from datetime import datetime

import database as db
import agent as ag

# ─────────────────────────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Max Hospital AI Assistant",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────────────────────
# GLOBAL CSS
# ─────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

/* Hide only footer/menu - KEEP header (it has the sidebar toggle) */
#MainMenu, footer { visibility: hidden; }
.block-container { padding-top: 1rem; padding-bottom: 2rem; }

/* ── Sidebar ── */
[data-testid="stSidebar"] {
    background: #1e293b !important;
    border-right: 2px solid #334155 !important;
    min-width: 260px;
}
[data-testid="stSidebar"] > div { background: #1e293b !important; }
[data-testid="stSidebar"] * { color: #e2e8f0 !important; }
[data-testid="collapsedControl"] {
    background: #1e293b !important;
    border: 1px solid #334155 !important;
    color: white !important;
}

.brand-header {
    background: linear-gradient(135deg, #0f6cbd 0%, #1a8cff 100%);
    padding: 16px 20px; border-radius: 12px;
    margin-bottom: 20px; text-align: center;
}
.brand-header h2 { color: white !important; margin: 0; font-size: 1.1rem; font-weight: 700; }
.brand-header p  { color: rgba(255,255,255,0.8) !important; margin: 4px 0 0; font-size: 0.75rem; }

/* ── Stat cards ── */
.stat-card { background: #2d3f55; border: 1px solid #334155; border-radius: 12px; padding: 16px; text-align: center; }
.stat-card .num { font-size: 1.6rem; font-weight: 700; color: #60a5fa !important; }
.stat-card .lbl { font-size: 0.75rem; color: #94a3b8 !important; margin-top: 2px; }

/* ── Messages ── */
.msg-user      { display: flex; justify-content: flex-end; margin: 10px 0; }
.msg-assistant { display: flex; justify-content: flex-start; margin: 10px 0; align-items: flex-start; }

/* FIX: word-wrap + overflow hidden to prevent text leaking out */
.bubble-user {
    background: linear-gradient(135deg, #0f6cbd, #1a8cff);
    color: white; border-radius: 18px 18px 4px 18px;
    padding: 12px 16px; max-width: 68%;
    font-size: 0.875rem; line-height: 1.6;
    box-shadow: 0 2px 8px rgba(15,108,189,0.3);
    word-wrap: break-word; overflow-wrap: break-word;
    white-space: pre-wrap;
}
.bubble-assistant {
    background: white; color: #1e293b;
    border: 1px solid #e2e8f0;
    border-radius: 18px 18px 18px 4px;
    padding: 12px 16px; max-width: 72%;
    font-size: 0.875rem; line-height: 1.6;
    box-shadow: 0 2px 8px rgba(0,0,0,0.06);
    word-wrap: break-word; overflow-wrap: break-word;
    white-space: pre-wrap;
}
.bubble-system {
    background: #fffbeb; color: #92400e;
    border: 1px solid #fcd34d; border-radius: 10px;
    padding: 10px 14px; font-size: 0.82rem;
    width: 100%; margin: 6px 0;
    word-wrap: break-word;
}
.avatar {
    width: 30px; height: 30px; border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    font-size: 13px; flex-shrink: 0;
}
.avatar-bot  { background: linear-gradient(135deg, #0f6cbd, #1a8cff); margin-right: 8px; margin-top: 2px; }
.avatar-user { background: #64748b; margin-left: 8px; }
.ts { font-size: 0.65rem; color: #94a3b8; margin-top: 4px; }

/* ── Intent badge ── */
.badge { display: inline-block; padding: 2px 8px; border-radius: 99px; font-size: 0.7rem; font-weight: 600; margin-bottom: 4px; }
.badge-billing { background: #dbeafe; color: #1e40af; }
.badge-general { background: #d1fae5; color: #065f46; }
.badge-tech    { background: #fce7f3; color: #9d174d; }

/* ── Status bar — compact, max 4 steps visible ── */
.status-bar {
    display: flex; align-items: center; gap: 6px;
    background: #f0f9ff; border: 1px solid #bae6fd;
    border-radius: 8px; padding: 8px 12px;
    font-size: 0.78rem; color: #0369a1;
    margin: 6px 0; overflow: hidden;
    white-space: nowrap;
}
.status-bar .spin {
    width: 14px; height: 14px; border-radius: 50%;
    border: 2px solid #bae6fd; border-top-color: #0369a1;
    animation: spin 0.7s linear infinite; flex-shrink: 0;
}
.step-done   { color: #16a34a; font-size: 0.75rem; }
.step-active { color: #0369a1; font-weight: 600; font-size: 0.78rem; }
.step-sep    { color: #cbd5e1; }

/* ── Streaming cursor ── */
.streaming-cursor::after {
    content: '▋'; animation: blink 0.8s step-end infinite; color: #0f6cbd;
}

/* ── HITL panels ── */
.hitl-panel {
    background: linear-gradient(135deg, #fff7ed, #fffbeb);
    border: 2px solid #f59e0b; border-radius: 14px;
    padding: 18px 22px; margin: 10px 0;
}
.hitl-panel h4 { color: #92400e; margin: 0 0 6px; font-size: 0.95rem; }
.hitl-panel p  { color: #78350f; font-size: 0.83rem; margin: 0 0 14px; }
.email-box {
    background: #f8fafc; border: 1px solid #e2e8f0;
    border-radius: 8px; padding: 12px;
    font-family: 'Courier New', monospace; font-size: 0.76rem;
    color: #334155; white-space: pre-wrap;
    max-height: 260px; overflow-y: auto; margin-bottom: 12px;
    word-wrap: break-word;
}

/* ── Empty state ── */
.empty-state { text-align: center; padding: 50px 20px; color: #94a3b8; }
.empty-state .icon { font-size: 2.8rem; margin-bottom: 10px; }
.empty-state h3 { color: #475569; font-size: 1rem; margin-bottom: 6px; }

/* ── Quick-start chips ── */
.chip {
    display: inline-block;
    background: #f1f5f9; border: 1px solid #e2e8f0;
    border-radius: 99px; padding: 5px 12px;
    font-size: 0.78rem; color: #475569; margin: 3px;
    cursor: pointer; transition: all 0.15s;
}
.chip:hover { background: #dbeafe; border-color: #93c5fd; color: #1e40af; }

@keyframes spin   { to { transform: rotate(360deg); } }
@keyframes blink  { 50% { opacity: 0; } }
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────
# INIT
# ─────────────────────────────────────────────────────────────
db.init_db()
db.clean_html_messages()   # strip stale HTML-in-content rows from old code versions
workflow = ag.get_workflow()

if "active_thread"  not in st.session_state: st.session_state.active_thread  = None
if "pending_state"  not in st.session_state: st.session_state.pending_state  = {}
if "is_streaming"   not in st.session_state: st.session_state.is_streaming   = False


# ─────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────
def _badge(intent: str) -> str:
    cls  = {"billing": "badge-billing", "general": "badge-general",
             "tech": "badge-tech"}.get(intent or "", "badge-general")
    icon = {"billing": "💳", "general": "💬", "tech": "🔧"}.get(intent or "", "💬")
    return f'<span class="badge {cls}">{icon} {(intent or "general").title()}</span>'


def _fmt_time(ts: str) -> str:
    try:
        dt   = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
        diff = (datetime.utcnow() - dt).total_seconds()
        if diff < 60:    return "just now"
        if diff < 3600:  return f"{int(diff//60)}m ago"
        if diff < 86400: return f"{int(diff//3600)}h ago"
        return dt.strftime("%b %d")
    except Exception:
        return ts[:10]


def _render_message(msg: dict):
    role    = msg["role"]
    # FIX: always escape content before injecting into HTML to prevent leakage
    content = html_lib.escape(msg.get("content", ""))
    meta    = msg.get("meta", {})
    ts      = _fmt_time(msg.get("created_at", ""))

    if role == "user":
        st.markdown(f"""
        <div class="msg-user">
          <div>
            <div class="bubble-user">{content}</div>
            <div class="ts" style="text-align:right">{ts}</div>
          </div>
          <div class="avatar avatar-user">👤</div>
        </div>""", unsafe_allow_html=True)

    elif role == "assistant":
        intent_html = _badge(meta.get("intent")) if meta.get("intent") else ""
        st.markdown(f"""
        <div class="msg-assistant">
          <div class="avatar avatar-bot">🏥</div>
          <div style="min-width:0;flex:1">
            {intent_html}
            <div class="bubble-assistant">{content}</div>
            <div class="ts">{ts}</div>
          </div>
        </div>""", unsafe_allow_html=True)

    elif role == "system":
        st.markdown(f'<div class="bubble-system">ℹ️ {content}</div>',
                    unsafe_allow_html=True)


def _run_query(thread_id: str, query: str):
    """Stream agent execution, showing a compact live status bar."""
    db.add_message(thread_id, "user", query)
    st.session_state.is_streaming = True

    status_ph   = st.empty()
    response_ph = st.empty()
    error_ph    = st.empty()

    # Only keep the last 3 completed steps to avoid overflow
    MAX_VISIBLE_STEPS = 3
    completed_steps: list[tuple[str, str]] = []   # (icon, short_label)
    streaming_text = ""

    try:
        for event in ag.stream_turn(workflow, thread_id, query):
            etype = event["type"]

            if etype == "node_start":
                icon  = event["icon"]
                label = event["label"]
                # Show spinner with last N done steps + current active step
                visible = completed_steps[-MAX_VISIBLE_STEPS:]
                done_html = "".join(
                    f'<span class="step-done">{i} {l}</span>'
                    f'<span class="step-sep"> › </span>'
                    for i, l in visible
                )
                status_ph.markdown(f"""
                <div class="status-bar">
                  <div class="spin"></div>
                  {done_html}
                  <span class="step-active">{icon} {label}</span>
                </div>""", unsafe_allow_html=True)

            elif etype == "token":
                streaming_text += event["token"]
                safe = html_lib.escape(streaming_text)
                response_ph.markdown(f"""
                <div class="msg-assistant">
                  <div class="avatar avatar-bot">🏥</div>
                  <div style="min-width:0;flex:1">
                    <div class="bubble-assistant streaming-cursor">{safe}</div>
                  </div>
                </div>""", unsafe_allow_html=True)

            elif etype == "node_end":
                icon, label = ag.NODE_LABELS.get(event["node"], ("⚙️", event["node"]))
                completed_steps.append((icon, label))

            elif etype == "done":
                final_state = event["state"]
                status_ph.empty()
                response_ph.empty()
                response = final_state.get("response") or "I couldn't process that."
                intent   = final_state.get("intent")
                db.add_message(thread_id, "assistant", response, meta={"intent": intent})
                db.update_thread(thread_id, intent=intent)
                st.session_state.pending_state = final_state

            elif etype == "interrupt":
                interrupt_node = event["node"]
                final_state    = event["state"]
                status_ph.empty()
                response_ph.empty()
                st.session_state.pending_state = final_state

                if interrupt_node == "human_escalation":
                    response = final_state.get("response", "")
                    intent   = final_state.get("intent")
                    if response:
                        db.add_message(thread_id, "assistant", response,
                                       meta={"intent": intent})
                    db.add_message(thread_id, "system",
                                   "This query requires escalation. "
                                   "Please review and decide below.")
                    db.update_thread(thread_id, intent=intent)

                elif interrupt_node == "review":
                    db.add_message(thread_id, "assistant",
                                   "Email draft ready for your review.",
                                   meta={"intent": final_state.get("intent"),
                                         "email_draft": final_state.get("email_draft")})

            elif etype == "error":
                status_ph.empty()
                response_ph.empty()
                msg_text = event["message"]
                error_ph.error(f"⚠️ {msg_text}")
                db.add_message(thread_id, "system", f"Error: {msg_text}")

    except Exception as e:
        status_ph.empty()
        response_ph.empty()
        error_ph.error(f"⚠️ Unexpected error: {e}")
        db.add_message(thread_id, "system", f"Unexpected error: {e}")
    finally:
        st.session_state.is_streaming = False


# ─────────────────────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("""
    <div class="brand-header">
      <h2>🏥 Max Hospital</h2>
      <p>AI Assistant · Dehradun</p>
    </div>""", unsafe_allow_html=True)

    all_threads = db.list_threads()
    c1, c2 = st.columns(2)
    with c1:
        st.markdown(f"""<div class="stat-card">
            <div class="num">{len(all_threads)}</div>
            <div class="lbl">Chats</div></div>""", unsafe_allow_html=True)
    with c2:
        total = sum(len(db.get_messages(t["thread_id"])) for t in all_threads) if all_threads else 0
        st.markdown(f"""<div class="stat-card">
            <div class="num">{total}</div>
            <div class="lbl">Messages</div></div>""", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    if st.button("＋  New Conversation", use_container_width=True, type="primary"):
        tid = ag.new_thread_id()
        db.create_thread(tid, "New Conversation")
        st.session_state.active_thread = tid
        st.session_state.pending_state = {}
        st.rerun()

    st.markdown("---")
    st.markdown("**Recent Conversations**")

    if not all_threads:
        st.markdown("*No conversations yet.*")
    else:
        for t in all_threads:
            tid    = t["thread_id"]
            active = tid == st.session_state.active_thread
            intent = t.get("intent") or "general"
            icon   = {"billing": "💳", "general": "💬", "tech": "🔧"}.get(intent, "💬")
            ca, cb = st.columns([5, 1])
            with ca:
                if st.button(f"{icon}  {t['title']}", key=f"t_{tid}",
                             use_container_width=True,
                             type="primary" if active else "secondary"):
                    st.session_state.active_thread = tid
                    st.session_state.pending_state = {}
                    st.rerun()
            with cb:
                if st.button("🗑", key=f"d_{tid}", help="Delete"):
                    db.delete_thread(tid)
                    if st.session_state.active_thread == tid:
                        st.session_state.active_thread = None
                    st.rerun()
            st.caption(_fmt_time(t["updated_at"]))

    st.markdown("---")
    st.markdown("""<div style="font-size:0.7rem;color:#64748b;text-align:center">
    Max Super Specialty Hospital · Dehradun<br>FY 24-25 · LangGraph + Streamlit
    </div>""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────
# MAIN  — never call st.stop(); use if/else so sidebar always renders
# ─────────────────────────────────────────────────────────────
active_tid = st.session_state.active_thread

if not active_tid:
    # ── Welcome / no thread selected ─────────────────────────
    st.markdown("""
    <div class="empty-state">
      <div class="icon">🏥</div>
      <h3>Welcome to Max Hospital AI Assistant</h3>
      <p>Select a conversation from the sidebar or start a new one.</p>
    </div>""", unsafe_allow_html=True)

    st.markdown("**Quick start — try asking:**")
    sample_qs = [
        "What are OPD registration charges?",
        "What is the ICU advance amount?",
        "Refund policy for cancelled surgery?",
        "What is 15% of 35000?",
        "AAPL stock price",
        "Latest AI news",
    ]
    cols = st.columns(3)
    for i, q in enumerate(sample_qs):
        with cols[i % 3]:
            if st.button(q, key=f"s_{i}", use_container_width=True):
                tid = ag.new_thread_id()
                db.create_thread(tid, db.smart_title(q))
                st.session_state.active_thread = tid
                st.session_state.pending_state = {}
                _run_query(tid, q)
                st.rerun()

else:
    # ── Active chat ───────────────────────────────────────────
    thread_info   = db.get_thread(active_tid)
    thread_title  = (thread_info or {}).get("title", "Conversation")
    thread_intent = (thread_info or {}).get("intent", "")
    badge_html    = _badge(thread_intent) if thread_intent else ""

    st.markdown(f"""
    <div style="display:flex;align-items:center;gap:10px;padding:8px 0 14px">
      <span style="font-size:1.4rem">🏥</span>
      <div>
        <div style="font-weight:600;font-size:0.95rem;color:#0f172a">{html_lib.escape(thread_title)}</div>
        <div style="font-size:0.72rem;color:#64748b">
          Thread · {active_tid[:8]}…&nbsp;&nbsp;{badge_html}
        </div>
      </div>
    </div>""", unsafe_allow_html=True)

    # ── Message history ───────────────────────────────────────
    messages = db.get_messages(active_tid)
    if not messages:
        st.markdown("""
        <div class="empty-state" style="padding:30px 0">
          <div class="icon">💬</div>
          <p>Send a message to get started.</p>
        </div>""", unsafe_allow_html=True)
    else:
        for msg in messages:
            _render_message(msg)

    # ── HITL panels ───────────────────────────────────────────
    interrupt = ag.pending_interrupt(workflow, active_tid)
    pending   = st.session_state.pending_state

    if interrupt == "human_escalation":
        st.markdown("""
        <div class="hitl-panel">
          <h4>⚠️ Escalation Required</h4>
          <p>This query needs manual intervention by the billing team.
             Draft and send an escalation email?</p>
        </div>""", unsafe_allow_html=True)
        c1, c2 = st.columns(2)
        with c1:
            if st.button("✅ Yes — Draft Email", type="primary", use_container_width=True):
                with st.spinner("Drafting…"):
                    state = ag.resume_escalation(workflow, active_tid, escalate=True)
                st.session_state.pending_state = state
                db.add_message(active_tid, "system", "Escalation confirmed. Drafting email…")
                st.rerun()
        with c2:
            if st.button("❌ No — Close", use_container_width=True):
                state = ag.resume_escalation(workflow, active_tid, escalate=False)
                st.session_state.pending_state = state
                db.add_message(active_tid, "system", "Escalation declined.")
                st.rerun()

    elif interrupt == "review":
        draft   = pending.get("email_draft", "")
        version = pending.get("draft_version", 1)
        st.markdown(f"""
        <div class="hitl-panel">
          <h4>📧 Email Draft v{version} — Review</h4>
          <p>Approve to send, or provide feedback for revision.</p>
          <div class="email-box">{html_lib.escape(draft)}</div>
        </div>""", unsafe_allow_html=True)
        c1, c2 = st.columns([1, 2])
        with c1:
            if st.button("✅ Approve & Send", type="primary", use_container_width=True):
                with st.spinner("Sending…"):
                    ag.resume_review(workflow, active_tid, approved=True)
                st.session_state.pending_state = {}
                db.add_message(active_tid, "system", "Email approved and sent to billing team.")
                db.add_message(active_tid, "assistant",
                               "The escalation email has been sent to the billing team. "
                               "You will receive a follow-up within 1–2 business days.")
                st.rerun()
        with c2:
            feedback = st.text_input("Revision feedback",
                                     placeholder="e.g. Make it more formal…",
                                     key="review_feedback")
            if st.button("🔄 Revise", use_container_width=True):
                if feedback.strip():
                    with st.spinner("Revising…"):
                        state = ag.resume_review(workflow, active_tid,
                                                 approved=False, feedback=feedback)
                    st.session_state.pending_state = state
                    db.add_message(active_tid, "system", f'Revision requested: "{feedback}"')
                    st.rerun()
                else:
                    st.warning("Please enter feedback first.")

    # ── Input bar ─────────────────────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    hitl_active    = interrupt in ("human_escalation", "review")
    currently_busy = hitl_active or st.session_state.get("is_streaming", False)

    with st.form("chat_form", clear_on_submit=True):
        ci, cs = st.columns([9, 1])
        with ci:
            placeholder = (
                "⏳ Agent is responding…"       if st.session_state.get("is_streaming") else
                "⏳ Complete the action above…" if hitl_active else
                "Ask about billing, charges, stocks, math…"
            )
            user_input = st.text_input("Message", placeholder=placeholder,
                                       disabled=currently_busy,
                                       label_visibility="collapsed")
        with cs:
            submitted = st.form_submit_button("➤", disabled=currently_busy,
                                              use_container_width=True)

    if submitted and user_input.strip():
        query = user_input.strip()
        if (thread_info or {}).get("title") == "New Conversation":
            db.update_thread(active_tid, title=db.smart_title(query))
        _run_query(active_tid, query)
        st.rerun()

    # ── Suggested follow-ups ──────────────────────────────────
    if messages and not hitl_active:
        last_intent = (db.get_thread(active_tid) or {}).get("intent")
        suggestions = {
            "billing": ["ICU advance amount?", "RTGS refund timeline?", "OT booking charges?"],
            "general": ["Latest health news", "18% of 50000?", "TSLA stock price"],
            "tech":    ["Reset portal password", "Contact IT support"],
        }.get(last_intent or "general", [])

        if suggestions:
            st.markdown(
                "<div style='margin-top:6px'>"
                + "".join(f'<span class="chip">{s}</span>' for s in suggestions)
                + "</div>",
                unsafe_allow_html=True,
            )