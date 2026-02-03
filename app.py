import json
from datetime import datetime
from typing import List, Optional
from uuid import uuid4

# PERF FIX: Pandas lazy-loaded inside functions that need it (saves 25+ seconds on startup)
# import pandas as pd - MOVED TO FUNCTION SCOPE

import streamlit as st
import streamlit.components.v1 as components

from modules.auth import validate_login
from modules.gs1_client import parse_scan
from modules.reports import (
    export_csv,
    export_excel,
    export_excel_single,
    export_excel_with_metadata,
    export_pdf,
    export_pdf_report,
    to_dataframe,
)
from modules.settings import DEFAULT_SETTINGS, load_settings, save_settings
from modules.storage import (
    create_audit,
    create_line,
    create_session,
    delete_line,
    find_duplicates,
    find_serial_duplicates,
    get_session,
    init_db,
    list_audit,
    list_lines,
    list_sessions,
    update_line,
    update_session,
)
from modules.utils import expiry_status, normalize_sfda, safe_get

st.set_page_config(page_title="Pharmacy Inventory / Stock Count", layout="wide")

# PERF FIX: init_db() moved to after login (saves 7s on login page load!)
# init_db() - NOW CALLED IN main() AFTER LOGIN


def _now_local() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _ensure_session_state():
    if "user" not in st.session_state:
        st.session_state.user = None
    if "session_id" not in st.session_state:
        st.session_state.session_id = None
    if "last_parsed" not in st.session_state:
        st.session_state.last_parsed = None
    if "duplicate_pending" not in st.session_state:
        st.session_state.duplicate_pending = None
    if "read_only" not in st.session_state:
        st.session_state.read_only = False


def _inject_global_styles() -> None:
    st.markdown(
        """
        <style>
        :root {
            --primary: #1B6EF3;
            --success: #0F9D58;
            --warning: #F4B400;
            --error: #DB4437;
            --info: #1A73E8;
            --bg: #F7F8FB;
            --surface: #FFFFFF;
            --text: #1F2937;
            --muted: #6B7280;
            --border: #E5E7EB;
        }
        .section-title {
            font-size: 18px;
            font-weight: 600;
            margin: 8px 0 12px 0;
            color: var(--text);
        }
        .card {
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 16px;
            box-shadow: 0 1px 2px rgba(0,0,0,0.04);
        }
        .card-grid {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 8px 16px;
        }
        .label {
            color: var(--muted);
            font-size: 12px;
            text-transform: uppercase;
            letter-spacing: 0.4px;
        }
        .value {
            font-size: 14px;
            color: var(--text);
        }
        .badge {
            display: inline-block;
            padding: 2px 8px;
            border-radius: 999px;
            font-size: 12px;
            font-weight: 600;
        }
        .badge-valid { background: #E8F5EE; color: #0F9D58; }
        .badge-near { background: #FFF7E0; color: #B26A00; }
        .badge-expired { background: #FDEAEA; color: #B3261E; }
        .badge-unknown { background: #EEF2F7; color: #4B5563; }
        .action-bar {
            display: flex;
            gap: 8px;
            align-items: center;
            margin-top: 8px;
        }
        .stButton button {
            border-radius: 10px !important;
            padding: 6px 12px !important;
            font-weight: 600 !important;
        }
        .btn-primary button {
            background: var(--primary) !important;
            color: #FFFFFF !important;
            border: 1px solid var(--primary) !important;
        }
        .btn-danger button {
            background: var(--error) !important;
            color: #FFFFFF !important;
            border: 1px solid var(--error) !important;
        }
        .btn-secondary button {
            background: #EEF2FF !important;
            color: #1E3A8A !important;
            border: 1px solid #C7D2FE !important;
        }
        .scan-input input {
            font-size: 18px !important;
            padding: 10px 12px !important;
            border-radius: 10px !important;
            border: 2px solid #C7D2FE !important;
        }
        .scan-input input:focus {
            border-color: var(--primary) !important;
            box-shadow: 0 0 0 3px rgba(27,110,243,0.15) !important;
        }
        @media (max-width: 900px) {
            .card-grid {
                grid-template-columns: 1fr;
            }
            .table-toolbar {
                flex-direction: column;
                align-items: stretch;
            }
        }
        .kpi-card {
            border-radius: 12px;
            padding: 12px 14px;
            border: 1px solid var(--border);
            background: var(--surface);
        }
        .kpi-label {
            font-size: 12px;
            color: var(--muted);
            text-transform: uppercase;
            letter-spacing: 0.4px;
        }
        .kpi-value {
            font-size: 20px;
            font-weight: 700;
            margin-top: 4px;
            color: var(--text);
        }
        .kpi-success { border-left: 4px solid var(--success); }
        .kpi-warning { border-left: 4px solid var(--warning); }
        .kpi-error { border-left: 4px solid var(--error); }
        .kpi-info { border-left: 4px solid var(--info); }
        .table-toolbar {
            display: flex;
            flex-wrap: wrap;
            gap: 8px 12px;
            align-items: center;
            margin: 6px 0 12px 0;
        }
        .table-toolbar > div {
            min-width: 160px;
        }
        .table-wrap {
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 8px;
            background: var(--surface);
        }
        .export-toolbar {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            align-items: center;
        }
        [data-testid="stSidebar"] {
            background: #0F172A;
            border-right: 1px solid #E5E7EB;
        }
        [data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3 {
            color: #E2E8F0;
        }
        [data-testid="stSidebar"] .stRadio label, [data-testid="stSidebar"] .stSelectbox label {
            color: #CBD5E1 !important;
            font-weight: 600;
        }
        [data-testid="stSidebar"] .stSelectbox div,
        [data-testid="stSidebar"] .stRadio div[role="radiogroup"] {
            background: #111827;
            border-radius: 10px;
            padding: 6px 8px;
        }
        [data-testid="stSidebar"] button {
            background: #1B6EF3;
            color: #FFFFFF;
            border-radius: 10px;
            border: 1px solid #1B6EF3;
        }
        [data-testid="stSidebar"] .stSelectbox,
        [data-testid="stSidebar"] .stRadio,
        [data-testid="stSidebar"] .stTextInput,
        [data-testid="stSidebar"] .stButton {
            margin-bottom: 12px;
        }
        [data-testid="stSidebar"] .stSidebarContent {
            padding-top: 16px;
        }
        [data-testid="stSidebar"] hr {
            border: none;
            border-top: 1px solid #1F2937;
            margin: 14px 0;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_status_badge(status: str) -> str:
    if status == "Valid":
        cls = "badge-valid"
    elif status == "Near Expiry":
        cls = "badge-near"
    elif status == "Expired":
        cls = "badge-expired"
    else:
        cls = "badge-unknown"
    return f'<span class="badge {cls}">{status}</span>'


def _render_kpi(label: str, value: str, tone: str = "info") -> str:
    return (
        f'<div class="kpi-card kpi-{tone}">'
        f'<div class="kpi-label">{label}</div>'
        f'<div class="kpi-value">{value}</div>'
        f"</div>"
    )


def _table_controls(
    df,  # pd.DataFrame - pandas imported locally
    *,
    key: str,
    default_sort: str,
    status_options: Optional[List[str]] = None,
):
    col_search, col_status, col_sort, col_order, col_page = st.columns([2, 1.2, 1.4, 1, 1])
    search_text = col_search.text_input("Search", key=f"{key}_search")
    if status_options:
        status_filter = col_status.multiselect("Status", status_options, key=f"{key}_status")
    else:
        status_filter = []

    df_view = df.copy()
    if search_text:
        mask = df_view.apply(
            lambda col: col.astype(str).str.contains(search_text, case=False, na=False)
        )
        df_view = df_view[mask.any(axis=1)]
    if status_filter and "status" in df_view.columns:
        df_view = df_view[df_view["status"].isin(status_filter)]

    sort_cols = [default_sort] + [c for c in df_view.columns if c != default_sort]
    sort_col = col_sort.selectbox("Sort by", sort_cols, key=f"{key}_sort")
    sort_dir = col_order.selectbox("Order", ["Descending", "Ascending"], key=f"{key}_order")
    if not df_view.empty and sort_col in df_view.columns:
        df_view = df_view.sort_values(sort_col, ascending=(sort_dir == "Ascending"))

    page_size = col_page.selectbox("Page size", [25, 50, 100], index=0, key=f"{key}_pagesize")
    total_rows = len(df_view)
    total_pages = max(1, (total_rows + page_size - 1) // page_size)
    page = st.number_input("Page", min_value=1, max_value=total_pages, value=1, step=1, key=f"{key}_page")
    start = (page - 1) * page_size
    end = start + page_size
    return df_view.iloc[start:end]


def _apply_display_mode(settings: dict) -> None:
    if settings.get("display_mode") != "Dark":
        return
    st.markdown(
        """
        <style>
        :root, body, [data-testid="stAppViewContainer"] {
            background-color: #0f1115 !important;
            color: #e6e6e6 !important;
        }
        [data-testid="stSidebar"] {
            background-color: #141821 !important;
        }
        [data-testid="stSidebar"] {
            border-right: 1px solid #2A3244 !important;
        }
        .stButton button, .stTextInput input, .stTextArea textarea, .stSelectbox div {
            color: #e6e6e6 !important;
            background-color: #1c2230 !important;
            border-color: #2a3244 !important;
        }
        .card, .table-wrap, .kpi-card {
            background: #151A24 !important;
            border-color: #2A3244 !important;
        }
        .section-title, .value {
            color: #E6E6E6 !important;
        }
        .label {
            color: #9AA3B2 !important;
        }
        .badge-valid { background: #103D2B !important; color: #7AE2B8 !important; }
        .badge-near { background: #3F2F0B !important; color: #F7D37A !important; }
        .badge-expired { background: #3A1412 !important; color: #F5A39C !important; }
        .badge-unknown { background: #273042 !important; color: #B6C2D9 !important; }
        [data-testid="stDataFrame"] {
            background: #151A24 !important;
        }
        [data-testid="stDataFrame"] table {
            color: #E6E6E6 !important;
        }
        [data-testid="stDataFrame"] thead th {
            background: #1C2230 !important;
            color: #E6E6E6 !important;
        }
        [data-testid="stDataFrame"] tbody tr:nth-child(odd) {
            background: #141A26 !important;
        }
        [data-testid="stDataFrame"] tbody tr:nth-child(even) {
            background: #151F2B !important;
        }
        [data-testid="stDataEditor"] {
            background: #151A24 !important;
        }
        [data-testid="stDataEditor"] table {
            color: #E6E6E6 !important;
        }
        [data-testid="stDataEditor"] thead th {
            background: #1C2230 !important;
            color: #E6E6E6 !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _status_badge(status: str) -> str:
    if status == "Valid":
        return "✅ Valid"
    if status == "Near Expiry":
        return "⚠️ Near Expiry"
    if status == "Expired":
        return "❌ Expired"
    if status == "Unknown":
        return "❔ Unknown"
    return f"⚠️ {status}"


def _line_status(parsed: dict, settings: dict) -> str:
    expiry = parsed.get("Expiry Date", "")
    if not parsed.get("Trade Name"):
        return "Unknown"
    return expiry_status(expiry, settings["near_expiry_months"])


def _require_login():
    if st.session_state.user:
        return True
    st.title("Login")
    with st.form("login_form", clear_on_submit=False):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Login")
    if submitted:
        if validate_login(username, password):
            st.session_state.user = username
            create_audit(username, "login_success")
            st.success("Logged in")
            st.rerun()
        else:
            create_audit(username or "unknown", "login_failure")
            st.error("Invalid credentials")
    return False


def _session_header(session: dict):
    cols = st.columns([2, 2, 2, 2, 2, 1])
    cols[0].metric("Counter", session.get("counter_name", ""))
    cols[1].metric("Location", session.get("location", ""))
    cols[2].metric("Session ID", session.get("session_id", ""))
    cols[3].metric("Start Time", session.get("start_datetime", ""))
    cols[4].metric("Status", session.get("status", ""))
    if cols[5].button("Logout"):
        st.session_state.user = None
        st.session_state.session_id = None
        st.rerun()

    is_admin = st.session_state.user == "admin"
    is_finalized = session.get("status") == "Finalized"
    if is_finalized and not is_admin:
        st.info("This session is finalized and read-only for non-admin users.")
    if is_finalized or is_admin:
        if st.button("New Session"):
            st.session_state.session_id = None
            st.session_state.read_only = False
            st.rerun()
    elif not is_admin:
        st.info("Finalize the session to start a new one.")


def _select_or_restore_session():
    sessions = list_sessions()
    if not sessions:
        return None
    session_map = {
        f"{s['session_name'] or 'Session'} | {s['session_id']} | {s['status']}": s["session_id"]
        for s in sessions
    }
    selection = st.sidebar.selectbox("Open Session", ["--"] + list(session_map.keys()))
    if selection != "--":
        st.session_state.session_id = session_map[selection]
        update_session(st.session_state.session_id, {"last_opened": _now_local()})
        session = get_session(st.session_state.session_id)
        st.session_state.read_only = bool(session and session.get("status") == "Finalized" and st.session_state.user != "admin")


def _build_line_data(parsed: dict, count: float, count_unit: str, settings: dict) -> dict:
    sfda = parsed.get("SFDA Code")
    status = _line_status(parsed, settings)
    return {
        "session_id": st.session_state.session_id,
        "scan_timestamp": _now_local(),
        "scanned_by": st.session_state.user,
        "gtin": safe_get(parsed, "GTIN"),
        "trade_name": safe_get(parsed, "Trade Name"),
        "scientific_name": safe_get(parsed, "Scientific Name"),
        "batch_lot": safe_get(parsed, "BATCH/LOT"),
        "expiry_date": safe_get(parsed, "Expiry Date"),
        "serial": safe_get(parsed, "SERIAL"),
        "on_hand_count": float(count),
        "count_unit": count_unit,
        "unit_type": safe_get(parsed, "UNIT_TYPE"),
        "granular_unit": safe_get(parsed, "GRANULAR_UNIT"),
        "dosage_form": safe_get(parsed, "DOSAGE_FORM"),
        "strength": safe_get(parsed, "STRENGTH"),
        "roa": safe_get(parsed, "ROA"),
        "package_type": safe_get(parsed, "PACKAGE_TYPE"),
        "package_size": safe_get(parsed, "PACKAGE_SIZE"),
        "category": safe_get(parsed, "CATEGORY"),
        "price": parsed.get("PRICE"),
        "sfda_code": normalize_sfda(sfda),
        "status": status,
        "notes": "",
    }


def _render_scan_card(parsed: dict, settings: dict):
    if not parsed:
        return
    expiry = parsed.get("Expiry Date", "")
    status = expiry_status(expiry, settings["near_expiry_months"])
    unknown_gtin = not parsed.get("Trade Name")
    sfda_codes = parsed.get("SFDA Code")
    sfda_display = normalize_sfda(sfda_codes)

    st.markdown("### Scan Result")
    st.markdown(
        f"""
        <div class="card">
            <div style="font-size:20px;font-weight:700;">{safe_get(parsed, "Trade Name") or "Unknown GTIN"}</div>
            <div style="color:var(--muted);margin-bottom:8px;">{safe_get(parsed, "Scientific Name")}</div>
            <div class="card-grid">
                <div><div class="label">GTIN</div><div class="value">{safe_get(parsed, "GTIN")}</div></div>
                <div><div class="label">Expiry</div><div class="value">{expiry} {_render_status_badge(status)}</div></div>
                <div><div class="label">Batch/Lot</div><div class="value">{safe_get(parsed, "BATCH/LOT")}</div></div>
                <div><div class="label">Serial</div><div class="value">{safe_get(parsed, "SERIAL")}</div></div>
                <div><div class="label">Strength</div><div class="value">{safe_get(parsed, "STRENGTH")}</div></div>
                <div><div class="label">Dosage Form</div><div class="value">{safe_get(parsed, "DOSAGE_FORM")}</div></div>
                <div><div class="label">Unit Type</div><div class="value">{safe_get(parsed, "UNIT_TYPE")} ({safe_get(parsed, "GRANULAR_UNIT")})</div></div>
                <div><div class="label">Package</div><div class="value">{safe_get(parsed, "PACKAGE_TYPE")} {safe_get(parsed, "PACKAGE_SIZE")}</div></div>
                <div><div class="label">ROA</div><div class="value">{safe_get(parsed, "ROA")}</div></div>
                <div><div class="label">Price</div><div class="value">{safe_get(parsed, "PRICE")}</div></div>
                <div><div class="label">SFDA Code</div><div class="value">{sfda_display}</div></div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    gtin_value = safe_get(parsed, "GTIN")
    if gtin_value:
        st.markdown('<div class="action-bar">', unsafe_allow_html=True)
        st.markdown('<div class="btn-secondary">', unsafe_allow_html=True)
        if st.button("Copy GTIN"):
            components.html(
                f"""
                <script>
                navigator.clipboard.writeText("{gtin_value}");
                </script>
                """,
                height=0,
            )
            st.success("GTIN copied.")
        st.markdown("</div>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

    if isinstance(sfda_codes, list) and len(sfda_codes) > 1:
        with st.expander("Show all SFDA codes"):
            st.write(sfda_codes)

    if unknown_gtin:
        st.warning("Unknown GTIN - no lookup data found.")
        col1, col2 = st.columns(2)
        temp_name = col1.text_input("Trade Name", key="quick_add_trade_name")
        temp_scientific = col2.text_input("Scientific Name", key="quick_add_scientific")
        col3, col4 = st.columns(2)
        temp_strength = col3.text_input("Strength", key="quick_add_strength")
        temp_dosage = col4.text_input("Dosage Form", key="quick_add_dosage")
        if temp_name:
            parsed["Trade Name"] = temp_name
        if temp_scientific:
            parsed["Scientific Name"] = temp_scientific
        if temp_strength:
            parsed["STRENGTH"] = temp_strength
        if temp_dosage:
            parsed["DOSAGE_FORM"] = temp_dosage


def _scan_and_count(settings: dict):
    st.header("Scan & Count")

    if not st.session_state.session_id:
        st.info("Create or select a session first.")
        return

    session = get_session(st.session_state.session_id)
    if not session:
        st.error("Session not found.")
        return

    is_admin = st.session_state.user == "admin"
    if session.get("status") == "Finalized" and not is_admin:
        st.warning("Session is finalized. Scanning is disabled.")
        return
    if session.get("status") == "Finalized" and is_admin:
        st.warning("Session is finalized. Admin override enabled.")

    if settings.get("auto_parse_on_enter", True):
        with st.form("scan_form", clear_on_submit=True):
            st.markdown('<div class="scan-input">', unsafe_allow_html=True)
            scan_text = st.text_input(
                "Scan Input",
                placeholder="Scan barcode here",
                help="Scanner input",
                key="scan_input",
            )
            st.markdown("</div>", unsafe_allow_html=True)
            st.markdown('<div class="btn-primary">', unsafe_allow_html=True)
            submitted = st.form_submit_button("Parse (Enter)")
            st.markdown("</div>", unsafe_allow_html=True)
        if submitted:
            ok, data, err = parse_scan(scan_text)
            if ok:
                st.session_state.last_parsed = data
            else:
                st.session_state.last_parsed = None
                st.error(err)
    else:
        st.markdown('<div class="scan-input">', unsafe_allow_html=True)
        scan_text = st.text_input(
            "Scan Input",
            placeholder="Scan barcode here",
            help="Scanner input",
            key="scan_input",
        )
        st.markdown("</div>", unsafe_allow_html=True)
        st.markdown('<div class="btn-primary">', unsafe_allow_html=True)
        if st.button("Parse"):
            ok, data, err = parse_scan(scan_text)
            if ok:
                st.session_state.last_parsed = data
            else:
                st.session_state.last_parsed = None
                st.error(err)
        st.markdown("</div>", unsafe_allow_html=True)

    parsed = st.session_state.last_parsed
    _render_scan_card(parsed, settings)

    if settings.get("auto_parse_on_enter", True):
        components.html(
            """
            <script>
            const scanInput = window.parent.document.querySelector('input[aria-label="Scan Input"]');
            if (scanInput && !scanInput.dataset.enterBind) {
                scanInput.dataset.enterBind = "1";
                scanInput.addEventListener("keydown", (e) => {
                    if (e.key === "Enter") {
                        const buttons = Array.from(window.parent.document.querySelectorAll("button"));
                        const target = buttons.find(b => b.textContent.trim() === "Parse (Enter)");
                        if (target) target.click();
                    }
                });
            }
            </script>
            """,
            height=0,
        )

    if st.session_state.get("last_added"):
        st.info(f"Last Added: {st.session_state.last_added}")

    if parsed:
        count_units = [
            "BOX",
            "PACK",
            "BLISTER",
            "TABLET",
            "CAPSULE",
            "VIAL",
            "AMPOULE",
            "BOTTLE",
        ]
        default_unit = parsed.get("UNIT_TYPE") or "PACK"
        if default_unit not in count_units:
            count_units.append(default_unit)

        with st.form("count_form", clear_on_submit=True):
            st.markdown('<div class="card">', unsafe_allow_html=True)
            st.markdown('<div class="section-title">Count Input</div>', unsafe_allow_html=True)
            count = st.number_input("On-hand Count", min_value=0.0, step=1.0)
            unit = st.selectbox("Count Unit", count_units, index=count_units.index(default_unit))
            st.markdown('<div class="btn-primary">', unsafe_allow_html=True)
            add_clicked = st.form_submit_button("Add to Inventory (Enter)")
            st.markdown("</div>", unsafe_allow_html=True)
            st.markdown("</div>", unsafe_allow_html=True)

        if add_clicked:
            if count <= 0:
                st.error("Count is required.")
            else:
                pending = {
                    "parsed": parsed,
                    "count": count,
                    "unit": unit,
                }
                st.session_state.duplicate_pending = pending
                st.session_state.focus_scan = True

        components.html(
            """
            <script>
            const countInput = window.parent.document.querySelector('input[aria-label="On-hand Count"]');
            if (countInput && !countInput.dataset.enterBind) {
                countInput.dataset.enterBind = "1";
                countInput.addEventListener("keydown", (e) => {
                    if (e.key === "Enter") {
                        const buttons = Array.from(window.parent.document.querySelectorAll("button"));
                        const target = buttons.find(b => b.textContent.trim() === "Add to Inventory (Enter)");
                        if (target) target.click();
                    }
                });
            }
            </script>
            """,
            height=0,
        )

    _handle_duplicate_flow(settings)

    st.subheader("Data Quality Panel")
    _quality_panel(settings)

    st.subheader("Inventory Lines")
    _lines_table(settings, session)

    if settings.get("auto_focus_scan_input") or st.session_state.get("focus_scan"):
        components.html(
            """
            <script>
            const el = window.parent.document.querySelector('input[aria-label="Scan Input"]');
            if (el) { el.focus(); el.select(); }
            </script>
            """,
            height=0,
        )
        st.session_state.focus_scan = False


def _handle_duplicate_flow(settings: dict):
    pending = st.session_state.duplicate_pending
    if not pending:
        return

    parsed = pending["parsed"]
    line_data = _build_line_data(parsed, pending["count"], pending["unit"], settings)

    duplicates = find_duplicates(
        st.session_state.session_id,
        gtin=line_data["gtin"],
        batch_lot=line_data["batch_lot"],
        expiry_date=line_data["expiry_date"],
    )
    serial_duplicates = find_serial_duplicates(st.session_state.session_id, line_data["serial"])

    if serial_duplicates and not settings["allow_duplicate_serial_override"]:
        create_audit(
            st.session_state.user,
            "duplicate_serial_blocked",
            session_id=st.session_state.session_id,
            old_value={"serial": line_data["serial"]},
            new_value=None,
        )
        st.error("Duplicate serial detected. Add blocked (override disabled).")
        st.session_state.duplicate_pending = None
        return
    if serial_duplicates and settings["allow_duplicate_serial_override"]:
        create_audit(
            st.session_state.user,
            "override_duplicate_serial",
            session_id=st.session_state.session_id,
            old_value={"serial": line_data["serial"]},
            new_value={"override": True},
        )

    if not duplicates:
        _commit_line(line_data)
        st.session_state.duplicate_pending = None
        return

    st.warning("Duplicate detected for GTIN + Batch/Lot + Expiry.")
    default_mode = settings.get("duplicate_handling_mode", "Aggregate")
    action = st.radio(
        "Duplicate handling action",
        ["Aggregate", "New line"],
        index=0 if default_mode == "Aggregate" else 1,
        horizontal=True,
        key="duplicate_action_choice",
    )
    st.markdown('<div class="btn-primary">', unsafe_allow_html=True)
    if st.button("Apply Duplicate Action"):
        if action == "Aggregate":
            target = duplicates[0]
            new_count = float(target["on_hand_count"]) + float(line_data["on_hand_count"])
            update_line(target["line_id"], {"on_hand_count": new_count})
            create_audit(
                st.session_state.user,
                "aggregate_line",
                session_id=st.session_state.session_id,
                line_id=target["line_id"],
                old_value=target,
                new_value={"on_hand_count": new_count},
            )
            st.success("Quantity aggregated.")
        else:
            _commit_line(line_data)
        st.session_state.duplicate_pending = None
    st.markdown("</div>", unsafe_allow_html=True)


def _commit_line(line_data: dict):
    line_id = create_line(line_data)
    create_audit(
        st.session_state.user,
        "add_line",
        session_id=st.session_state.session_id,
        line_id=line_id,
        new_value=line_data,
    )
    st.success("Added to inventory.")
    st.session_state.last_added = f"{line_data.get('gtin')} | {line_data.get('trade_name')}"


def _quality_panel(settings: dict):
    lines = list_lines(st.session_state.session_id)
    total_scans = len(lines)
    unique_items = len(
        set(
            (l.get("gtin"), l.get("batch_lot"), l.get("expiry_date"))
            for l in lines
        )
    )
    near_expiry = sum(1 for l in lines if l.get("status") == "Near Expiry")
    expired = sum(1 for l in lines if l.get("status") == "Expired")
    unknown = sum(1 for l in lines if l.get("status") == "Unknown")
    dup_serial = 0
    seen_serial = set()
    for l in lines:
        serial = l.get("serial") or ""
        if serial and serial in seen_serial:
            dup_serial += 1
        seen_serial.add(serial)

    cols = st.columns(6)
    cols[0].markdown(_render_kpi("Total Scans", str(total_scans), "info"), unsafe_allow_html=True)
    cols[1].markdown(_render_kpi("Unique Items", str(unique_items), "info"), unsafe_allow_html=True)
    cols[2].markdown(_render_kpi("Near Expiry", str(near_expiry), "warning"), unsafe_allow_html=True)
    cols[3].markdown(_render_kpi("Expired", str(expired), "error"), unsafe_allow_html=True)
    cols[4].markdown(_render_kpi("Unknown GTIN", str(unknown), "info"), unsafe_allow_html=True)
    cols[5].markdown(_render_kpi("Duplicate Serials", str(dup_serial), "warning"), unsafe_allow_html=True)


def _lines_table(settings: dict, session: dict):
    # PERF: Lazy-load pandas only when needed
    import pandas as pd

    lines = list_lines(st.session_state.session_id)
    if not lines:
        st.info("No lines yet.")
        return
    is_finalized = session.get("status") == "Finalized"
    is_admin = st.session_state.user == "admin"
    allow_edit = (not is_finalized) or is_admin

    df = pd.DataFrame(lines)
    display_cols = [
        "line_id",
        "scan_timestamp",
        "scanned_by",
        "gtin",
        "trade_name",
        "scientific_name",
        "batch_lot",
        "expiry_date",
        "serial",
        "on_hand_count",
        "count_unit",
        "unit_type",
        "granular_unit",
        "dosage_form",
        "strength",
        "roa",
        "package_type",
        "package_size",
        "category",
        "price",
        "sfda_code",
        "status",
        "notes",
    ]
    df = df[display_cols]
    if "status" in df.columns:
        def _status_label(value: str) -> str:
            if value == "Valid":
                return "🟢 Valid"
            if value == "Near Expiry":
                return "🟡 Near Expiry"
            if value == "Expired":
                return "🔴 Expired"
            if value == "Unknown":
                return "⚪ Unknown"
            return str(value)

        df["status"] = df["status"].apply(_status_label)

    st.markdown("### Filters")
    col_search, col_status, col_sort, col_order, col_page = st.columns([2, 1.2, 1.4, 1, 1])
    search_text = col_search.text_input("Search", key="lines_search")
    status_options = sorted({str(l.get("status") or "") for l in lines if l.get("status")})
    status_filter = col_status.multiselect("Status", status_options, key="lines_status_filter")

    df_view = df.copy()
    if search_text:
        mask = df_view.apply(
            lambda col: col.astype(str).str.contains(search_text, case=False, na=False)
        )
        df_view = df_view[mask.any(axis=1)]
    if status_filter:
        df_view = df_view[df_view["status"].isin(status_filter)]

    sort_col = col_sort.selectbox("Sort by", ["scan_timestamp"] + [c for c in df_view.columns if c != "scan_timestamp"])
    sort_dir = col_order.selectbox("Order", ["Descending", "Ascending"])
    if not df_view.empty and sort_col in df_view.columns:
        df_view = df_view.sort_values(sort_col, ascending=(sort_dir == "Ascending"))

    page_size = col_page.selectbox("Page size", [25, 50, 100], index=0)
    total_rows = len(df_view)
    total_pages = max(1, (total_rows + page_size - 1) // page_size)
    page = st.number_input("Page", min_value=1, max_value=total_pages, value=1, step=1)
    start = (page - 1) * page_size
    end = start + page_size
    df_view = df_view.iloc[start:end]

    if is_finalized and not is_admin:
        st.info("Session is finalized. Line edits are disabled.")
    st.markdown('<div class="table-wrap">', unsafe_allow_html=True)
    edited = st.data_editor(
        df_view,
        num_rows="dynamic",
        width="stretch",
        disabled=[c for c in df_view.columns if c not in ("on_hand_count", "notes")] if allow_edit else True,
        key="lines_editor",
    )
    st.markdown("</div>", unsafe_allow_html=True)

    if allow_edit and st.button("Save Line Edits"):
        blocked = 0
        for _, row in edited.iterrows():
            line_id = row["line_id"]
            original = next((l for l in lines if l["line_id"] == line_id), None)
            if not original:
                continue
            if original.get("locked") and not is_admin:
                blocked += 1
                continue
            updates = {}
            if float(row["on_hand_count"]) != float(original["on_hand_count"]):
                updates["on_hand_count"] = float(row["on_hand_count"])
            if str(row["notes"]) != str(original.get("notes") or ""):
                updates["notes"] = row["notes"]
            if updates:
                update_line(line_id, updates)
                create_audit(
                    st.session_state.user,
                    "edit_line",
                    session_id=st.session_state.session_id,
                    line_id=line_id,
                    old_value=original,
                    new_value=updates,
                )
        st.success("Edits saved.")
        if blocked:
            st.warning(f"Skipped {blocked} locked line(s).")

    st.markdown("### Export Current View")
    st.markdown('<div class="export-toolbar">', unsafe_allow_html=True)
    st.markdown('<div class="btn-secondary">', unsafe_allow_html=True)
    if st.button("Export Current View CSV"):
        path = export_csv(df_view, f"lines_view_{st.session_state.session_id}.csv")
        st.success(f"Saved: {path}")
    st.markdown("</div>", unsafe_allow_html=True)
    st.markdown('<div class="btn-secondary">', unsafe_allow_html=True)
    if st.button("Export Current View Excel"):
        meta = {
            "Session ID": st.session_state.session_id,
            "Export Type": "Inventory Lines View",
            "Generated At": _now_local(),
            "Generated By": st.session_state.user,
        }
        path = export_excel_with_metadata(df_view, pd.DataFrame(), pd.DataFrame(), meta, f"lines_view_{st.session_state.session_id}.xlsx")
        st.success(f"Saved: {path}")
    st.markdown("</div>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

    delete_ids = st.multiselect("Delete lines", df_view["line_id"].tolist()) if allow_edit else []
    if allow_edit:
        st.markdown('<div class="btn-danger">', unsafe_allow_html=True)
        delete_clicked = st.button("Delete Selected")
        st.markdown("</div>", unsafe_allow_html=True)
    else:
        delete_clicked = False
    if allow_edit and delete_clicked:
        blocked = 0
        for line_id in delete_ids:
            original = next((l for l in lines if l["line_id"] == line_id), None)
            if original and original.get("locked") and not is_admin:
                blocked += 1
                continue
            delete_line(line_id)
            create_audit(
                st.session_state.user,
                "delete_line",
                session_id=st.session_state.session_id,
                line_id=line_id,
                old_value=original,
            )
        st.success("Deleted selected lines.")
        if blocked:
            st.warning(f"Skipped {blocked} locked line(s).")


def _review_page(settings: dict):
    # PERF: Lazy-load pandas only when needed
    import pandas as pd

    st.header("Review & Reconcile")
    if not st.session_state.session_id:
        st.info("Create or select a session first.")
        return
    session = get_session(st.session_state.session_id)
    if not session:
        st.error("Session not found.")
        return
    is_finalized = session.get("status") == "Finalized"
    is_admin = st.session_state.user == "admin"
    lines = list_lines(st.session_state.session_id)
    if not lines:
        st.info("No lines to review.")
        return
    df = pd.DataFrame(lines)
    group_cols = ["gtin", "batch_lot", "expiry_date"]
    summary = (
        df.groupby(group_cols)
        .agg(
            trade_name=("trade_name", "first"),
            scientific_name=("scientific_name", "first"),
            strength=("strength", "first"),
            dosage_form=("dosage_form", "first"),
            unit_type=("unit_type", "first"),
            package_size=("package_size", "first"),
            total_count=("on_hand_count", "sum"),
            count_unit=("count_unit", "first"),
            sfda_code=("sfda_code", "first"),
            status=("status", "first"),
        )
        .reset_index()
    )
    kpi_cols = st.columns(4)
    kpi_cols[0].markdown(_render_kpi("Total Lines", str(len(df)), "info"), unsafe_allow_html=True)
    kpi_cols[1].markdown(_render_kpi("Unique Items", str(len(summary)), "info"), unsafe_allow_html=True)
    kpi_cols[2].markdown(_render_kpi("Near Expiry", str((df["status"] == "Near Expiry").sum()), "warning"), unsafe_allow_html=True)
    kpi_cols[3].markdown(_render_kpi("Expired", str((df["status"] == "Expired").sum()), "error"), unsafe_allow_html=True)
    st.subheader("Aggregated View")
    summary_view = _table_controls(summary, key="review_summary", default_sort="gtin")
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.dataframe(summary_view, width="stretch")
    st.markdown("</div>", unsafe_allow_html=True)

    st.subheader("Detailed View")
    detailed_view = _table_controls(
        df,
        key="review_detailed",
        default_sort="scan_timestamp",
        status_options=sorted(df["status"].dropna().unique().tolist()) if "status" in df else None,
    )
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.dataframe(detailed_view, width="stretch")
    st.markdown("</div>", unsafe_allow_html=True)

    st.subheader("Warnings")
    warnings = df[df["status"].isin(["Near Expiry", "Expired", "Unknown"])]
    warnings_view = _table_controls(
        warnings,
        key="review_warnings",
        default_sort="scan_timestamp",
        status_options=["Near Expiry", "Expired", "Unknown"],
    )
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.dataframe(warnings_view, width="stretch")
    st.markdown("</div>", unsafe_allow_html=True)

    st.subheader("Exports (Current Views)")
    st.markdown('<div class="export-toolbar">', unsafe_allow_html=True)
    col1, col2, col3, col4 = st.columns(4)
    st.markdown('<div class="btn-secondary">', unsafe_allow_html=True)
    if col1.button("Export Summary CSV"):
        path = export_csv(summary_view, f"summary_view_{st.session_state.session_id}.csv")
        st.success(f"Saved: {path}")
    st.markdown("</div>", unsafe_allow_html=True)
    st.markdown('<div class="btn-secondary">', unsafe_allow_html=True)
    if col2.button("Export Detailed CSV"):
        path = export_csv(detailed_view, f"detailed_view_{st.session_state.session_id}.csv")
        st.success(f"Saved: {path}")
    st.markdown("</div>", unsafe_allow_html=True)
    st.markdown('<div class="btn-secondary">', unsafe_allow_html=True)
    if col3.button("Export Warnings CSV"):
        path = export_csv(warnings_view, f"warnings_view_{st.session_state.session_id}.csv")
        st.success(f"Saved: {path}")
    st.markdown("</div>", unsafe_allow_html=True)
    st.markdown('<div class="btn-secondary">', unsafe_allow_html=True)
    if col4.button("Export Summary Excel"):
        meta = {
            "Session ID": st.session_state.session_id,
            "Export Type": "Review Summary View",
            "Generated At": _now_local(),
            "Generated By": st.session_state.user,
        }
        path = export_excel_with_metadata(summary_view, None, None, meta, f"summary_view_{st.session_state.session_id}.xlsx")
        st.success(f"Saved: {path}")
    st.markdown("</div>", unsafe_allow_html=True)
    col5, col6 = st.columns(2)
    st.markdown('<div class="btn-secondary">', unsafe_allow_html=True)
    if col5.button("Export Detailed Excel"):
        meta = {
            "Session ID": st.session_state.session_id,
            "Export Type": "Review Detailed View",
            "Generated At": _now_local(),
            "Generated By": st.session_state.user,
        }
        path = export_excel_with_metadata(detailed_view, None, None, meta, f"detailed_view_{st.session_state.session_id}.xlsx")
        st.success(f"Saved: {path}")
    st.markdown("</div>", unsafe_allow_html=True)
    st.markdown('<div class="btn-secondary">', unsafe_allow_html=True)
    if col6.button("Export Warnings Excel"):
        meta = {
            "Session ID": st.session_state.session_id,
            "Export Type": "Review Warnings View",
            "Generated At": _now_local(),
            "Generated By": st.session_state.user,
        }
        path = export_excel_with_metadata(warnings_view, None, None, meta, f"warnings_view_{st.session_state.session_id}.xlsx")
        st.success(f"Saved: {path}")
    st.markdown("</div>", unsafe_allow_html=True)
    col7, col8, col9 = st.columns(3)
    st.markdown('<div class="btn-secondary">', unsafe_allow_html=True)
    if col7.button("Export Summary PDF"):
        path = export_pdf("Review Summary", summary_view, f"summary_view_{st.session_state.session_id}.pdf")
        st.success(f"Saved: {path}")
    st.markdown("</div>", unsafe_allow_html=True)
    st.markdown('<div class="btn-secondary">', unsafe_allow_html=True)
    if col8.button("Export Detailed PDF"):
        path = export_pdf("Review Detailed", detailed_view, f"detailed_view_{st.session_state.session_id}.pdf")
        st.success(f"Saved: {path}")
    st.markdown("</div>", unsafe_allow_html=True)
    st.markdown('<div class="btn-secondary">', unsafe_allow_html=True)
    if col9.button("Export Warnings PDF"):
        path = export_pdf("Review Warnings", warnings_view, f"warnings_view_{st.session_state.session_id}.pdf")
        st.success(f"Saved: {path}")
    st.markdown("</div>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

    st.subheader("Bulk Edit (Optional)")
    if st.session_state.read_only and st.session_state.user != "admin":
        st.info("Read-only mode: bulk edit disabled.")
    else:
        bulk_ids = st.multiselect("Select lines for bulk edit", df["line_id"].tolist())
        if bulk_ids:
            col1, col2, col3 = st.columns(3)
            bulk_status = col1.selectbox(
                "Set Status",
                ["--", "Valid", "Near Expiry", "Expired", "Unknown"],
                index=0,
            )
            bulk_notes = col2.text_input("Append Note")
            bulk_lock = col3.selectbox("Lock Lines", ["--", "Lock", "Unlock"], index=0)

            st.markdown('<div class="btn-primary">', unsafe_allow_html=True)
            if st.button("Apply Bulk Edit"):
                for line_id in bulk_ids:
                    original = next((l for l in lines if l["line_id"] == line_id), None)
                    if not original:
                        continue
                    updates = {}
                    if bulk_status != "--":
                        updates["status"] = bulk_status
                    if bulk_notes:
                        existing = original.get("notes") or ""
                        updates["notes"] = (existing + " " + bulk_notes).strip()
                    if bulk_lock == "Lock":
                        updates["locked"] = True
                    if bulk_lock == "Unlock":
                        if st.session_state.user != "admin":
                            st.error("Only admin can unlock lines.")
                            continue
                        updates["locked"] = False
                    if updates:
                        update_line(line_id, updates)
                        create_audit(
                            st.session_state.user,
                            "bulk_edit_line",
                            session_id=st.session_state.session_id,
                            line_id=line_id,
                            old_value=original,
                            new_value=updates,
                        )
                st.success("Bulk edit applied.")
            st.markdown("</div>", unsafe_allow_html=True)

    st.subheader("Session Notes")
    session_notes = st.text_area(
        "Notes",
        value=session.get("notes") or "",
        height=120,
        disabled=is_finalized and not is_admin,
    )
    if st.button("Save Session Notes", disabled=is_finalized and not is_admin):
        update_session(st.session_state.session_id, {"notes": session_notes})
        create_audit(
            st.session_state.user,
            "update_session_notes",
            session_id=st.session_state.session_id,
            old_value={"notes": session.get("notes")},
            new_value={"notes": session_notes},
        )
        st.success("Session notes saved.")
    if is_finalized and not is_admin:
        st.info("Session is finalized. Notes are read-only for non-admin users.")

    st.subheader("Lock Lines (Optional)")
    line_map = {f"{l['line_id']} | {l.get('gtin','') or ''}": l for l in lines}
    selection = st.multiselect("Select lines", list(line_map.keys()))
    if selection:
        lock_ids = [line_map[s]["line_id"] for s in selection]
        cols = st.columns(2)
        if cols[0].button("Lock Selected", disabled=is_finalized and not is_admin):
            for line_id in lock_ids:
                update_line(line_id, {"locked": True})
                create_audit(
                    st.session_state.user,
                    "lock_line",
                    session_id=st.session_state.session_id,
                    line_id=line_id,
                    new_value={"locked": True},
                )
            st.success("Lines locked.")
        if cols[1].button("Unlock Selected"):
            if not is_admin:
                st.error("Only admin can unlock lines.")
            else:
                for line_id in lock_ids:
                    update_line(line_id, {"locked": False})
                    create_audit(
                        st.session_state.user,
                        "unlock_line",
                        session_id=st.session_state.session_id,
                        line_id=line_id,
                        new_value={"locked": False},
                    )
                st.success("Lines unlocked.")


def _finalize_page():
    # PERF: Lazy-load pandas only when needed
    import pandas as pd

    st.header("Finalize & Reports")
    if not st.session_state.session_id:
        st.info("Create or select a session first.")
        return
    session = get_session(st.session_state.session_id)
    if not session:
        st.error("Session not found.")
        return

    if session.get("status") != "Finalized":
        st.markdown('<div class="btn-danger">', unsafe_allow_html=True)
        if st.button("Finalize / Lock Session"):
            update_session(st.session_state.session_id, {"status": "Finalized"})
            create_audit(st.session_state.user, "finalize_session", session_id=st.session_state.session_id)
            st.success("Session finalized.")
            st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

    lines = list_lines(st.session_state.session_id)
    if not lines:
        st.info("No lines to report.")
        return
    df = pd.DataFrame(lines)
    group_cols = ["gtin", "batch_lot", "expiry_date"]
    summary = (
        df.groupby(group_cols)
        .agg(
            trade_name=("trade_name", "first"),
            scientific_name=("scientific_name", "first"),
            strength=("strength", "first"),
            dosage_form=("dosage_form", "first"),
            unit_type=("unit_type", "first"),
            package_size=("package_size", "first"),
            total_count=("on_hand_count", "sum"),
            count_unit=("count_unit", "first"),
            sfda_code=("sfda_code", "first"),
            status=("status", "first"),
        )
        .reset_index()
    )

    warnings = df[df["status"].isin(["Near Expiry", "Expired", "Unknown"])]
    kpi_cols = st.columns(4)
    kpi_cols[0].markdown(_render_kpi("Total Lines", str(len(df)), "info"), unsafe_allow_html=True)
    kpi_cols[1].markdown(_render_kpi("Unique Items", str(len(summary)), "info"), unsafe_allow_html=True)
    kpi_cols[2].markdown(_render_kpi("Warnings", str(len(warnings)), "warning"), unsafe_allow_html=True)
    kpi_cols[3].markdown(_render_kpi("Unknown GTIN", str((df["status"] == "Unknown").sum()), "info"), unsafe_allow_html=True)

    st.subheader("Warnings")
    warnings_view = _table_controls(
        warnings,
        key="finalize_warnings",
        default_sort="scan_timestamp",
        status_options=["Near Expiry", "Expired", "Unknown"],
    )
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.dataframe(warnings_view, width="stretch")
    st.markdown("</div>", unsafe_allow_html=True)

    st.subheader("Exports")
    detailed_df = df.copy()
    summary_df = summary.copy()
    warnings_df = warnings.copy()
    metadata = {
        "Session ID": session.get("session_id", ""),
        "Session Name": session.get("session_name", ""),
        "Location": session.get("location", ""),
        "Counter Name": session.get("counter_name", ""),
        "Generated At": _now_local(),
        "Generated By": st.session_state.user,
        "Status": session.get("status", ""),
    }
    kpis = {
        "Total Unique Items": str(len(summary_df)),
        "Total Lines": str(len(detailed_df)),
        "Total Quantity": str(float(detailed_df["on_hand_count"].sum())) if not detailed_df.empty else "0",
        "Near Expiry Count": str((detailed_df["status"] == "Near Expiry").sum()) if "status" in detailed_df else "0",
        "Expired Count": str((detailed_df["status"] == "Expired").sum()) if "status" in detailed_df else "0",
        "Unknown GTIN Count": str((detailed_df["status"] == "Unknown").sum()) if "status" in detailed_df else "0",
    }

    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">Export Options</div>', unsafe_allow_html=True)
    st.markdown('<div class="export-toolbar">', unsafe_allow_html=True)
    col1, col2, col3, col4 = st.columns(4)
    st.markdown('<div class="btn-secondary">', unsafe_allow_html=True)
    if col1.button("Export CSV"):
        path = export_csv(detailed_df, f"detailed_{st.session_state.session_id}.csv")
        st.success(f"Saved: {path}")
    st.markdown("</div>", unsafe_allow_html=True)
    st.markdown('<div class="btn-secondary">', unsafe_allow_html=True)
    if col2.button("Export Excel"):
        path = export_excel_with_metadata(
            detailed_df,
            summary_df,
            warnings_df,
            metadata,
            f"report_{st.session_state.session_id}.xlsx",
        )
        st.success(f"Saved: {path}")
    st.markdown("</div>", unsafe_allow_html=True)
    st.markdown('<div class="btn-secondary">', unsafe_allow_html=True)
    if col3.button("Export PDF (Detailed)"):
        path = export_pdf_report(
            "Inventory Stock Count Report",
            detailed_df,
            summary_df,
            warnings_df,
            metadata,
            kpis,
            f"report_{st.session_state.session_id}.pdf",
        )
        st.success(f"Saved: {path}")
    st.markdown("</div>", unsafe_allow_html=True)
    st.markdown('<div class="btn-secondary">', unsafe_allow_html=True)
    if col4.button("Export PDF (Summary)"):
        path = export_pdf("Inventory Summary Report", summary_df, f"summary_{st.session_state.session_id}.pdf")
        st.success(f"Saved: {path}")
    st.markdown("</div>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)


def _audit_page():
    # PERF: Lazy-load pandas only when needed
    import pandas as pd

    st.header("Audit & Logs")
    records = list_audit(st.session_state.session_id)
    if not records:
        st.info("No audit logs yet.")
        return
    df = pd.DataFrame(records)
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">Audit Records</div>', unsafe_allow_html=True)
    audit_view = _table_controls(df, key="audit", default_sort="timestamp")
    st.dataframe(audit_view, width="stretch")

    col1, col2 = st.columns(2)
    st.markdown('<div class="btn-secondary">', unsafe_allow_html=True)
    if col1.button("Export Audit CSV"):
        path = export_csv(audit_view, f"audit_{st.session_state.session_id or 'all'}.csv")
        st.success(f"Saved: {path}")
    st.markdown("</div>", unsafe_allow_html=True)
    st.markdown('<div class="btn-secondary">', unsafe_allow_html=True)
    if col2.button("Export Audit Excel"):
        meta = {
            "Session ID": st.session_state.session_id or "all",
            "Export Type": "Audit View",
            "Generated At": _now_local(),
            "Generated By": st.session_state.user,
        }
        path = export_excel_with_metadata(audit_view, pd.DataFrame(), pd.DataFrame(), meta, f"audit_{st.session_state.session_id or 'all'}.xlsx")
        st.success(f"Saved: {path}")
    st.markdown("</div>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)


def _settings_page():
    st.header("Settings")
    if st.session_state.user != "admin":
        st.error("Admin only.")
        return

    settings = load_settings()
    current_backend = settings.get("persistence_backend", "MongoDB")
    with st.form("settings_form"):
        near_expiry_months = st.number_input("Near Expiry threshold (months)", min_value=1, step=1, value=int(settings["near_expiry_months"]))
        allow_override = st.checkbox("Allow override for duplicate serial", value=bool(settings["allow_duplicate_serial_override"]))
        duplicate_mode = st.selectbox("Default duplicate handling mode", ["Aggregate", "New line"], index=0 if settings["duplicate_handling_mode"] == "Aggregate" else 1)
        display_mode = st.selectbox("Display mode", ["Light", "Dark"], index=0 if settings["display_mode"] == "Light" else 1)
        auto_parse = st.checkbox("Auto-parse on Enter", value=bool(settings["auto_parse_on_enter"]))
        auto_focus = st.checkbox("Auto-focus on scan input", value=bool(settings["auto_focus_scan_input"]))
        persistence_backend = st.selectbox(
            "Persistence backend",
            ["MongoDB", "JSON"],
            index=0 if current_backend == "MongoDB" else 1,
        )
        data_retention = st.number_input("Data retention sessions (0 = keep all)", min_value=0, step=1, value=int(settings["data_retention_sessions"]))
        saved = st.form_submit_button("Save Settings")

    if saved:
        save_settings(
            {
                "near_expiry_months": near_expiry_months,
                "allow_duplicate_serial_override": allow_override,
                "duplicate_handling_mode": duplicate_mode,
                "display_mode": display_mode,
                "auto_parse_on_enter": auto_parse,
                "auto_focus_scan_input": auto_focus,
                "persistence_backend": persistence_backend,
                "data_retention_sessions": data_retention,
            }
        )
        st.success("Settings saved.")
        st.info("Persistence backend uses the PERSISTENCE_BACKEND environment variable; restart required.")


def _session_setup_page():
    st.header("Inventory Session Setup")
    with st.form("session_form"):
        session_name = st.text_input("Session Name (optional)")
        counter_name = st.text_input("Counter Name *")
        location = st.text_input("Location *")
        inventory_type = st.selectbox(
            "Inventory Type",
            ["Full", "Partial", "Shelf", "Department", "Supplier"],
            index=0,
        )
        device_id = st.text_input("Device ID (optional)")
        notes = st.text_area("Notes (optional)")
        submitted = st.form_submit_button("Create Session")

    if submitted:
        if not counter_name or not location:
            st.error("Counter Name and Location are required.")
            return
        session_id = create_session(
            {
                "session_name": session_name,
                "counter_name": counter_name,
                "location": location,
                "inventory_type": inventory_type,
                "device_id": device_id,
                "notes": notes,
            }
        )
        st.session_state.session_id = session_id
        create_audit(st.session_state.user, "create_session", session_id=session_id)
        st.success("Session created.")
        st.rerun()


def main():
    _ensure_session_state()
    settings = load_settings()
    _inject_global_styles()
    _apply_display_mode(settings)

    if not _require_login():
        return

    # PERF FIX: Initialize database only after successful login (saves 7s on login page!)
    if 'db_initialized' not in st.session_state:
        init_db()
        st.session_state.db_initialized = True

    st.sidebar.title("Navigation")
    _select_or_restore_session()

    page = st.sidebar.radio(
        "Go to",
        [
            "Session Setup",
            "Scan & Count",
            "Review & Reconcile",
            "Finalize & Reports",
            "Audit & Logs",
            "Settings",
        ],
    )

    if st.session_state.session_id:
        session = get_session(st.session_state.session_id)
        if session:
            _session_header(session)

    if page == "Session Setup":
        _session_setup_page()
    elif page == "Scan & Count":
        _scan_and_count(settings)
    elif page == "Review & Reconcile":
        _review_page(settings)
    elif page == "Finalize & Reports":
        _finalize_page()
    elif page == "Audit & Logs":
        _audit_page()
    elif page == "Settings":
        _settings_page()


if __name__ == "__main__":
    main()
