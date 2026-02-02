import json
from datetime import datetime
from uuid import uuid4

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from modules.auth import validate_login
from modules.gs1_client import parse_scan
from modules.reports import export_csv, export_excel, export_excel_single, export_pdf, export_pdf_report, to_dataframe
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


init_db()


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
    with st.container():
        st.markdown(
            f"""
            <div style="border:1px solid #e0e0e0;padding:16px;border-radius:12px;background:#fafafa;">
                <div style="font-size:20px;font-weight:700;">{safe_get(parsed, "Trade Name") or "Unknown GTIN"}</div>
                <div style="color:#666;margin-bottom:8px;">{safe_get(parsed, "Scientific Name")}</div>
                <div><b>GTIN:</b> {safe_get(parsed, "GTIN")}</div>
                <div><b>Expiry Date:</b> {expiry} <span>{_status_badge(status)}</span></div>
                <div><b>Batch/Lot:</b> {safe_get(parsed, "BATCH/LOT")}</div>
                <div><b>Serial:</b> {safe_get(parsed, "SERIAL")}</div>
                <div><b>Strength:</b> {safe_get(parsed, "STRENGTH")}</div>
                <div><b>Dosage Form:</b> {safe_get(parsed, "DOSAGE_FORM")}</div>
                <div><b>Unit Type:</b> {safe_get(parsed, "UNIT_TYPE")} ({safe_get(parsed, "GRANULAR_UNIT")})</div>
                <div><b>Package:</b> {safe_get(parsed, "PACKAGE_TYPE")} {safe_get(parsed, "PACKAGE_SIZE")}</div>
                <div><b>ROA:</b> {safe_get(parsed, "ROA")}</div>
                <div><b>Price:</b> {safe_get(parsed, "PRICE")}</div>
                <div><b>SFDA Code:</b> {sfda_display}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    gtin_value = safe_get(parsed, "GTIN")
    if gtin_value:
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
            scan_text = st.text_input(
                "Scan Input",
                placeholder="Scan barcode here",
                help="Scanner input",
                key="scan_input",
            )
            submitted = st.form_submit_button("Parse (Enter)")
        if submitted:
            ok, data, err = parse_scan(scan_text)
            if ok:
                st.session_state.last_parsed = data
            else:
                st.session_state.last_parsed = None
                st.error(err)
    else:
        scan_text = st.text_input(
            "Scan Input",
            placeholder="Scan barcode here",
            help="Scanner input",
            key="scan_input",
        )
        if st.button("Parse"):
            ok, data, err = parse_scan(scan_text)
            if ok:
                st.session_state.last_parsed = data
            else:
                st.session_state.last_parsed = None
                st.error(err)

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
            count = st.number_input("On-hand Count", min_value=0.0, step=1.0)
            unit = st.selectbox("Count Unit", count_units, index=count_units.index(default_unit))
            add_clicked = st.form_submit_button("Add to Inventory (Enter)")

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
    cols[0].metric("Total Scans", total_scans)
    cols[1].metric("Unique Items", unique_items)
    cols[2].metric("Near Expiry", near_expiry)
    cols[3].metric("Expired", expired)
    cols[4].metric("Unknown GTIN", unknown)
    cols[5].metric("Duplicate Serials", dup_serial)


def _lines_table(settings: dict, session: dict):
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
    search_text = st.text_input("Search lines", key="lines_search")
    status_options = sorted({str(l.get("status") or "") for l in lines if l.get("status")})
    status_filter = st.multiselect("Status filter", status_options, key="lines_status_filter")

    df_view = df.copy()
    if search_text:
        mask = df_view.apply(
            lambda col: col.astype(str).str.contains(search_text, case=False, na=False)
        )
        df_view = df_view[mask.any(axis=1)]
    if status_filter:
        df_view = df_view[df_view["status"].isin(status_filter)]

    st.markdown("### Sorting")
    sort_col = st.selectbox("Sort by", ["scan_timestamp"] + [c for c in df_view.columns if c != "scan_timestamp"])
    sort_dir = st.selectbox("Order", ["Descending", "Ascending"])
    if not df_view.empty and sort_col in df_view.columns:
        df_view = df_view.sort_values(sort_col, ascending=(sort_dir == "Ascending"))

    if is_finalized and not is_admin:
        st.info("Session is finalized. Line edits are disabled.")
    edited = st.data_editor(
        df_view,
        num_rows="dynamic",
        width="stretch",
        disabled=[c for c in df_view.columns if c not in ("on_hand_count", "notes")] if allow_edit else True,
        key="lines_editor",
    )

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
    if st.button("Export Current View CSV"):
        path = export_csv(df_view, f"lines_view_{st.session_state.session_id}.csv")
        st.success(f"Saved: {path}")
    if st.button("Export Current View Excel"):
        path = export_excel_single(df_view, f"lines_view_{st.session_state.session_id}.xlsx", sheet_name="Lines")
        st.success(f"Saved: {path}")

    delete_ids = st.multiselect("Delete lines", df_view["line_id"].tolist()) if allow_edit else []
    if allow_edit and st.button("Delete Selected"):
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
    st.subheader("Aggregated View")
    st.dataframe(summary, width="stretch")

    st.subheader("Detailed View")
    st.dataframe(df, width="stretch")

    st.subheader("Warnings")
    warnings = df[df["status"].isin(["Near Expiry", "Expired", "Unknown"])]
    st.dataframe(warnings, width="stretch")

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
    st.header("Finalize & Reports")
    if not st.session_state.session_id:
        st.info("Create or select a session first.")
        return
    session = get_session(st.session_state.session_id)
    if not session:
        st.error("Session not found.")
        return

    if session.get("status") != "Finalized":
        if st.button("Finalize / Lock Session"):
            update_session(st.session_state.session_id, {"status": "Finalized"})
            create_audit(st.session_state.user, "finalize_session", session_id=st.session_state.session_id)
            st.success("Session finalized.")
            st.rerun()

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

    if st.button("Export CSV"):
        path = export_csv(detailed_df, f"detailed_{st.session_state.session_id}.csv")
        st.success(f"Saved: {path}")

    if st.button("Export Excel"):
        path = export_excel(detailed_df, summary_df, warnings_df, f"report_{st.session_state.session_id}.xlsx")
        st.success(f"Saved: {path}")

    if st.button("Export PDF (Detailed)"):
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

    if st.button("Export PDF (Summary Only)"):
        path = export_pdf("Inventory Summary Report", summary_df, f"summary_{st.session_state.session_id}.pdf")
        st.success(f"Saved: {path}")


def _audit_page():
    st.header("Audit & Logs")
    records = list_audit(st.session_state.session_id)
    if not records:
        st.info("No audit logs yet.")
        return
    df = pd.DataFrame(records)
    st.dataframe(df, width="stretch")

    if st.button("Export Audit CSV"):
        path = export_csv(df, f"audit_{st.session_state.session_id or 'all'}.csv")
        st.success(f"Saved: {path}")
    if st.button("Export Audit Excel"):
        path = export_excel_single(df, f"audit_{st.session_state.session_id or 'all'}.xlsx", sheet_name="Audit")
        st.success(f"Saved: {path}")


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
        st.info("Persistence backend changes take effect on next app restart.")


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
    _apply_display_mode(settings)

    if not _require_login():
        return

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
        .stButton button, .stTextInput input, .stTextArea textarea, .stSelectbox div {
            color: #e6e6e6 !important;
            background-color: #1c2230 !important;
            border-color: #2a3244 !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


st.set_page_config(page_title="Pharmacy Inventory / Stock Count", layout="wide")
