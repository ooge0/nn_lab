## Here is an attempt to add localization for the UA and ENG languages

import json
import logging
import os
import subprocess
import sys
import time
import traceback
import warnings

import nltk
import ollama
import pandas as pd
import plotly.express as px
import streamlit as st
from loguru import logger
from openai import OpenAI

from core.rag.ingestion import RAGEngine
from core.analysis.model_evaluation import ModelEvaluation
from tmp.simple_plotty_staff import get_high_dim_dashboard

current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)
from core.analysis.calculate_advanced_linguistic_metrics import calculate_advanced_linguistic_metrics
from core.analysis.nlp_science import PsychScientist
from core.analysis.neuro_metrics import NeuroMetrics
from core.analysis.data_contract import LabDataBridge
from core.analysis.cluster_discovery import ClusterDiscovery
import hdbscan
import numpy as np
from sklearn.preprocessing import StandardScaler
import matplotlib.pyplot as plt

logging.getLogger("transformers").setLevel(logging.ERROR)

# Hiding dummy errors in console
warnings.filterwarnings("ignore", category=UserWarning, module="transformers")
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings('ignore', message='.*n_jobs value 1 overridden.*')


# --- 0.Auto-download required resources if missing ---

@st.cache_resource
def ensure_nltk_resources():
    """
    Essential NLP initialization.
    Runs once per session start to ensure no 'Resource Not Found' errors.
    """
    required = [
        'vader_lexicon',
        'punkt',
        'punkt_tab',
        'brown',
        'averaged_perceptron_tagger_eng'
    ]

    for res in required:
        try:
            # Check if it exists locally first
            nltk.data.find(res)
        except (LookupError, AttributeError):
            # Download only if missing
            nltk.download(res, quiet=True)
    return True


ensure_nltk_resources()

# ============================================================
#   CONFIG & DIRECTORIES
# ============================================================
RESULTS_DIR = "results"
LOGS_DIR = "logs"
os.makedirs(LOGS_DIR, exist_ok=True)
os.makedirs(RESULTS_DIR, exist_ok=True)

LOG_FILE = os.path.join(LOGS_DIR, "lab_debug.log")
logger.remove()
logger.add(LOG_FILE, rotation="10 MB", retention="10 days", level="INFO",
           format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}")

# ============================================================
#  PAGE CONFIG
# ============================================================
st.set_page_config(page_title="Psych Data Lab Pro", layout="wide", page_icon="🧠")

st.markdown("""
    <style>
        .terminal-container {
            height: 250px; overflow-y: auto; background: #0e1117;
            border: 1px solid #30363d; border-radius: 4px; padding: 10px;
            font-family: 'Courier New', monospace;
        }
        .terminal-line { border-left: 3px solid #00ff00; padding-left: 10px; margin: 2px 0; font-size: 12px; color: #e0e0e0; }
        .stats-text { font-family: 'Courier New', monospace; font-size: 14px; font-weight: bold; color: #00ff00; }
        .warning-text { color: #ff4b4b; font-size: 12px; margin-top: -10px; margin-bottom: 10px; }
    </style>
    """, unsafe_allow_html=True)


# ============================================================
# CLIENT
# ============================================================
def ensure_ollama_run():
    """Checks if the Ollama service is reachable."""
    try:
        ollama.list()
        return True
    except Exception as e:
        logger.error(f"Ollama connection failed: {e}")
        return False


client = OpenAI(
    base_url="http://localhost:11434/v1",
    api_key="ollama"
)

# ============================================================
# SESSION STATE
# ============================================================

if "history" not in st.session_state: st.session_state.history = []
if "log_entries" not in st.session_state: st.session_state.log_entries = []
if "stop_requested" not in st.session_state: st.session_state.stop_requested = False
if "current_progress" not in st.session_state: st.session_state.current_progress = 0
if "steps" not in st.session_state: st.session_state.steps = 0
if "total_tasks" not in st.session_state: st.session_state.total_tasks = 0
if "is_running" not in st.session_state: st.session_state.is_running = False
if "last_run_summary" not in st.session_state: st.session_state.last_run_summary = ""
if "auto_expanded" not in st.session_state:
    st.session_state.auto_expanded = True
if "exp_expanded" not in st.session_state:
    st.session_state.exp_expanded = True

# Pull State (related to the uploading models via ollama API
if "pull_process" not in st.session_state:
    st.session_state.pull_process = None

if "pull_logs" not in st.session_state:
    st.session_state.pull_logs = []

if "pull_running" not in st.session_state:
    st.session_state.pull_running = False

ARCHETYPES = {
    "Neutral": "Balanced, polite, task-oriented, and objective communication without emotional or structural extremes.",
    "Expressive": "Theatrical, egocentric, focus on external effect.",
    "Defensive": "Suspicious, focus on hidden threats and logic.",
    "Detached": "Emotional coldness, focus on abstract concepts.",
    "Structured": "Focus on order, rules, meticulously aggressive."
}


# ============================================================
# UTILS
# ============================================================
def trigger_stop():
    st.session_state.is_running = False
    st.session_state.stop_requested = False


def extract_best_text(raw_json_str):
    try:
        parsed = json.loads(raw_json_str)
        return str(parsed.get("text", next(iter(parsed.values())) if parsed else "EMPTY"))
    except:
        return raw_json_str


def render_console():
    return f'<div class="terminal-container">{"".join([f"<div class=\"terminal-line\">{e}</div>" for e in reversed(st.session_state.log_entries)])}</div>'


def stream_pull_output(process):
    """
    Reads ollama pull stdout in real time.
    """
    while True:
        line = process.stdout.readline()

        if not line:
            break

        clean = line.strip()

        if clean:
            st.session_state.pull_logs.append(clean)

    process.stdout.close()


# ============================================================
# SIDEBAR
# ============================================================
# --- 5. SIDEBAR ---
if "open_debug" not in st.session_state:
    st.session_state["open_debug"] = False  # Default to open
if st.sidebar.button("Toggle 'Debug' + 'Lab'"):
    st.session_state["open_debug"] = not st.session_state["open_debug"]
    st.rerun()

# ============================================================
# SIDEBAR. DEBUG MODES CONFIGURATION
# ============================================================
st.sidebar.title("🧪 Debug preset")

with st.sidebar.expander("📊 Modes and statuses", expanded=st.session_state["open_debug"]):
    # --- Row 1: Infrastructure Status ---
    status_col1, status_col2 = st.columns(2)

    with status_col1:
        if ensure_ollama_run():
            st.success("Ollama ✅")
        else:
            st.error("Ollama ❌")
            st.caption("Run: `ollama serve`")
            m_names = ["OFFLINE"]

    with status_col2:
        if ensure_nltk_resources():
            st.success("NLP ✅")

    # --- Row 2: Action Buttons ---
    st.write("")  # Spacer
    col_db1, col_db2 = st.columns(2)

    # Mode 1: Self-Critic (SC)
    if col_db1.button("Mode: SC", width='stretch'):
        st.session_state["self_critic"] = True
        st.session_state["prompt_strategy"] = "Behavioral conditioning (Tuned)"
        st.session_state["model_select"] = ["qwen:latest"]
        st.session_state["selected_archetypes"] = ["Detached"]
        st.session_state["current_sweep"] = "None"
        st.session_state["split_biases"] = False
        st.session_state["exclude_from_prompt"] = False
        st.session_state.auto_expanded = False
        st.session_state.exp_expanded = False
        st.toast("Applied Self-Critic Debug Config")
        st.rerun()

    # Mode 2: Teacher-Student
    if col_db2.button("Mode: T-S", width='stretch'):
        st.session_state["self_critic"] = False
        st.session_state["prompt_strategy"] = "Behavioral conditioning (Tuned)"
        st.session_state["model_select"] = ["qwen:latest"]
        st.session_state["teacher_model_key"] = "llama3:latest"
        st.session_state["selected_archetypes"] = ["Detached"]
        st.session_state["current_sweep"] = "None"
        st.session_state["split_biases"] = False
        st.session_state["exclude_from_prompt"] = False
        st.session_state.auto_expanded = False
        st.session_state.exp_expanded = False
        st.toast("Applied Teacher-Student Debug Config")
        st.rerun()

# ============================================================
#
# ============================================================
st.sidebar.title("🧪 Lab controls")
with st.sidebar.expander("📊 Neutral parameters", expanded=st.session_state["open_debug"]):
    base_temp = st.slider("Temperature", 0.0, 2.0, 0.3, 0.1)
    base_top_p = st.slider("Top P", 0.0, 1.0, 0.9, 0.05)
    base_freq = st.slider("Frequency penalty", -2.0, 2.0, 1.1, 0.1)
    base_pres = st.slider("Presence penalty", -2.0, 2.0, 0.2, 0.1)
    base_max_tokens = st.number_input("Max tokens", 10, 4096, 800)
    seed = st.number_input("Random seed", value=42)


# --- Two buttons side by side, outside the expander ---
col1, col2 = st.sidebar.columns(2)

with col1:
    if st.button("💾 Save JSONL", use_container_width=True):
        if st.session_state.history:
            fname = f"{RESULTS_DIR}/lab_export_{time.strftime('%Y%m%d_%H%M%S')}.jsonl"
            with open(fname, 'w', encoding='utf-8') as f:
                for entry in st.session_state.history:
                    f.write(json.dumps(entry, ensure_ascii=False) + '\n')
            st.sidebar.success(f"{fname} saved!")
        else:
            st.sidebar.warning("No data")

with col2:
    if st.button("🗑️ Clear history", use_container_width=True):
        st.session_state.history = []
        st.session_state.log_entries = []
        st.session_state.last_run_summary = ""
        st.session_state.is_running = False
        st.session_state.stop_requested = False
        if "model_select" in st.session_state:
            st.session_state.model_select = []
        st.rerun()


st.sidebar.title("📂 Experiment recovery")
with st.sidebar.expander(" 📂 Upload data", expanded=False):
    uploaded_file = st.file_uploader("Load JSONL for analysis", type=["jsonl"])
    if uploaded_file is not None:
        if st.button("🔄 Inject data"):
            try:
                st.session_state.history = [json.loads(line) for line in uploaded_file if line.strip()]
                st.rerun()
            except Exception as e:
                st.error(str(e))

# ============================================================
#  MAIN INTERFACE
# ============================================================
# 1- 🚀 Generation
# 2- 📊 Performance
# 3- 📈 Analytics
# 4- 🧪 NLP Science
# 5- 🧩 Clustering
# 6- 🧬 Model evaluation
# 7- 📑 Benchmark
# 8- 🖥️ Monitor
# 9- 🛠️ Debug << depends on the SHOW_DEBUG_TAB flag
# 10- ❓ FAQ

SHOW_DEBUG_TAB = False

tab_labels = [
    "🚀 Generation",
    "📊 Performance",
    "📈 Analytics",
    "🧪 NLP Science",
    "🧩 Clustering",
    "🧬 Model evaluation",
    "📑 Benchmark",
    "🖥️ Monitor",
]

if SHOW_DEBUG_TAB:
    tab_labels.append("🛠️ Debug")

tab_labels.append("❓ FAQ")

tabs = st.tabs(tab_labels)

tab_gen = tabs[0]
tab_perf = tabs[1]
tab_analytics = tabs[2]
tab_nlp = tabs[3]
tab_clusters = tabs[4]
tab_model_evo = tabs[5]
tab_benchmark = tabs[6]
tab_monitor = tabs[7]

tab_debug = None

if SHOW_DEBUG_TAB:
    tab_debug = tabs[8]
    tab_faq = tabs[9]
else:
    tab_faq = tabs[8]

df = None

# if "history" in st.session_state and st.session_state.history:
#     df = pd.json_normalize(st.session_state.history)
# else:
#     st.info("Run automation to populate the metric analytics.")
df = pd.json_normalize(st.session_state.history) if st.session_state.history else pd.DataFrame()

# ============================================================
# SESSION STATE INIT
# ============================================================

DEFAULT_SESSION_VALUES = {
    "history": [],
    "log_entries": [],
    "is_running": False,
    "stop_requested": False,
    "current_progress": 0,
    "total_tasks": 0,
    "last_run_summary": "",
    "auto_expanded": True,
    "exp_expanded": True,
    "rag_engine": None,
    "rag_loaded": False
}

for k, v in DEFAULT_SESSION_VALUES.items():
    if k not in st.session_state:
        st.session_state[k] = v


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def trigger_stop():
    """
    Stop current generation loop safely.
    """
    st.session_state.stop_requested = True


def extract_best_text(raw_response):
    """
    Extract clean text from model response.

    Handles:
    - JSON responses
    - plain text
    """

    try:
        import json

        parsed = json.loads(raw_response)

        if isinstance(parsed, dict):
            return parsed.get("text", raw_response)

        return raw_response

    except Exception:
        return raw_response


def render_console():
    """
    Render log console as HTML.
    """

    logs = st.session_state.log_entries[-20:]

    html = """
    <div style="
        background:#111;
        padding:10px;
        border-radius:8px;
        height:300px;
        overflow-y:auto;
        font-family:monospace;
        font-size:12px;
        color:#ddd;
    ">
    """

    for line in logs:
        html += f"<div>{line}</div>"

    html += "</div>"

    return html


# ============================================================
# ARCHETYPES
# ============================================================

ARCHETYPES = {

    "Expressive":
        "Theatrical, egocentric, emotional amplification, dramatic expression.",

    "Defensive":
        "Suspicious, threat-focused, defensive logic, distrustful reasoning.",

    "Detached":
        "Emotionally detached, abstract, low social engagement, conceptual focus.",

    "Structured":
        "Order-focused, rigid, structured, control-oriented communication.",

    "Neutral":
        "Balanced, objective, emotionally neutral, polite and task-oriented."
}

# ============================================================
# BASE GENERATION PARAMS
# ============================================================

base_temp = 0.7
base_top_p = 0.9
base_max_tokens = 300
seed = 42

# ============================================================
#        -=-=-=-=-=-=-=-= UI -=-=-=-=-=-=-=-=
# ============================================================

# ============================================================
# TAB: GENERATION
# Full RAG-enabled Generation Pipeline
# ============================================================

with tab_gen:
    # ========================================================
    # LOAD MODELS
    # ========================================================
    try:
        m_names = [m.model for m in ollama.list().models]

    except Exception:
        m_names = ["ollama_offline"]

    # ========================================================
    # AUTOMATION SUITE
    # ========================================================
    with st.expander("Automation suite", expanded=st.session_state.auto_expanded):
        c1, c2, c3 = st.columns(3)

        # 1. Use st.markdown inside c1 with a header style instead of st.subheader
        c1.markdown("### Model orchestration")

        # 2. Render the fields across the parallel columns
        self_critic = c1.checkbox("Self-Critic mode", key="self_critic")

        # 3. Render the remaining radio options in column 1
        prompt_strategy = c1.radio(
            "Prompt strategy",
            ["Behavioral conditioning (Tuned)", "Blind mode (Hide label)", "Raw / No system prompt"],
            key="prompt_strategy"
        )

        # 5. Teacher (Synced to st.session_state["teacher_model_key"])
        teacher_model = c2.selectbox(
            "Teacher (Judge)",
            ["Select Teacher..."] + m_names,
            disabled=self_critic,
            key="teacher_model_key"
        )

        # 6. Students (Synced to st.session_state["model_select"])
        student_models = c3.multiselect(
            "Students (Generators)",
            m_names,
            key="model_select"
        )
        # ====================================================
        # RAG CONFIG
        # ====================================================

        st.divider()
        st.subheader("RAG Configuration")
        r1, r2, r3, r4 = st.columns([1, 1, 1, 2])
        rag_enabled = r1.checkbox(
            "Enable RAG",
            value=False
        )

        rag_top_k = r2.slider(
            "Top-K",
            1,
            10,
            3,
            disabled=not rag_enabled
        )

        rag_mode = r3.selectbox(
            "Mode",
            [
                "Archetype Only",
                "Archetype + Bias",
                "Global"
            ],
            disabled=not rag_enabled
        )

        # knowledge_path = r4.text_input(
        #     "Knowledge Path",
        #     value="./knowledge",
        # #     disabled=not rag_enabled
        # )

        knowledge_path = "./knowledge"
        # ====================================================
        # LOAD RAG ENGINE
        # ====================================================

        if rag_enabled and not st.session_state.rag_loaded:
            try:
                with st.spinner("Loading RAG knowledge base..."):
                    rag_engine = RAGEngine()
                    rag_engine.load_knowledge_base(
                        knowledge_path
                    )
                    st.session_state.rag_engine = rag_engine
                    st.session_state.rag_loaded = True
                st.success("RAG loaded.")
            except Exception as e:
                st.error(f"RAG load failed: {e}")
                st.code(traceback.format_exc())
        elif not rag_enabled:
            st.session_state.rag_loaded = False
            st.session_state.rag_engine = None
        st.divider()
        # ====================================================
        # PARAM SWEEP
        # ====================================================
        st.subheader("Active sweep parameters")
        current_sweep = st.radio("Sweep Parameter",
                                 ["None", "Temperature", "Top P", "Frequency penalty", "Presence penalty"],
                                 horizontal=True,
                                 key="current_sweep", label_visibility="collapsed")

        # Create weighted columns with a small gap
        r = st.columns([0.6, 0.7, 0.5, 0.4, 0.4, 0.8], gap="small")
        is_none = current_sweep == "None"

        with r[0]:
            sweep_mode = st.selectbox("Mode", ["Delta", "Min-Max"], disabled=is_none, key="sweep_mode")

        # 1. Capture the base value (center)
        center = {
            "Temperature": base_temp,
            "Top P": base_top_p,
            "Frequency penalty": base_freq,
            "Presence penalty": base_pres
        }.get(current_sweep, 0.5)

        # 2. Define v_min and v_max based on mode
        with r[1]:
            if sweep_mode == "Delta":
                delta = st.number_input("Delta", 0.0, 1.0, 0.2, 0.05, disabled=is_none)
                v_min, v_max = (center - delta), (center + delta)
            else:
                # Min-Max Range Slider with 0.05 step
                m_range = st.slider("Range", 0.0, 2.0, (max(0.0, center - 0.2), min(2.0, center + 0.2)), step=0.05,
                                    disabled=is_none)
                v_min, v_max = m_range

        with r[2]:
            steps = st.number_input("Steps", 1, 20, 3, disabled=is_none)

        # --- ASC/DESC checkboxes in individual columns for one-line look ---
        sort_disabled = is_none or sweep_mode == "Min-Max"

        with r[3]:
            st.write(" ")  # Padding
            st.write(" ")
            asc = st.checkbox("ASC", value=True, disabled=sort_disabled)

        with r[4]:
            st.write(" ")  # Padding
            st.write(" ")
            desc = st.checkbox("DESC", value=False, disabled=sort_disabled)

        # --- NOW calculate val_range (after both variables are defined) ---
        if is_none:
            val_range = [center]
        else:
            if steps > 1:
                val_range = [round(v_min + (v_max - v_min) * i / (max(1, steps - 1)), 2) for i in range(steps)]
            else:
                val_range = [v_min]

            # Sorting logic
            if sweep_mode == "Delta":
                if desc and not asc:
                    val_range = sorted(val_range, reverse=True)
                else:
                    val_range = sorted(val_range)  # Default ASC

        # 3. Generate val_range with proper sorting
        if is_none:
            range_text = "STATIC"
        elif sweep_mode == "Delta" and desc and not asc:
            range_text = f"{v_max:.2f} → {v_min:.2f}"
        else:
            range_text = f"{v_min:.2f} → {v_max:.2f}"

        # ---  Render with custom small font ---
        with r[5]:
            st.write(" ")  # Top padding
            st.write(" ")
            # Using markdown with inline CSS for smaller font size
            st.markdown(
                f"""
                <div style="line-height: 1; margin-top: -5px;">
                    <p style="font-size: 0.8rem; color: gray; margin-bottom: 0;">Sweep Range</p>
                    <p style="font-size: 1rem; font-weight: bold;">{range_text}</p>
                </div>
                """,
                unsafe_allow_html=True
            )

        st.divider()

    # ========================================================
    # EXPERIMENT DATA
    # ========================================================

    with st.expander("Experiment data", expanded=st.session_state.exp_expanded):
        c_in, c_out = st.columns(2)
        with c_in:
            # 5. Archetypes (Synced to st.session_state["selected_archetypes"])
            selected_archetypes = st.multiselect(
                "Archetypes",
                list(ARCHETYPES.keys()),
                key="selected_archetypes"
            )

            target_biases_raw = st.text_input(
                "Target biases",
                value="personalization, formal, toxic"
            )

            # 6. Split biases (Synced to st.session_state["split_biases"])
            split_biases = st.checkbox(
                "Split biases",
                key="split_biases"
            )

            # ------------------------------------------------
            # PROMPT MASKING
            # ------------------------------------------------

            mask_disabled = (
                    prompt_strategy ==
                    "Blind mode (Hide label)"
                    or
                    prompt_strategy ==
                    "Raw / No system prompt"
            )

            exclude_from_prompt = st.checkbox(
                "Exclude archetype from prompt",
                value=mask_disabled,
                disabled=mask_disabled
            )

            # ------------------------------------------------
            # SYSTEM PROMPT PREVIEW
            # ------------------------------------------------

            if selected_archetypes:

                display_names = (
                    "[HIDDEN]"
                    if exclude_from_prompt
                    else ", ".join(selected_archetypes)
                )

                if prompt_strategy == "Behavioral conditioning (Tuned)":

                    default_prompt = (
                        f"Act as Behavioral conditioning. "
                        f"Rewrite to the {display_names} archetype(s). "
                        f"Return JSON with 'text' key."
                    )

                elif prompt_strategy == "Blind mode (Hide label)":

                    default_prompt = (
                        "Act as Behavioral conditioning. "
                        "Rewrite using personality traits. "
                        "Return JSON with 'text' key."
                    )

                else:
                    default_prompt = ""

            else:
                default_prompt = ""

            sys_prompt = st.text_area(
                "System prompt",
                value=default_prompt,
                height=100
            )

            # ------------------------------------------------
            # VALIDATION
            # ------------------------------------------------

            missing_params = []

            if not selected_archetypes:
                missing_params.append("Archetypes")

            if not student_models:
                missing_params.append("Students")

            if (
                    not self_critic
                    and
                    (
                            not teacher_model
                            or
                            teacher_model == "Select Teacher..."
                    )
            ):
                missing_params.append("Teacher")

            is_ready_to_run = (
                    len(missing_params) == 0
            )

            if (
                    not is_ready_to_run
                    and
                    not st.session_state.is_running
            ):
                st.warning(
                    f"Missing: {', '.join(missing_params)}"
                )

            # ------------------------------------------------
            # PLACEHOLDERS
            # ------------------------------------------------

            stats_placeholder = st.empty()
            prog_placeholder = st.empty()
            log_placeholder = st.empty()

            log_placeholder.markdown(
                render_console(),
                unsafe_allow_html=True
            )

        # ====================================================
        # RIGHT PANEL
        # ====================================================

        with c_out:

            st.subheader("JSONL Feed")

            for item in reversed(
                    st.session_state.history[-25:]
            ):
                label = (
                    f"{item.get('batch')} | "
                    f"{item.get('student')} | "
                    f"OK: {item.get('v_ok')}"
                )

                with st.expander(label):
                    st.json(item)

    # ========================================================
    # CONTROL BUTTONS
    # ========================================================

    st.divider()

    b1, b2, b3 = st.columns([1, 1, 3])

    with b1:

        if st.button(
                "Run generation",
                disabled=(
                        not is_ready_to_run
                        or
                        st.session_state.is_running
                ),
                width='stretch'
        ):
            st.session_state.is_running = True
            st.session_state.stop_requested = False
            st.rerun()

    with b2:

        if st.button(
                "Stop generation",
                disabled=(
                        not st.session_state.is_running
                ),
                on_click=trigger_stop,
                width='stretch'
        ):
            st.rerun()

    # ========================================================
    # EXECUTION LOOP
    # ========================================================

    if (
            st.session_state.is_running
            and
            not st.session_state.stop_requested
    ):

        try:

            start_batch_time = time.time()

            biases = (
                [b.strip() for b in target_biases_raw.split(",")]
                if split_biases
                else [target_biases_raw]
            )

            st.session_state.total_tasks = (
                    len(student_models)
                    *
                    len(biases)
                    *
                    len(selected_archetypes)
                    *
                    len(val_range)
            )

            st.session_state.current_progress = 0

            # =================================================
            # MAIN NESTED LOOPS
            # =================================================

            for current_type in selected_archetypes:

                if st.session_state.stop_requested:
                    break

                # --------------------------------------------
                # SYSTEM PROMPT
                # --------------------------------------------

                if prompt_strategy == "Raw / No system prompt":

                    iter_sys_prompt = (
                        ARCHETYPES[current_type]
                    )
                
                elif prompt_strategy == "Blind mode (Hide label)":

                    iter_sys_prompt = (
                        "Act as psychologist. "
                        f"Rewrite using traits: "
                        f"{ARCHETYPES[current_type]}. "
                        "Return JSON with 'text' key."
                    )

                else:

                    if exclude_from_prompt:

                        iter_sys_prompt = (
                            "Act as psychologist. "
                            f"Rewrite using traits: "
                            f"{ARCHETYPES[current_type]}. "
                            "Return JSON with 'text' key."
                        )

                    else:

                        iter_sys_prompt = (
                            "Act as psychologist. "
                            f"Rewrite to the "
                            f"{current_type} archetype: "
                            f"{ARCHETYPES[current_type]}. "
                            "Return JSON with 'text' key."
                        )

                # =============================================
                # STUDENT LOOP
                # =============================================

                for student in student_models:

                    if st.session_state.stop_requested:
                        break

                    for b_item in biases:

                        if st.session_state.stop_requested:
                            break

                        for v_val in val_range:

                            if st.session_state.stop_requested:
                                break

                            # --------------------------------
                            # PROGRESS
                            # --------------------------------

                            st.session_state.current_progress += 1

                            elapsed = time.strftime(
                                "%H:%M:%S",
                                time.gmtime(
                                    time.time()
                                    -
                                    start_batch_time
                                )
                            )

                            current_summary = (
                                f"Progress: "
                                f"{st.session_state.current_progress}/"
                                f"{st.session_state.total_tasks} "
                                f"| TYPE: {current_type} "
                                f"| TIME: {elapsed}"
                            )

                            prog_placeholder.progress(
                                st.session_state.current_progress
                                /
                                st.session_state.total_tasks
                            )

                            stats_placeholder.info(
                                current_summary
                            )

                            # --------------------------------
                            # PARAMS
                            # --------------------------------

                            params = {
                                "temperature": v_val if current_sweep == "Temperature"
                                else base_temp,
                                "top_p": v_val if current_sweep == "Top P"
                                else base_top_p,
                                "frequency_penalty": v_val if current_sweep == "Frequency penalty"
                                else base_freq,
                                "presence_penalty": v_val if current_sweep == "Presence penalty"
                                else base_pres,
                                "max_tokens": base_max_tokens,
                                "seed": seed
                            }

                            try:

                                # =================================
                                # RAG RETRIEVAL
                                # =================================

                                rag_context = ""
                                rag_chunks = []
                                rag_query = ""

                                if (
                                        rag_enabled
                                        and
                                        st.session_state.rag_engine
                                ):

                                    if rag_mode == "Archetype Only":

                                        rag_query = current_type

                                    elif rag_mode == "Archetype + Bias":

                                        rag_query = (
                                            f"{current_type} "
                                            f"{b_item}"
                                        )

                                    else:

                                        rag_query = b_item

                                    rag_chunks = (
                                        st.session_state
                                        .rag_engine
                                        .retrieve(
                                            rag_query,
                                            top_k=rag_top_k
                                        )
                                    )

                                    rag_context = "\n\n".join([
                                        (
                                            f"[{x['archetype']} | "
                                            f"{x['category']}]\n"
                                            f"{x['text']}"
                                        )
                                        for x in rag_chunks
                                    ])

                                # =================================
                                # FINAL USER PROMPT
                                # =================================

                                if rag_context:

                                    final_user_prompt = f"""
TASK:
{b_item}

REFERENCE KNOWLEDGE:
{rag_context}

INSTRUCTION:
Generate response using retrieved archetype information.
"""

                                else:

                                    final_user_prompt = b_item

                                # =================================
                                # GENERATION
                                # =================================

                                start_t = time.time()

                                res = client.chat.completions.create(
                                    model=student,
                                    messages=[
                                        {
                                            "role": "system",
                                            "content": iter_sys_prompt
                                        },
                                        {
                                            "role": "user",
                                            "content": final_user_prompt
                                        }
                                    ],
                                    response_format={
                                        "type": "json_object"
                                    }
                                    if "JSON" in iter_sys_prompt
                                    else None,
                                    **params
                                )

                                gen_dur = (
                                                  time.time()
                                                  -
                                                  start_t
                                          ) * 1000

                                clean_text = extract_best_text(
                                    res.choices[0]
                                    .message
                                    .content
                                )

                                # =================================
                                # NLP ANALYSIS
                                # =================================

                                sci = PsychScientist()

                                neuro = NeuroMetrics(
                                    sci.sia
                                )

                                nlp_stats = sci.analyze_text(
                                    clean_text,
                                    gen_dur
                                )

                                neuro_stats = neuro.compute(
                                    clean_text
                                )

                                base_metrics = (
                                    calculate_advanced_linguistic_metrics(
                                        b_item,
                                        clean_text,
                                        gen_dur
                                    )
                                )

                                # =================================
                                # VALIDATION
                                # =================================

                                judge = (
                                    student
                                    if self_critic
                                    else teacher_model
                                )

                                v_start = time.time()

                                v_res = client.chat.completions.create(
                                    model=judge,
                                    messages=[
                                        {
                                            "role": "system",
                                            "content":
                                                (
                                                    "Validator. "
                                                    "Return JSON: "
                                                    "{\"ok\": true/false}"
                                                )
                                        },
                                        {
                                            "role": "user",
                                            "content":
                                                (
                                                    f"Type: {current_type}\n"
                                                    f"Text: {clean_text}"
                                                )
                                        }
                                    ],
                                    response_format={
                                        "type": "json_object"
                                    }
                                )

                                v_ok = (
                                        "true"
                                        in
                                        v_res.choices[0]
                                        .message
                                        .content
                                        .lower()
                                )

                                v_dur = (
                                                time.time()
                                                -
                                                v_start
                                        ) * 1000

                                # =================================
                                # FINAL ENTRY
                                # =================================

                                st.session_state.steps += 1
                                entry = {

                                    "batch": time.strftime("%Y-%m-%d %H:%M:%S"),
                                    "total_tasks": st.session_state.total_tasks,
                                    "steps": st.session_state.steps,
                                    "step":
                                        (
                                            f"{st.session_state.current_progress}/"
                                            f"{st.session_state.total_tasks}"
                                        ),
                                    "strategy": prompt_strategy,
                                    "archetype": current_type,
                                    "split_bias_mode": bool(st.session_state.get("split_biases", False)),
                                    "bias": b_item,
                                    "system_prompt": iter_sys_prompt,
                                    "student": student,
                                    "teacher": judge,
                                    "sweet_param": current_sweep,
                                    "v_ok": v_ok,
                                    "v_ok_numeric": int(v_ok),
                                    "val": v_val,
                                    "output": clean_text,
                                    "duration_ms": gen_dur,
                                    "validation_duration_ms": v_dur,
                                    "rag_enabled": rag_enabled,
                                    "rag_mode":
                                        rag_mode
                                        if rag_enabled
                                        else None,
                                    "rag_top_k":
                                        rag_top_k
                                        if rag_enabled
                                        else None,
                                    "rag_query":
                                        rag_query,
                                    "rag_chunks_count":
                                        len(rag_chunks),
                                    "rag_context_chars":
                                        len(rag_context),
                                    "rag_context":
                                        rag_context
                                }
                                # MERGE METRICS
                                # =================================

                                entry.update(nlp_stats)
                                entry.update(neuro_stats)
                                entry.update(base_metrics)

                                # =================================
                                # SAVE
                                # =================================

                                st.session_state.history.append(
                                    entry
                                )

                                st.session_state.log_entries.append(
                                    (
                                        f"SUCCESS | "
                                        f"{student} | "
                                        f"{current_type}"
                                    )
                                )

                            except Exception as e:

                                st.session_state.log_entries.append(
                                    f"ERROR: {str(e)}"
                                )

                            # --------------------------------
                            # REFRESH LOG
                            # --------------------------------

                            log_placeholder.markdown(
                                render_console(),
                                unsafe_allow_html=True
                            )

            st.success("Generation complete.")

        except Exception as e:

            st.error(f"Critical error: {e}")

        finally:

            st.session_state.is_running = False
            st.session_state.stop_requested = False

            st.rerun()

# ============================================================
# Performance TAB (HIDDEN)
# ============================================================
with tab_perf:
    st.subheader("📊 Performance Summary")
    if df is None or df.empty:
        st.info("No experiment data found. Run a generation first or upload data set.")
    else:
        # --- 1. Calculate General Metrics ---
        total_records = len(df)

        # Determine Sweep Info (using 'sweet_param' and 'val' from your JSONL)
        sweep_name = df['sweet_param'].iloc[0] if 'sweet_param' in df.columns else "N/A"
        if 'val' in df.columns:
            val_min = df['val'].min()
            val_max = df['val'].max()
            sweep_range = f"{val_min} — {val_max}"
        else:
            sweep_range = "N/A"

        # Calculate Duration (using the 'batch' timestamp as a proxy or sum of durations)
        # If 'batch' is your start time, we take the difference between last and first
        try:
            df['batch_dt'] = pd.to_datetime(df['batch'])
            start_time = df['batch_dt'].min()
            end_time = df['batch_dt'].max()
            # If all have the same batch timestamp, we sum the actual processing durations
            total_duration_sec = df['duration_ms'].sum() / 1000
            duration_str = f"{total_duration_sec / 60:.2f} min"
        except:
            duration_str = "Unknown"
        # --- Calculate Remaining Metadata for summary_data ---

        # 1. Basic Stats
        total_records = len(df)
        steps_count = df['step'].iloc[-1] if 'step' in df.columns else "N/A"

        # 2. Models
        teachers = df['teacher'].unique().tolist()
        students = df['student'].unique().tolist()

        # 3. Strategy & Logic
        prompt_strategy = df['strategy'].unique().tolist()
        archetypes_list = df['archetype'].unique().tolist()
        bias_mode = df['bias'].unique().tolist()

        # 4. RAG Status
        rag_active = df['rag_enabled'].any()
        rag_modes = df['rag_mode'].unique().tolist() if rag_active else ["Disabled"]

        # 5. Final summary_data Dictionary
        summary_data = {
            "Metric": [
                "Total Records",
                "Steps",
                "Sweep Parameter",
                "Value Range",
                "Estimated Processing Time",
                "Avg. MS per Word",
                "Avg. Validation Time",
                "teacher",
                "student(s)",
                "Prompt strategy",
                "Archetypes",
                "Biases",
                "Split bias mode",
                "RAG enabled",
                "RAG configuration mode"
            ],
            "Value": [
                total_records,
                steps,
                sweep_name,
                sweep_range,
                duration_str,
                f"{df['ms_per_word'].mean():.2f} ms",
                f"{df['validation_duration_ms'].mean() / 1000:.2f} sec",
                ", ".join(teachers),
                ", ".join(students),
                ", ".join(map(str, prompt_strategy)),
                ", ".join(map(str, archetypes_list)),
                ", ".join(map(str, bias_mode)),
                "✅ Enabled" if st.session_state.get("split_biases", False) else "❌ Disabled",
                "✅ Yes" if rag_active else "❌ No",
                ", ".join([str(m) for m in rag_modes if m is not None])
            ]
        }
        with st.expander("Summary for the current experiment", expanded=True):
            # Convert dict → DataFrame first
            summary_df = pd.DataFrame(summary_data)

            # Cast all values to string if needed (avoids Arrow serialization errors)
            summary_df = summary_df.astype(str)

            # Display in Streamlit
            st.table(summary_df)

        # --- 6. Full Data View ---
        with st.expander("Raw experiment logs", expanded=False):
            st.dataframe(df, width='stretch')

# ============================================================
# Analytics
# ============================================================
with tab_analytics:
    st.subheader("📈 Analytics")

    if st.session_state.history:
        # Load data from session history
        df = pd.json_normalize(st.session_state.history)

        # Define subtabs
        sub_tab_heatmap, sub_tab_high_dim, sub_tab_zipf = st.tabs([
            "🔥 Adherence & Metrics",
            "🌐 High-Dim Analytics",
            "📊 Zipf Deviation"
        ])

        # -------------------------------
        # Subtab 1: Adherence & Metrics
        # -------------------------------
        with sub_tab_heatmap:
            st.subheader("🔥 Adherence Heatmap (By Parameter)")
            if 'val' in df.columns and 'v_ok_numeric' in df.columns:
                pivot = df.pivot_table(
                    index='student',
                    columns='val',
                    values='v_ok_numeric',
                    aggfunc='mean',
                    fill_value=0
                )
                st.dataframe(
                    pivot.style.background_gradient(cmap='RdYlGn', axis=None).format("{:.0%}"),
                    width='stretch'
                )

            st.plotly_chart(
                px.pie(df, names='student', title="Workload Distribution", template="plotly_dark"),
                width='stretch'
            )

            st.divider()
            st.subheader("⚡ Performance & Velocity")
            col_p1, col_p2 = st.columns(2)
            with col_p1:
                st.plotly_chart(
                    px.box(df, x="student", y="duration_ms", color="student", title="Latency (ms)",
                           template="plotly_dark"),
                    width='stretch'
                )
            with col_p2:
                st.plotly_chart(
                    px.line(df, y="ms_per_word", color="student", title="Generation Velocity (ms/word)",
                            template="plotly_dark"),
                    width='stretch'
                )

            st.divider()
            st.subheader("📝 Volume & Diversity")
            col_v1, col_v2 = st.columns(2)
            with col_v1:
                st.plotly_chart(
                    px.line(df, y="word_count", color="student", markers=True, title="Word Count Consistency",
                            template="plotly_dark"),
                    width='stretch'
                )
            with col_v2:
                st.plotly_chart(
                    px.bar(df, x="student", y="unique_ratio", color="student", title="Vocabulary Diversity Ratio",
                           template="plotly_dark"),
                    width='stretch'
                )

            st.divider()
            st.subheader("⚖️ Linguistic Distance")
            col_l1, col_l2 = st.columns(2)
            with col_l1:
                st.plotly_chart(
                    px.bar(df, x="student", y="levenshtein_dist", color="val", barmode="group",
                           title="Levenshtein Distance to Teacher", template="plotly_dark"),
                    width='stretch'
                )
            with col_l2:
                st.plotly_chart(
                    px.line(df, y="semantic_overlap", color="student", title="Semantic Alignment Overlap",
                            template="plotly_dark"),
                    width='stretch'
                )

            st.divider()
            st.subheader("🎭 Psycholinguistic Signature")
            st.plotly_chart(
                px.scatter(df, x="punc_density", y="expansion_ratio", color="archetype", symbol="student",
                           size="word_count", title="Style Distribution (Raw Space)", template="plotly_dark"),
                width='stretch'
            )

        # -------------------------------
        # Subtab 2: High-Dim Analytics
        # -------------------------------
        with sub_tab_high_dim:
            st.subheader("🌐 Multi-Model Dependency Analytics")
            required_cols = ['lexical_density', 'ms_per_word', 'cognitive_load']
            if all(col in df.columns for col in required_cols):
                with st.spinner("Calculating Pipeline..."):
                    figs = get_high_dim_dashboard(df)

                st.write("#### 🔀 Logic Pipeline")
                st.plotly_chart(figs[0], width='stretch', key="plot_logic_psy")
                st.plotly_chart(figs[1], width='stretch', key="plot_logic_success")

                st.write("#### 🏗️ Model Productivity Matrix")
                st.plotly_chart(figs[2], width='stretch', key="plot_productivity")

                st.write("#### 🧪 Dependency Matrices")
                st.plotly_chart(figs[3], width='stretch', key="plot_matrix_teacher")
                st.plotly_chart(figs[4], width='stretch', key="plot_matrix_cross")
            else:
                st.warning(f"Missing columns: {[c for c in required_cols if c not in df.columns]}")

        # -------------------------------
        # Subtab 3: Zipf Deviation
        # -------------------------------
        with sub_tab_zipf:
            st.subheader("📊 Zipf Deviation Benchmarking")

            if "zipf_deviation" in df.columns:
                # Distribution per model
                st.plotly_chart(
                    px.box(df, x="student", y="zipf_deviation", color="student",
                           title="Zipf Deviation Distribution (Normalized)",
                           template="plotly_dark"),
                    width='stretch'
                )

                # By archetype
                if "archetype" in df.columns:
                    st.plotly_chart(
                        px.bar(df, x="archetype", y="zipf_deviation", color="student",
                               barmode="group", title="Zipf Deviation by archetype",
                               template="plotly_dark"),
                        width='stretch'
                    )
            else:
                st.warning("No Zipf deviation scores found in history. Run generation with metrics enabled.")



    else:
        st.info("No experiment data found. Run a generation first or upload data set.")


# ============================================================
#  NLP Science
# ============================================================
with tab_nlp:
    st.subheader("🧪 Deep NLP Investigation (NLTK)")
    if st.session_state.history:
        with st.spinner("Processing Scientific Metrics..."):
            # Use the Bridge to build the optimized DataFrame
            # This handles normalization, POS flattening, and numeric conversion
            full_df = LabDataBridge.build_dataframe(st.session_state.history)
            logger.debug(f'{full_df.columns}')

        # Layout for algorithms
        sub_tab_nlp_1, sub_tab_nlp_2, sub_tab_nlp_3 = st.tabs(["NLP-1", "NLP-2", "NLP-3"])
        with sub_tab_nlp_1:
            # Row 1: POS Morphology Profile
            # Note: 'Adjectives', 'Nouns', and 'Verbs' are created in LabDataBridge
            st.plotly_chart(px.scatter_ternary(
                full_df,
                a="pos_adj",
                b="pos_noun",
                c="pos_verb",
                color="archetype",
                size="word_count",
                title="POS Morphology Profile"
            ), width='stretch')

            # --- Row 2: Archetype Proofs ---
            st.divider()
            col_a, col_b = st.columns(2)

            with col_a:
                st.write(
                    "**Cognitive Complexity (Readability vs Diversity)**")
                # Detacheds usually cluster top-right (High ARI, High TTR)
                st.plotly_chart(px.scatter(
                    full_df, x="readability_ari", y="corrected_ttr",
                    color="archetype", symbol="student", size="word_count",
                    title="Intelligence & Vocabulary Breadth"
                ), width='stretch')

            with col_b:
                st.write(
                    "**Emotional Engagement (Subjectivity vs Sentiment)** ")
                st.plotly_chart(px.scatter(
                    full_df, x="subjectivity", y="sentiment",
                    color="archetype",
                    symbol="student",
                    size="lexical_density",
                    facet_col="bias",
                    size_max=15,
                    # hover_data=["bias"],
                    title="Bias & Polarity Analysis"
                ), width='stretch')

        # --- Row 3: Psycholinguistic Signals ---
        with sub_tab_nlp_2:
            col_c, col_d = st.columns(2)

            with col_c:
                st.write(
                    "**Emotional Stability (Sentiment Variance)**")

                st.plotly_chart(px.box(
                    full_df,
                    x="archetype",
                    y="sentiment_variance",
                    color="archetype",
                    points="all",
                    title="Emotional Variability per archetype"
                ), width='stretch')

            with col_d:
                st.write("**Repetition / Fixation Patterns**")
                st.plotly_chart(px.box(
                    full_df,
                    x="bias",
                    y="repetition_score",
                    color="archetype",
                    points="all",
                    notched=True,
                    title="Repetition Triggered by Bias Type"
                ), width='stretch')
        with sub_tab_nlp_3:
            # --- Row 4: Sentence Structure ---
            st.write(
                "**Syntactic Flow (Sentence Length Distribution)**")
            st.plotly_chart(px.box(
                full_df, x="archetype", y="avg_sentence_length",
                color="archetype", points="all", title="Sentence Length per archetype"
            ), width='stretch')

            # --- Row 5: Neuropsychological Metrics ---
            st.divider()
            col_e, col_e_e = st.columns(2)
            with col_e:
                st.write("**Self-Focus vs Cognitive Rigidity** ")
                st.plotly_chart(px.scatter(
                    full_df,
                    x="neuro_self_focus",
                    y="rigidity",
                    color="archetype",
                    size="word_count",
                    # This is your Alias mapping
                    labels={
                        "neuro_self_focus": "Self-Reference (I-Factor)",
                        "rigidity": "Cognitive Rigidity (Fixation)",
                        "archetype": "Archetype Cluster"
                    },
                    hover_data=["bias", "student"],
                    title="Egocentricity vs Fixation"
                ), width='stretch')

            with col_e_e:
                st.write(
                    "**Self-Focus vs Cognitive Rigidity (Bias Dependency)**")
                st.plotly_chart(px.scatter(
                    full_df,
                    x="neuro_self_focus",
                    y="rigidity",
                    color="archetype",
                    facet_col="bias",
                    size="word_count",
                    hover_data=["student", "val"],
                    labels={
                        "neuro_self_focus": "I-Factor",
                        "rigidity": "Cognitive Rigidity (Fixation)",
                        "archetype": "Archetype Cluster"
                    },
                    title="Egocentricity vs Fixation by Input Bias"
                ), width='stretch')

            st.divider()
            col_f, col_f_f = st.columns(2)
            with col_f:
                st.write("**Rigidity Distribution by Bias Type** ")
                st.plotly_chart(px.box(
                    full_df,
                    x="bias",
                    y="rigidity",
                    color="archetype",
                    points="all",
                    notched=True,
                    title="Linguistic Rigidity: Impact of Bias",
                    hover_data = "student",
                ), width='stretch')

            with col_f_f:
                st.write("**Abstraction vs Cognitive Load** ")
                st.plotly_chart(px.scatter(
                    full_df,
                    x="neuro_abstract_ratio_ext",
                    y="neuro_cognitive_load",
                    color="archetype",
                    size="word_count",
                    title="Abstract Thinking vs Processing Load",
                    hover_data="student",
                ), width='stretch')

            # --- Row 6: Coherence & Emotional Dynamics ---

            st.divider()
            col_g, col_h = st.columns(2)

            with col_g:
                st.write("**Narrative Coherence Distribution** ")
                st.plotly_chart(px.box(
                    full_df,
                    x="archetype",
                    y="neuro_coherence",
                    color="archetype",
                    points="all",
                    title="Logical Continuity per archetype",
                    hover_data="student",
                ), width='stretch')

            with col_h:
                st.write(
                    "**Emotional Volatility (Sentence Variance)**")
                st.plotly_chart(px.box(
                    full_df,
                    x="archetype",
                    y="sentiment_variance",
                    color="archetype",
                    points="all",
                    title="Emotional Stability per archetype",
                    hover_data="student",
                ), width='stretch')
    else:
        st.info("No experiment data found. Run a generation first or upload data set.")

# ============================================================
#  Clustering
# ============================================================
with tab_clusters:
    st.subheader("🧬 Multi-Dimensional Analysis")
    if df is None or df.empty:
        st.info("No experiment data found. Run a generation first or upload data set.")
    else:
        # Layout for algorithms
        sub_tab_pca, sub_tab_hdbscan, sub_tab_hdbscan_UMAP, sub_tab_hdbscan_UMAP_old = st.tabs(
            ["K-Means (PCA)", "HDBSCAN (Density)", "sub_tab_hdbscan_UMAP", "sub_tab_hdbscan_UMAP_old"])

        with sub_tab_pca:
            # 1. Configuration & Data Prep
            c1, c2 = st.columns([1, 2])
            with c1:
                n_clusters = st.slider("Number of Clusters", 2, 8, 3)
            with c2:
                # Allow user to toggle colors between Ground Truth and K-Means Clusters
                color_target = st.radio(
                    "Color Points By:", ["archetype", "cluster_id", "student", "v_ok"],
                    horizontal=True,
                    help="Switch between actual archetypes or machine-discovered clusters."
                )

            # Load and Clean Data
            raw_history = pd.json_normalize(st.session_state.history)

            # Identify numeric columns and exclude technical coordinates
            numeric_cols = raw_history.select_dtypes(include=[np.number]).columns
            exclude_from_fit = ['x', 'y', 'cluster_id']
            fit_features = [c for c in numeric_cols if c not in exclude_from_fit]

            # Create clean copy for clustering
            clean_history = raw_history.copy()
            clean_history[fit_features] = clean_history[fit_features].replace([np.inf, -np.inf], np.nan).fillna(0)

            discovery = ClusterDiscovery(n_clusters=n_clusters)

            try:
                # --- PROCESS CLEAN DATA ---
                df_clustered = discovery.process_data(clean_history)

                # 2. Advanced 2D PCA Visualization
                fig = px.scatter(
                    df_clustered,
                    x='x', y='y',
                    color=color_target,
                    symbol='student',
                    hover_data=['archetype', 'bias', 'val', 'v_ok'],
                    title=f"PCA Space: {color_target.capitalize()} distribution",
                    template="plotly_dark",
                    color_discrete_sequence=px.colors.qualitative.Vivid
                )

                fig.update_traces(
                    marker=dict(size=9, opacity=0.75, line=dict(width=1, color='rgba(255, 255, 255, 0.5)')))
                fig.update_layout(height=600, legend_title_text='Legend')
                st.plotly_chart(fig, width='stretch')

                # 3. Visual Driver Analysis
                st.write("### 🚀 Axis Drivers Interpretation")
                pc1_drivers, pc2_drivers = discovery.get_component_dependencies()


                def plot_drivers(drivers, axis_name):
                    top_drivers = drivers.reindex(drivers.abs().sort_values(ascending=False).index).head(10)
                    fig_dr = px.bar(
                        top_drivers,
                        orientation='h',
                        labels={'value': 'Impact Strength', 'index': 'NLP Metric'},
                        color=top_drivers.values,
                        color_continuous_scale='RdBu',
                        title=f"Top Drivers for {axis_name}"
                    )
                    fig_dr.update_layout(showlegend=False, height=350, margin=dict(l=20, r=20, t=40, b=20))
                    return fig_dr


                col_d1, col_d2 = st.columns(2)
                with col_d1:
                    st.plotly_chart(plot_drivers(pc1_drivers, "X-Axis (PC1)"), width='stretch')
                with col_d2:
                    st.plotly_chart(plot_drivers(pc2_drivers, "Y-Axis (PC2)"), width='stretch')

                # 4. Cluster Purity & Mapping
                st.write("### 🧩 Cluster Purity (Ground Truth Mapping)")
                if 'archetype' in df_clustered.columns:
                    purity_df = pd.crosstab(
                        df_clustered['cluster_id'],
                        df_clustered['archetype'],
                        normalize='index'
                    ) * 100
                    st.caption("Percentage of each Archetype present within the machine-discovered Clusters:")
                    st.dataframe(
                        purity_df.style.background_gradient(axis=1, cmap='YlGnBu').format("{:.1f}%"),
                        width='stretch'
                    )

            except Exception as e:
                st.error(f"K-Means Error: {e}")
                st.info("Check if your history contains enough numeric metrics (Sentiment, Rigidity, etc.)")

            st.divider()

        with sub_tab_hdbscan:
            st.write("### 🌌 HDBSCAN Density Clustering")

            # 1. Setup Parameters
            col_h1, col_h2 = st.columns(2)
            with col_h1:
                min_size = st.number_input("Min Cluster Size", 2, 50, 5, key="hdb_min_size")
            with col_h2:
                min_samples = st.number_input("Min Samples (Noise control)", 1, 20, 1, key="hdb_min_samples")

            # 2. Extract and Scale
            numeric_data = df.select_dtypes(include=[np.number])
            clean_numeric = numeric_data.dropna(axis=1, how='all').fillna(0)

            if clean_numeric.shape[0] > min_size:
                scaled_data = StandardScaler().fit_transform(clean_numeric)

                # 3. HDBSCAN call with MST generation enabled
                clusterer = hdbscan.HDBSCAN(
                    min_cluster_size=min_size,
                    min_samples=min_samples,
                    cluster_selection_method='eom',
                    prediction_data=True,
                    gen_min_span_tree=True  # Required for MST plotting
                )
                hdb_labels = clusterer.fit_predict(scaled_data)

                # 4. Create Tabs for different views
                plot_tab1, plot_tab2 = st.tabs(["Clustering Scatter", "Minimum Spanning Tree"])

                with plot_tab1:
                    df_hdb = df_clustered.copy()
                    df_hdb['cluster_id'] = hdb_labels
                    df_hdb['Cluster Name'] = df_hdb['cluster_id'].apply(
                        lambda x: "Noise" if x == -1 else f"Cluster {x}")

                    fig_hdb = px.scatter(
                        df_hdb, x='x', y='y',
                        color='Cluster Name',
                        symbol='student',
                        title="HDBSCAN: Density-Based Groups",
                        hover_data=['archetype', 'bias'],
                        color_discrete_map={'Noise': '#7f8c8d'},
                        template="plotly_dark"
                    )
                    st.plotly_chart(fig_hdb, width='stretch')

                with plot_tab2:
                    st.write(
                        "**Minimum Spanning Tree (MST) & Path Analysis**")

                    # --- 1. Coloring Option ---
                    mst_color_mode = st.selectbox(
                        "Color MST Nodes by:",
                        ["Default (Density)", "Student Model", "Archetype"],
                        help="Identify if specific models or archetypes form isolated branches."
                    )

                    fig_mst, ax_mst = plt.subplots(figsize=(12, 8))
                    fig_mst.patch.set_facecolor('#0e1117')
                    ax_mst.set_facecolor('#0e1117')

                    # Base MST Plot
                    if len(df) > 32:
                        clusterer.minimum_spanning_tree_.plot(
                            axis=ax_mst, node_size=0, edge_alpha=0.4,
                            edge_cmap='viridis', edge_linewidth=1.5, vary_line_width=True
                        )
                    else:
                        st.warning("Dataset too small for MST projection (need >32 samples).")

                    # --- 2. Custom Node Overlay for "Model Fingerprint" ---
                    # We overlay the scatter points on top of the MST lines
                    mst_data = clusterer.minimum_spanning_tree_.to_pandas()
                    # Note: MST uses internal indexing, so we align with our scaled_data

                    color_map_cols = {
                        "Student Model": "student",
                        "Archetype": "archetype"
                    }

                    if mst_color_mode != "Default (Density)":
                        target_col = color_map_cols[mst_color_mode]
                        # Generate color mapping for categories
                        unique_vals = df_hdb[target_col].unique()
                        colors = plt.cm.get_cmap('tab10', len(unique_vals))

                        for i, val in enumerate(unique_vals):
                            idx = df_hdb[df_hdb[target_col] == val].index
                            # We use the PCA 'x' and 'y' coordinates for visual consistency
                            ax_mst.scatter(
                                df_hdb.loc[idx, 'x'], df_hdb.loc[idx, 'y'],
                                label=val, s=30, alpha=0.8, edgecolors='white', linewidth=0.5
                            )
                        ax_mst.legend(facecolor='#0e1117', labelcolor='white')
                    else:
                        # Re-plot default nodes if no category selected
                        ax_mst.scatter(df_hdb['x'], df_hdb['y'], c='cyan', s=10, alpha=0.3)

                    ax_mst.axis('off')

                    st.pyplot(fig_mst)

                # --- 3. Anomaly Analysis with Contrast Mode ---
                st.write("### 🚩 Anomaly Analysis: High-Distance Outliers")

                # Filter Noise points
                outlier_df = df_hdb[df_hdb['cluster_id'] == -1].copy()

                if not outlier_df.empty:
                    # 1. Selection for Contrast Mode
                    c_col1, c_col2 = st.columns([1, 2])
                    with c_col1:
                        use_contrast = st.toggle("Enable Contrast Mode", help="Compare outliers to archetype averages")

                    # Identify numeric metrics for comparison (excluding coordinates)
                    metric_cols = [c for c in clean_numeric.columns if c not in ['x', 'y', 'cluster_id']]

                    if use_contrast:
                        # Calculate Benchmarks (Global means per archetype)
                        benchmarks = df_clustered.groupby('archetype')[metric_cols].mean()

                        # Select a specific outlier to inspect
                        selected_idx = st.selectbox(
                            "Select Outlier to Contrast:",
                            outlier_df.index,
                            format_func=lambda
                                x: f"ID: {x} | {outlier_df.loc[x, 'student']} | {outlier_df.loc[x, 'archetype']}"
                        )

                        target_row = outlier_df.loc[selected_idx]
                        target_psych = target_row['archetype']

                        # 2. Build Comparison Table
                        st.write(f"**Contrast: Outlier vs. {target_psych} Average**")

                        comparison_data = []
                        for m in metric_cols:
                            actual = target_row[m]
                            ref = benchmarks.loc[target_psych, m]
                            diff = actual - ref
                            comparison_data.append({
                                "Metric": m,
                                "Outlier Value": round(actual, 3),
                                "Archetype Avg": round(ref, 3),
                                "Delta": round(diff, 3),
                                "Deviation %": round((diff / ref * 100), 1) if ref != 0 else 0
                            })

                        comp_df = pd.DataFrame(comparison_data).set_index("Metric")

                        # Style the Delta column: Red for positive (higher than avg), Blue for negative
                        st.dataframe(
                            comp_df.style.background_gradient(subset=['Delta'], cmap='RdBu_r'),
                            width='stretch'
                        )

                    # 3. General Outlier Feed
                    st.write("**Full Outlier Datafeed:**")
                    display_cols = ['student', 'archetype', 'bias', 'val', 'v_ok', 'output']
                    # st.dataframe(
                    #     outlier_df[display_cols].style.background_gradient(subset=['v_ok'], cmap='RdYlGn'),
                    #     width='stretch',
                    #     height=300
                    # )
                    st.dataframe(
                        outlier_df[['student', 'archetype', 'step', 'output', 'v_ok']].astype(object),
                        width='stretch'
                    )

                    # 4. Distribution Chart
                    st.bar_chart(outlier_df['student'].value_counts())

                else:
                    st.success("Zero anomalies detected!")

                # 5. Metrics
                noise_count = len(df_hdb[df_hdb['cluster_id'] == -1])
                total = len(df_hdb)
                st.metric("Outliers (Noise Identified)", noise_count,
                          delta=f"{(noise_count / total * 100):.1f}% of total", delta_color="inverse")
            else:
                st.warning("Increase the number of data points to perform density clustering.")

        with sub_tab_hdbscan_UMAP:
            st.write("### 🌌 Advanced Density Clustering (UMAP + HDBSCAN)")
            st.info("High-precision latent space analysis with automated noise filtering.")

            # --- 1. DATA PRE-FILTERING ---
            with st.expander("🛠️ Data Pre-filtering & Cleaning", expanded=False):
                col_f1, col_f2 = st.columns(2)
                with col_f1:
                    min_len = st.number_input("Min Output Length", 0, 500, 20,
                                              help="Filters out very short or empty responses.")
                    filter_vok = st.toggle("Exclude v_ok == 0", value=True,
                                           help="Removes samples flagged as technically invalid.")
                with col_f2:
                    remove_json = st.toggle("Filter Raw JSON", value=True,
                                            help="Removes artifacts starting with {'text':")
                    exclude_keyword = st.text_input("Exclude by keyword", "",
                                                    help="Removes rows containing specific strings.")

            # --- 2. ADVANCED OPTIONS ---
            with st.expander("⚙️ Clustering Engine Configuration", expanded=False):
                col_h1, col_h2, col_h3 = st.columns(3)
                with col_h1:
                    st.markdown("**Density (HDBSCAN)**")
                    min_size = st.number_input("Min Cluster Size", 2, 50, 5, key="umap_v3_msize")
                    min_samples = st.number_input("Min Samples", 1, 20, 1, key="umap_v3_msamp")
                with col_h2:
                    st.markdown("**Projection (UMAP)**")
                    n_neighbors = st.slider("Neighbors", 2, 50, 15, key="umap_v3_neigh")
                    min_dist = st.slider("Min Distance", 0.0, 0.5, 0.1, 0.05, key="umap_v3_dist")
                with col_h3:
                    st.markdown("**Visuals**")
                    mst_color_mode = st.selectbox(
                        "Color Nodes By:",
                        ["Default (Density)", "Student Model", "Archetype"],
                        key="umap_v3_color"
                    )

            # --- 3. DATA PROCESSING ---
            df_clean = df.copy()
            if filter_vok and 'v_ok' in df_clean.columns:
                df_clean = df_clean[df_clean['v_ok'] != 0]
            if 'output' in df_clean.columns:
                df_clean = df_clean[df_clean['output'].astype(str).str.len() > min_len]
                if remove_json:
                    df_clean = df_clean[~df_clean['output'].astype(str).str.contains(r'^\{"text":', na=False)]
                if exclude_keyword:
                    df_clean = df_clean[
                        ~df_clean['output'].astype(str).str.contains(exclude_keyword, na=False, case=False)]

            numeric_data = df_clean.select_dtypes(include=[np.number])
            features = [c for c in numeric_data.columns if c not in ['x', 'y', 'cluster_id', 'v_ok_numeric']]
            clean_numeric = numeric_data[features].dropna(axis=1, how='all').fillna(0)

            if clean_numeric.shape[0] > min_size:
                try:
                    from umap import UMAP
                    from sklearn.preprocessing import StandardScaler

                    scaled_data = StandardScaler().fit_transform(clean_numeric)
                    reducer = UMAP(n_neighbors=n_neighbors, min_dist=min_dist, n_components=2, random_state=42)
                    umap_embedding = reducer.fit_transform(scaled_data)

                    clusterer = hdbscan.HDBSCAN(min_cluster_size=min_size, min_samples=min_samples,
                                                gen_min_span_tree=True)
                    hdb_labels = clusterer.fit_predict(umap_embedding)

                    df_hdb = df_clean.copy()
                    df_hdb['x_umap'], df_hdb['y_umap'] = umap_embedding[:, 0], umap_embedding[:, 1]
                    df_hdb['cluster_id'] = hdb_labels
                    df_hdb['Cluster Name'] = df_hdb['cluster_id'].apply(
                        lambda x: "Noise" if x == -1 else f"Cluster {x}")

                    # --- 4. VISUALIZATION EXPANDER ---
                    with st.expander("📊 Latent Space & Path Analysis (MST)", expanded=True):
                        v_tab1, v_tab2 = st.tabs(["Scatter Map", "Minimum Spanning Tree"])
                        with v_tab1:
                            color_col = "Cluster Name" if mst_color_mode == "Default (Density)" else (
                                "student" if mst_color_mode == "Student Model" else "archetype"
                            )
                            fig = px.scatter(df_hdb, x='x_umap', y='y_umap', color=color_col, symbol='student',
                                             hover_data=['archetype', 'bias', 'step', 'output'],
                                             template="plotly_dark", title="UMAP Space")
                            st.plotly_chart(fig, width='stretch')

                        with v_tab2:
                            #

                            fig_mst, ax_mst = plt.subplots(figsize=(12, 8))
                            fig_mst.patch.set_facecolor('#0e1117')
                            ax_mst.set_facecolor('#0e1117')
                            if len(df):
                                clusterer.minimum_spanning_tree_.plot(axis=ax_mst, node_size=0, edge_alpha=0.4,
                                                                      edge_cmap='viridis', edge_linewidth=1.5,
                                                                      vary_line_width=True)
                            else:
                                st.warning("Dataset too small for MST projection (need >32 samples).")

                            target_col = "student" if mst_color_mode == "Student Model" else "archetype"
                            if mst_color_mode != "Default (Density)" and target_col in df_hdb.columns:
                                for val in df_hdb[target_col].unique():
                                    m = df_hdb[target_col] == val
                                    ax_mst.scatter(df_hdb.loc[m, 'x_umap'], df_hdb.loc[m, 'y_umap'], label=val, s=45,
                                                   edgecolors='white', linewidth=0.6, zorder=3)
                                ax_mst.legend(facecolor='#0e1117', labelcolor='white')
                            else:
                                # Create a mask for outliers identified by HDBSCAN (labeled as -1)
                                # These are points that don't fit well into any specific archetype cluster
                                m_noise = df_hdb[target_col] == -1

                                # Plot noise as small, semi-transparent gray dots to keep focus on main clusters
                                # This prevents 'hallucinations' or 'random' generations from skewing the visualization
                                ax_mst.scatter(
                                    df_hdb.loc[m_noise, 'x_umap'],
                                    df_hdb.loc[m_noise, 'y_umap'],
                                    c='gray', s=10, alpha=0.3, label='Noise'
                                )
                            ax_mst.axis('off')
                            st.pyplot(fig_mst)

                    # --- MODEL FIT INDICES ---
                    st.write("### 📐 Model Fit Indices (Confirmatory Analysis)")
                    fit_col1, fit_col2, fit_col3 = st.columns(3)
                    try:
                        from sklearn.metrics import silhouette_score, davies_bouldin_score, adjusted_rand_score

                        sil_score = silhouette_score(scaled_data, hdb_labels) if len(set(hdb_labels)) > 1 else 0
                        dbi_score = davies_bouldin_score(scaled_data, hdb_labels) if len(set(hdb_labels)) > 1 else 99
                        ari_score = adjusted_rand_score(df_hdb['archetype'], hdb_labels)

                        fit_col1.metric("CFI (Silhouette)", f"{sil_score:.3f}",
                                        delta="Good" if sil_score > 0.4 else "Weak")
                        fit_col2.metric("RMSEA (DBI)", f"{dbi_score:.3f}",
                                        delta="Valid" if dbi_score < 1.5 else "Noisy", delta_color="inverse")
                        fit_col3.metric("Label Alignment (ARI)", f"{ari_score:.3f}")
                    except:
                        pass

                    # --- 5. ANOMALY ANALYSIS ---
                    outlier_df = df_hdb[df_hdb['cluster_id'] == -1].copy()
                    if not outlier_df.empty:
                        with st.expander(f"🚩 Behavioral Anomaly Analysis ({len(outlier_df)} Outliers)", expanded=False):
                            use_contrast = st.toggle("Enable Contrast Mode", key="v3_contrast_toggle")

                            with st.expander(f"🔍 Summary: {len(outlier_df)} non-standard responses", expanded=True):
                                col_a1, col_a2 = st.columns([1, 2])
                                with col_a1:
                                    st.metric("Outlier Rate", f"{(len(outlier_df) / len(df_hdb) * 100):.1f}%", )
                                    st.bar_chart(outlier_df['student'].value_counts())
                                with col_a2:
                                    selected_id = st.selectbox("Select Outlier to Inspect:", outlier_df.index,
                                                               key="v3_anom_sel")
                                    target_row = outlier_df.loc[selected_id]
                                    if use_contrast:
                                        benchmarks = df_hdb[df_hdb['archetype'] == target_row['archetype']][
                                            features].median()
                                        comp = [{"Metric": m, "Outlier": round(target_row[m], 3),
                                                 "Median": round(benchmarks[m], 3),
                                                 "Delta": round(target_row[m] - benchmarks[m], 3)} for m in features]
                                        st.table(pd.DataFrame(comp).set_index("Metric").T)
                                    else:
                                        st.write(
                                            f"**Persona:** {target_row['archetype']} | **Model:** {target_row['student']}")
                                        st.info(f"**Output:** {target_row['output']}")
                            ##############
                            with st.expander("📋 Full Outlier Datafeed", expanded=False):
                                st.dataframe(
                                    outlier_df[['student', 'archetype', 'step', 'output', 'v_ok']].astype(object),
                                    width='stretch')
                    else:
                        st.success("✅ No anomalies found.")

                except Exception as e:
                    st.error(f"Processing Error: {e}")
            else:
                st.warning("Insufficient data points after filtering.")

        with sub_tab_hdbscan_UMAP_old:
            st.write("### 🌌 Advanced Density Clustering (UMAP + HDBSCAN)")
            st.info(
                "UMAP helps separate 'collapsed' data, highlighting the unique behavioral fingerprint of each model.")

            # --- 1. SETUP PARAMETERS ---
            # Unique keys used to prevent StreamlitDuplicateElementKey errors
            col_h1, col_h2, col_h3 = st.columns(3)
            with col_h1:
                min_size = st.number_input("Min Cluster Size", 2, 50, 5, key="umap_hdb_min_size_old")
                min_samples = st.number_input("Min Samples (Noise)", 1, 20, 1, key="umap_hdb_min_samples_old")
            with col_h2:
                st.write("**UMAP Projection**")
                n_neighbors = st.slider("Neighbors (Local vs Global)", 2, 50, 15,
                                        key="umap_n_neighbors_old",
                                        help="Lower = focus on model differences. Higher = focus on global structure.")
                min_dist = st.slider("Min Distance", 0.0, 0.5, 0.1, 0.05,
                                     key="umap_min_dist_old",
                                     help="Packing density of points.")
            with col_h3:
                mst_color_mode = st.selectbox(
                    "Color MST Nodes by:",
                    ["Default (Density)", "Student Model", "Archetype"],
                    key="umap_mst_color_mode_old"
                )

            # --- 2. DATA PROCESSING ---
            # Extracting numeric metrics from the main DataFrame
            numeric_data = df.select_dtypes(include=[np.number])
            features = [c for c in numeric_data.columns if c not in ['x', 'y', 'cluster_id']]
            clean_numeric = numeric_data[features].dropna(axis=1, how='all').fillna(0)

            if clean_numeric.shape[0] > min_size:
                try:
                    from umap import UMAP
                    from sklearn.preprocessing import StandardScaler

                    # Step A: Standardization
                    scaled_data = StandardScaler().fit_transform(clean_numeric)

                    # Step B: UMAP Dimensionality Reduction
                    reducer = UMAP(
                        n_neighbors=n_neighbors,
                        min_dist=min_dist,
                        n_components=2,
                        random_state=42
                    )
                    umap_embedding = reducer.fit_transform(scaled_data)

                    # Step C: HDBSCAN Clustering on UMAP latent space
                    clusterer = hdbscan.HDBSCAN(
                        min_cluster_size=min_size,
                        min_samples=min_samples,
                        prediction_data=True,
                        gen_min_span_tree=True
                    )
                    hdb_labels = clusterer.fit_predict(umap_embedding)

                    # Creating a visualization copy to avoid modifying the main df
                    df_hdb = df.copy()
                    df_hdb['x_umap'] = umap_embedding[:, 0]
                    df_hdb['y_umap'] = umap_embedding[:, 1]
                    df_hdb['cluster_id'] = hdb_labels
                    df_hdb['Cluster Name'] = df_hdb['cluster_id'].apply(
                        lambda x: "Noise (Anomaly)" if x == -1 else f"Cluster {x}"
                    )

                    # --- 3. VISUALIZATION TABS ---
                    plot_tab1, plot_tab2 = st.tabs(["Clustering Scatter", "Minimum Spanning Tree"])

                    with plot_tab1:
                        # Selecting color column based on UI selection
                        color_col = "Cluster Name"
                        if mst_color_mode == "Student Model":
                            color_col = "student"
                        elif mst_color_mode == "Archetype":
                            color_col = "archetype"

                        fig_hdb = px.scatter(
                            df_hdb, x='x_umap', y='y_umap',
                            color=color_col,
                            symbol='student' if 'student' in df_hdb.columns else None,
                            title="UMAP + HDBSCAN: Latent Space Distribution",
                            hover_data=['archetype', 'bias', 'val'] if 'archetype' in df_hdb.columns else None,
                            template="plotly_dark",
                            color_discrete_sequence=px.colors.qualitative.Vivid
                        )
                        st.plotly_chart(fig_hdb, width='stretch')

                    with plot_tab2:
                        st.write("**Minimum Spanning Tree (Path Analysis)**")

                        fig_mst, ax_mst = plt.subplots(figsize=(12, 8))
                        fig_mst.patch.set_facecolor('#0e1117')
                        ax_mst.set_facecolor('#0e1117')

                        # Plotting MST edges
                        if len(df) > 32:
                            clusterer.minimum_spanning_tree_.plot(
                                axis=ax_mst, node_size=0, edge_alpha=0.4,
                                edge_cmap='viridis', edge_linewidth=1.5, vary_line_width=True
                            )
                        else:
                            st.warning("Dataset too small for MST projection (need >32 samples).")
                        # Overlaying colored nodes
                        if mst_color_mode != "Default (Density)":
                            target_col = "student" if mst_color_mode == "Student Model" else "archetype"
                            if target_col in df_hdb.columns:
                                unique_vals = df_hdb[target_col].unique()
                                for val in unique_vals:
                                    mask = df_hdb[target_col] == val
                                    ax_mst.scatter(
                                        df_hdb.loc[mask, 'x_umap'], df_hdb.loc[mask, 'y_umap'],
                                        label=val, s=40, alpha=0.9, edgecolors='white', linewidth=0.5
                                    )
                                ax_mst.legend(facecolor='#0e1117', labelcolor='white')
                        else:
                            ax_mst.scatter(df_hdb['x_umap'], df_hdb['y_umap'], c='cyan', s=15, alpha=0.5)

                        ax_mst.axis('off')
                        st.pyplot(fig_mst)

                    # --- 4. ANOMALY ANALYSIS ---
                    st.divider()
                    outlier_df = df_hdb[df_hdb['cluster_id'] == -1].copy()

                    if not outlier_df.empty:
                        st.subheader("🚩 Behavioral Anomaly Analysis")
                        st.write(f"Detected **{len(outlier_df)}** responses that do not fit into any standard cluster.")

                        col_anom1, col_anom2 = st.columns([1, 2])
                        with col_anom1:
                            # Anomaly rate metric
                            total_pts = len(df_hdb)
                            st.metric("Outlier Rate", f"{(len(outlier_df) / total_pts * 100):.1f}%",
                                      help="A high rate might suggest too strict 'Min Cluster Size' parameters.")

                            st.write("**Outliers by Model:**")
                            st.bar_chart(outlier_df['student'].value_counts())

                        with col_anom2:
                            st.write("**Detailed Anomaly Inspector:**")
                            selected_id = st.selectbox(
                                "Select Outlier ID to contrast:",
                                outlier_df.index,
                                format_func=lambda
                                    x: f"ID: {x} | {outlier_df.loc[x, 'student']} | {outlier_df.loc[x, 'archetype']}"
                            )

                            # Compare anomaly against archetype median
                            target_row = outlier_df.loc[selected_id]
                            target_psych = target_row['archetype']

                            metrics_to_compare = [c for c in clean_numeric.columns if c not in ['x', 'y', 'cluster_id']]
                            benchmarks = df_hdb[df_hdb['archetype'] == target_psych][metrics_to_compare].median()

                            diff_data = []
                            for m in metrics_to_compare:
                                val = target_row[m]
                                ref = benchmarks[m]
                                diff_data.append({
                                    "Metric": m,
                                    "Outlier Val": round(val, 3),
                                    "Typical Val": round(ref, 3),
                                    "Delta": round(val - ref, 3)
                                })

                            st.table(pd.DataFrame(diff_data).set_index("Metric").T)

                        # Full datafeed for inspection
                        st.write("**Full Outlier Datafeed:**")
                        display_cols = ['student', 'archetype', 'bias', 'val', 'v_ok', 'output']
                        st.dataframe(
                            outlier_df[display_cols].style.background_gradient(subset=['v_ok'], cmap='RdYlGn'),
                            width='stretch',
                            height=400
                        )
                    else:
                        st.success("✅ No anomalies detected. All model responses reside within dense clusters.")

                except Exception as e:
                    st.error(f"Analysis Error: {e}")
                    st.code(e)
            else:
                st.warning("Insufficient data for HDBSCAN. Please add more records.")

# ============================================================
# 🧬 MODEL EVALUATION
# ============================================================

with tab_model_evo:
    st.subheader("🧬 Model evaluation")

    if df is None or df.empty:
        st.info(
            "No experiment data found. "
            "Run a generation first or upload data set."
        )

    else:

        st.markdown(
            """
            Evaluate how well your linguistic / neuro metrics
            predict a target label such as:
            - hallucination
            - truthful output
            - anomaly
            - archetype
            """
        )

        # ----------------------------------------------------
        # LABEL COLUMN
        # ----------------------------------------------------
        possible_targets = [
            col for col in df.columns
            if (
                    2 <= df[col].nunique() <= 10
                    and df[col].dtype != "float64"
            )
        ]

        if not possible_targets:
            st.warning(
                "No suitable target column found.\n\n"
                "You need a label column like:\n"
                "- label\n"
                "- hallucination\n"
                "- is_valid\n"
                "- archetype"
            )

        else:

            target_column = st.selectbox(
                "🎯 Select Target Column",
                possible_targets,
                index=0
            )

            test_size = st.slider(
                "📦 Test Size",
                min_value=0.1,
                max_value=0.5,
                value=0.2,
                step=0.05
            )

            # ------------------------------------------------
            # RUN EVALUATION
            # ------------------------------------------------
            if st.button("🚀 Run Evaluation"):

                try:



                    evaluator = ModelEvaluation(
                        target_column=target_column
                    )

                    results = evaluator.evaluate(
                        df,
                        test_size=test_size
                    )

                    # ========================================
                    # METRICS
                    # ========================================
                    st.markdown("### 📊 Evaluation Metrics")

                    c1, c2, c3, c4 = st.columns(4)

                    c1.metric(
                        "Precision",
                        results["precision"]
                    )

                    c2.metric(
                        "Recall",
                        results["recall"]
                    )

                    c3.metric(
                        "F1 Score",
                        results["f1_score"]
                    )

                    c4.metric(
                        "ROC-AUC",
                        results["roc_auc"]
                    )

                    # ========================================
                    # CONFUSION MATRIX
                    # ========================================
                    st.markdown("### 🔀 Confusion Matrix")

                    cm = results["confusion_matrix"]

                    n_classes = len(cm)

                    cm_df = pd.DataFrame(
                        cm,
                        columns=[f"Pred {i}" for i in range(n_classes)],
                        index=[f"True {i}" for i in range(n_classes)]
                    )

                    st.write("Classes detected:", list(range(n_classes)))

                    st.dataframe(cm_df, width='stretch')

                    fig = px.imshow(
                        cm,
                        text_auto=True,
                        title="Confusion Matrix Heatmap"
                    )

                    st.plotly_chart(fig, width='stretch')
                    # ========================================
                    # CLASSIFICATION REPORT
                    # ========================================
                    st.markdown("### 📑 Classification Report")

                    st.code(
                        results["classification_report"],
                        language="text"
                    )

                    # ========================================
                    # TOP FEATURES
                    # ========================================
                    st.markdown("### 🧠 Top Predictive Features")

                    feature_df = pd.DataFrame(
                        results["top_features"]
                    )

                    st.dataframe(
                        feature_df,
                        width='stretch'
                    )

                    # ========================================
                    # BAR CHART
                    # ========================================
                    if not feature_df.empty:
                        fig = px.bar(
                            feature_df.head(10),
                            x="feature",
                            y="abs_weight",
                            title="Feature Importance"
                        )

                        st.plotly_chart(
                            fig,
                            width='stretch'
                        )

                except Exception as e:
                    st.exception(e)

# ============================================================
# Benchmark
# ============================================================
with tab_benchmark:
    st.header("📑 LLM Benchmark Report")

    if df is None or df.empty:
        st.info("No experiment data found. Run a generation first or upload data set.")
    else:

        # --- 1. IMPROVED DATA CLEANUP (Logic Alignment) ---
        df_clean = df.copy()

        # Apply standard filters to match the Clustering Tab
        # 1. Remove obvious technical failures (word_count 0)
        df_clean = df_clean[df_clean["word_count"] > 0]
        # 2. Filter by validation flag if available
        if 'v_ok' in df_clean.columns:
            # We keep only 'v_ok == 1' for the "clean" benchmark,
            # but the success rate chart will use the full df to show failures.
            df_valid = df_clean[df_clean["v_ok"] == 1]
        else:
            df_valid = df_clean.copy()

        # 3. Deduplication (Text + Model fingerprint)
        df_valid = df_valid.drop_duplicates(subset=["output", "student", "teacher"])

        # --- 2. DATASET OVERVIEW ---
        st.subheader("📊 Dataset Overview")
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total Samples", len(df))
        col2.metric("Valid Samples", len(df_valid))
        col3.metric("Unique Students", df_valid["student"].nunique())
        col4.metric("Unique Teachers", df_valid["teacher"].nunique())

        # --- 3. SUCCESS RATE (Uses full clean df to include failures) ---
        st.subheader("✅ Validation Success Rate")
        success_df = (
            df_clean.groupby("student")["v_ok_numeric"]
            .mean()
            .sort_values(ascending=False)
            .reset_index()
        )
        fig_success = px.bar(
            success_df, x="student", y="v_ok_numeric",
            title="Pass Rate (%) by Model (v_ok_numeric)",
            labels={'v_ok_numeric': 'Success Probability', 'student': 'Model Name'},
            template="plotly_dark",
            color="v_ok_numeric",
            color_continuous_scale="RdYlGn"
        )
        st.plotly_chart(fig_success, width='stretch')

        # --- 4. PERFORMANCE (Inference Speed) ---
        st.subheader("⚡ Performance Metrics")
        perf_df = (
            df_valid.groupby("student")[["ms_per_word", "duration_ms"]]
            .mean()
            .reset_index()
        )
        fig_perf = px.bar(
            perf_df, x="student", y="ms_per_word",
            title="Inference Speed (Lower is Better)",
            labels={'ms_per_word': 'Latency (ms/word)'},
            template="plotly_dark"
        )
        st.plotly_chart(fig_perf, width='stretch')

        # --- 5. QUALITY HEATMAP ---
        st.subheader("💎 Quality Metrics Heatmap")
        quality_cols = [
            "coherence", "cognitive_load", "lexical_density",
            "semantic_overlap", "expansion_ratio"
        ]
        # Ensure columns exist before plotting
        existing_quality = [c for c in quality_cols if c in df_valid.columns]
        if existing_quality:
            quality_df = df_valid.groupby("student")[existing_quality].mean().reset_index()
            fig_quality = px.imshow(
                quality_df.set_index("student"),
                text_auto=".3f",
                title="Avg Quality Scores per Model",
                color_continuous_scale="Viridis",
                template="plotly_dark"
            )
            st.plotly_chart(fig_quality, width='stretch')

        # --- 6. PSYCHOLINGUISTIC SIGNATURE ---
        st.subheader("🧠 Psycholinguistic signature")
        psycho_cols = [
            "self_focus", "modality", "cognitive_density",
            "abstract_ratio", "repetition_score"
        ]
        existing_psy = [c for c in psycho_cols if c in df_valid.columns]
        if existing_psy:
            psycho_df = df_valid.groupby("student")[existing_psy].mean().reset_index()
            fig_psy = px.bar(
                psycho_df, x="student", y=existing_psy,
                barmode="group",
                title="Linguistic Trait Distribution",
                template="plotly_dark"
            )
            st.plotly_chart(fig_psy, width='stretch')

        # --- 7. WEIGHTED LEADERBOARD ---
        st.subheader("🏆 Model Leaderboard")
        lb_metrics = {
            "v_ok_numeric": "mean",
            "coherence": "mean",
            "cognitive_load": "mean",
            "ms_per_word": "mean"
        }
        # --- Leaderboard score ---
        leaderboard = df_valid.groupby("student").agg({
            "v_ok_numeric": "mean",
            "coherence": "mean",
            "semantic_overlap": "mean",  # NEW: How well it mimics the teacher
            "ms_per_word": "mean"
        }).reset_index()

        # Calculate 'Persona Precision' (Higher is better)
        leaderboard["mimicry_score"] = leaderboard["semantic_overlap"] * 100

        # Normalized Speed Score (Inverse of ms_per_word)
        max_ms = leaderboard["ms_per_word"].max()
        leaderboard["speed_score"] = (max_ms - leaderboard["ms_per_word"]) / max_ms

        # Calculated Weighted Final Score
        # Logic: 30% Success, 30% Mimicry, 20% Logic, 20% Speed
        leaderboard["final_score"] = (
                leaderboard["v_ok_numeric"] * 0.3 +
                leaderboard["mimicry_score"] * 0.3 +
                leaderboard["coherence"] * 0.2 +
                leaderboard["speed_score"] * 0.2
        )

        leaderboard = leaderboard.sort_values("final_score", ascending=False).reset_index(drop=True)
        st.dataframe(
            leaderboard.astype(object).style.background_gradient(subset=["final_score"], cmap="Greens"),
            width='stretch'
        )

        # --- 8. AUTO INTERPRETATION ---
        if not leaderboard.empty:
            best_model = leaderboard.iloc[0]["student"]
            st.markdown(f"""
            ### 🥇 Champion: **{best_model}**
    
            **Behavioral Insights:**
            - **Stability:** Top validation success rate ensures high instruction following.
            - **Linguistic Depth:** Balanced cognitive load scores suggest nuanced persona emulation.
            - **Inference Optimization:** Demonstrates a superior words-per-second ratio.
    
            **Strategic Interpretation:** 
            This model is the most recommended for **{best_model}** persona replication within the current context-aware sweep.
            """)

# ============================================================
# Monitor
# ============================================================
with tab_monitor:
    st.subheader("🖥️ Ollama Management")

    # ============================================================
    # Pull Model
    # ============================================================
    st.markdown("##### Pull Model")
    with st.expander("📦 Model list", expanded=False):

        model_df = pd.DataFrame([
            {"Model": "gemma2:2b", "Size (GB)": 1.6},
            {"Model": "phi3:mini", "Size (GB)": 2.2},
            {"Model": "llama3.2:3b", "Size (GB)": 2.0},
            {"Model": "qwen2.5:3b", "Size (GB)": 2.1},
            {"Model": "tinyllama:latest", "Size (GB)": 0.7},
            {"Model": "all-MiniLM", "Size (GB)": 0.05},
            {"Model": "stablelm2:1.6b", "Size (GB)": 1.0},
            {"Model": "deepseek-r1:1.5b", "Size (GB)": 1.1},
            {"Model": "mistral:7b-instruct-q4_K_M", "Size (GB)": 4.1},
            {"Model": "llama3:8b-instruct-q4_K_M", "Size (GB)": 4.7},
            {"Model": "qwen2.5:7b-instruct-q4_K_M", "Size (GB)": 4.4},
        ])

        st.dataframe(
            model_df,
            width='stretch',
            hide_index=True
        )

        st.caption(
            "Q4 quantized models usually fit into ~4GB VRAM with partial CPU offloading."
        )

    pull_col1, pull_col2 = st.columns([8, 1])

    with pull_col1:
        model_to_pull = st.text_input(
            label="Pull Model",
            placeholder="e.g. llama3:latest",
            label_visibility="collapsed",
            key="model_to_pull"
        )

    with pull_col2:
        pull_clicked = st.button("🚀 Pull", width='stretch')

    # ============================================================
    # START PULL
    # ============================================================
    if pull_clicked:

        if model_to_pull.strip():

            try:
                cmd = ["ollama", "pull", model_to_pull.strip()]

                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )

                st.session_state.pull_running = True
                st.session_state.pull_model_name = model_to_pull.strip()
                st.session_state.pull_pid = process.pid

                st.toast(f"Started pulling {model_to_pull}")

                st.rerun()

            except Exception as e:
                st.error(f"Pull failed: {e}")

        else:
            st.warning("Enter model name")

    # ============================================================
    # LIVE STATUS PANEL
    # ============================================================
    if st.session_state.pull_running:

        current_model = st.session_state.pull_model_name

        st.info(f"📥 Pulling: {current_model}")

        # fake animated progress
        progress_placeholder = st.empty()

        if "pull_progress" not in st.session_state:
            st.session_state.pull_progress = 0

        st.session_state.pull_progress = min(
            st.session_state.pull_progress + 3,
            95
        )

        progress_placeholder.progress(
            st.session_state.pull_progress,
            text=f"Downloading {current_model} ..."
        )
        # ========================================================
        # Buttons
        # ========================================================
        col_stop1, col_stop2 = st.columns([1, 4])

        with col_stop1:

            if st.button("🛑 Cancel Pull"):

                try:

                    pid = st.session_state.pull_pid

                    if pid:

                        if os.name == "nt":
                            subprocess.call(
                                ["taskkill", "/F", "/PID", str(pid)]
                            )
                        else:
                            subprocess.call(
                                ["kill", "-9", str(pid)]
                            )

                    st.session_state.pull_running = False
                    st.session_state.pull_pid = None
                    st.session_state.pull_model_name = ""

                    st.warning("Pull cancelled")
                    st.session_state.pull_progress = 0
                    st.rerun()

                except Exception as e:
                    st.error(str(e))

        with col_stop2:
            st.caption(
                "Large models may take several minutes depending on internet speed."
            )

        # ========================================================
        # CHECK INSTALL COMPLETE
        # ========================================================
        try:

            installed_models = [
                m.model for m in ollama.list().models
            ]

            if any(current_model.lower() in m.lower() for m in installed_models):
                st.session_state.pull_running = False
                st.session_state.pull_pid = None
                st.session_state.pull_model_name = ""
                st.session_state.pull_progress = 100

                progress_placeholder.progress(
                    100,
                    text=f"{current_model} installed"
                )

                st.success(f"✅ {current_model} installed successfully")

                time.sleep(1)

                st.session_state.pull_progress = 0

                st.rerun()

        except:
            pass
        # ========================================================
        # AUTO REFRESH
        # ========================================================
        time.sleep(2)
        st.rerun()

    # ============================================================
    # Installed Models
    # ============================================================

    try:
        models = ollama.list().models

        if not models:
            st.info("No local models installed")

        for m in models:
            col1, col2, col3 = st.columns([6, 2, 1.5])

            with col1:
                st.write(f"**{m.model}**")

            with col2:
                st.write(f"💾 {m.size / 1e9:.2f} GB")

            with col3:
                if st.checkbox("🗑️", key=f"check_{m.model}"):
                    if st.button("Confirm Delete?", key=f"del_{m.model}", type="primary"):
                        ollama.delete(m.model)
                        st.rerun()

    except Exception as e:
        st.warning(f"Ollama connection error: {e}")

# ============================================================
# Debug << tab presence depends on the SHOW_DEBUG_TAB flag
# ============================================================
if SHOW_DEBUG_TAB:
    with tab_debug:
        st.write("### Session State Explorer")
        st.json(st.session_state.to_dict())

    if st.session_state.history:
        # 1. Flatten the JSON
        df = pd.json_normalize(st.session_state.history)

        # 2. FORCE conversion to standard Python objects
        for col in df.columns:
            if df[col].dtype.name in ['string', 'object', 'category']:
                # Fill NaNs first, then convert to basic object type
                df[col] = df[col].fillna("").astype(object)
            elif df[col].dtype.name == 'boolean':
                df[col] = df[col].astype(object)

        # 3. Final safety check: if Arrow still complains, use a copy
        df_display = df.copy()

    with st.expander("Schema check"):
        # width='stretch' is the modern replacement for width='stretch'
        st.dataframe(df_display, width='stretch')
        st.subheader("Current Data Schema")
        st.write(df.dtypes)

# ============================================================
# FAQ
# ============================================================
with tab_faq:
    st.subheader("📚 User Guide & Metric Methodology")
    faq_lang = st.segmented_control("Select Language", options=["English", "Українська"], default="English")

    # 1. Get the absolute path to the directory containing streamlit_app.py
    current_dir = os.path.dirname(os.path.abspath(__file__))

    # 2. Determine filename and build the full absolute path
    faq_filename = "faq_eng.md" if faq_lang == "English" else "faq_ua.md"
    faq_path = os.path.join(current_dir, faq_filename)

    # 3. Check for existence using the absolute path
    if os.path.exists(faq_path):
        with open(faq_path, "r", encoding="utf-8") as f:
            st.markdown(f.read())
    else:
        # Display the full path attempted to help with debugging
        st.error(f"❌ File not found at: {faq_path}")
