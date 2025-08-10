import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
from io import BytesIO
from datetime import datetime
import json

# Optional Google Sheets deps
try:
    import gspread
    from google.oauth2.service_account import Credentials
    from gspread_dataframe import set_with_dataframe, get_as_dataframe
except Exception:
    gspread = None
    Credentials = None

st.set_page_config(page_title="Blood Pressure Logger", page_icon="🩺", layout="wide")
st.title("🩺 Blood Pressure Logger")
st.caption("Log BP readings, add notes, and visualize trends. Now with Google Sheets sync.")

# ----------------- Config -----------------
CSV_PATH = "bp_data.csv"
DEFAULT_SHEET_NAME = "bp_data"

def get_gs_client():
    """Return an authorized gspread client using Streamlit secrets."""
    if "gcp_service_account" not in st.secrets:
        return None, "No Google credentials found in st.secrets. Using local CSV."
    try:
        sa_info = dict(st.secrets["gcp_service_account"])
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        creds = Credentials.from_service_account_info(sa_info, scopes=scopes)
        client = gspread.authorize(creds)
        return client, None
    except Exception as e:
        return None, f"Google auth failed: {e}"

def get_sheet_handles():
    """Open or create spreadsheet & worksheet based on secrets."""
    client, err = get_gs_client()
    if not client:
        return None, None, err

    # Spreadsheet target can be provided by URL or key in secrets
    # st.secrets["spreadsheet"] can be either a URL or a key.
    sheet_url = st.secrets.get("spreadsheet", "")
    ws_name = st.secrets.get("worksheet", DEFAULT_SHEET_NAME)

    try:
        if sheet_url:
            if "https://" in sheet_url or "http://" in sheet_url:
                sh = client.open_by_url(sheet_url)
            else:
                sh = client.open_by_key(sheet_url)
        else:
            # Create a new spreadsheet in the user's Drive if not specified
            sh = client.create("Blood Pressure Logger Data")
        try:
            ws = sh.worksheet(ws_name)
        except gspread.WorksheetNotFound:
            ws = sh.add_worksheet(title=ws_name, rows=1000, cols=20)
            # initialize headers
            headers = ["timestamp", "systolic", "diastolic", "pulse", "notes", "category", "map", "pulse_pressure"]
            ws.update([headers])
        return sh, ws, None
    except Exception as e:
        return None, None, f"Opening spreadsheet failed: {e}"

# ----------------- Domain helpers -----------------
def categorize_bp(sys, dia):
    if sys < 120 and dia < 80:
        return "Normal"
    if 120 <= sys < 130 and dia < 80:
        return "Elevated"
    if (130 <= sys < 140) or (80 <= dia < 90):
        return "Hypertension Stage 1"
    if sys >= 140 or dia >= 90:
        return "Hypertension Stage 2"
    return "Uncategorized"

# ----------------- Data IO -----------------
def load_data_local():
    try:
        df = pd.read_csv(CSV_PATH, parse_dates=["timestamp"])
        for col in ["systolic", "diastolic", "pulse", "map", "pulse_pressure"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        return df.dropna(subset=["timestamp"])
    except FileNotFoundError:
        cols = ["timestamp", "systolic", "diastolic", "pulse", "notes", "category", "map", "pulse_pressure"]
        return pd.DataFrame(columns=cols)

def save_data_local(df: pd.DataFrame):
    df.to_csv(CSV_PATH, index=False)

def load_data_gsheets():
    sh, ws, err = get_sheet_handles()
    if err or not ws:
        return None, err
    try:
        df = get_as_dataframe(ws, evaluate_formulas=True, header=0, dtype=None, nrows=None)
        # Drop fully empty rows if any (gspread_dataframe preserves sheet size)
        df = df.dropna(how="all")
        if df.empty:
            df = pd.DataFrame(columns=["timestamp","systolic","diastolic","pulse","notes","category","map","pulse_pressure"])
        # Parse types
        if "timestamp" in df.columns:
            df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
        for col in ["systolic","diastolic","pulse","map","pulse_pressure"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        return df.dropna(subset=["timestamp"]), None
    except Exception as e:
        return None, f"Read from Google Sheets failed: {e}"

def save_data_gsheets(df: pd.DataFrame):
    sh, ws, err = get_sheet_handles()
    if err or not ws:
        return err or "No worksheet"
    try:
        # Ensure consistent column order
        cols = ["timestamp","systolic","diastolic","pulse","notes","category","map","pulse_pressure"]
        for c in cols:
            if c not in df.columns:
                df[c] = None
        df = df[cols]
        # Convert timestamps to ISO strings for Sheets
        if pd.api.types.is_datetime64_any_dtype(df["timestamp"]):
            df["timestamp"] = df["timestamp"].dt.strftime("%Y-%m-%d %H:%M:%S")
        ws.clear()
        set_with_dataframe(ws, df, include_index=False, include_column_header=True, resize=True)
        return None
    except Exception as e:
        return f"Write to Google Sheets failed: {e}"

def load_data():
    # Prefer Sheets if configured
    if gspread and "gcp_service_account" in st.secrets:
        df, err = load_data_gsheets()
        if err:
            st.warning(f"Google Sheets read issue: {err} — falling back to local CSV.")
            return load_data_local(), "local"
        return df, "gsheets"
    else:
        return load_data_local(), "local"

def save_data(df, target):
    if target == "gsheets" and gspread and "gcp_service_account" in st.secrets:
        err = save_data_gsheets(df)
        if err:
            st.error(err)
            st.info("Saving locally instead.")
            save_data_local(df)
            return "local"
        return "gsheets"
    else:
        save_data_local(df)
        return "local"

def add_entry(sys, dia, pulse, notes, ts, io_target):
    df, _ = load_data()
    category = categorize_bp(sys, dia)
    pulse_pressure = sys - dia
    mean_arterial_pressure = round(dia + (pulse_pressure/3), 1)
    row = {
        "timestamp": pd.to_datetime(ts),
        "systolic": int(sys),
        "diastolic": int(dia),
        "pulse": int(pulse) if pulse is not None else None,
        "notes": notes or "",
        "category": category,
        "map": mean_arterial_pressure,
        "pulse_pressure": pulse_pressure,
    }
    df = pd.concat([df, pd.DataFrame([row])], ignore_index=True).sort_values("timestamp")
    actual_target = save_data(df, io_target)
    return df, actual_target

def df_download_bytes(df):
    out = BytesIO()
    df.to_csv(out, index=False)
    out.seek(0)
    return out

# ----------------- Sidebar (data ops) -----------------
with st.sidebar:
    st.header("Data")
    io_mode = "gsheets" if gspread and "gcp_service_account" in st.secrets else "local"
    if io_mode == "gsheets":
        st.success("Google Sheets: enabled")
        st.write(f"Worksheet: `{st.secrets.get('worksheet', DEFAULT_SHEET_NAME)}`")
        ss_label = st.secrets.get("spreadsheet", "auto-created")
        st.caption(f"Spreadsheet: {ss_label}")
    else:
        st.warning("Google Sheets not configured. Using local CSV.")

    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("⬇️ Download CSV"):
            df_tmp, _ = load_data()
            st.download_button("Save file", data=df_download_bytes(df_tmp), file_name="bp_data.csv", mime="text/csv")
    with col_b:
        uploaded = st.file_uploader("Restore/merge from CSV", type=["csv"], label_visibility="collapsed")
        if uploaded is not None:
            try:
                existing, _ = load_data()
                incoming = pd.read_csv(uploaded, parse_dates=["timestamp"])
                merged = pd.concat([existing, incoming], ignore_index=True).drop_duplicates().sort_values("timestamp")
                save_target = save_data(merged, io_mode)
                st.success(f"Imported {len(incoming)} rows. Total rows: {len(merged)}. Saved to {save_target}.")
            except Exception as e:
                st.error(f"Import failed: {e}")

    if st.button("🗑️ Clear ALL data"):
        empty = pd.DataFrame(columns=["timestamp","systolic","diastolic","pulse","notes","category","map","pulse_pressure"])
        save_target = save_data(empty, io_mode)
        st.warning(f"All data cleared. Saved to {save_target}.")

st.divider()

# ----------------- Input form -----------------
st.subheader("Add a reading")

with st.form("bp_form", clear_on_submit=True):
    col1, col2, col3, col4 = st.columns([1,1,1,2])
    with col1:
        systolic = st.number_input("Systolic (mmHg)", min_value=50, max_value=260, value=120, step=1)
    with col2:
        diastolic = st.number_input("Diastolic (mmHg)", min_value=30, max_value=180, value=75, step=1)
    with col3:
        pulse = st.number_input("Pulse (bpm)", min_value=20, max_value=220, value=70, step=1)
    with col4:
        notes = st.text_input("Notes (optional)", placeholder="Medication, posture, time since coffee, etc.")

    manual_ts = st.checkbox("Set custom date & time")
    if manual_ts:
        c1, c2 = st.columns(2)
        with c1:
            date = st.date_input("Date", value=datetime.now().date())
        with c2:
            time = st.time_input("Time", value=datetime.now().time().replace(microsecond=0))
        ts = datetime.combine(date, time)
    else:
        ts = datetime.now()

    submitted = st.form_submit_button("Add reading", type="primary")
    if submitted:
        df, target_used = add_entry(systolic, diastolic, pulse, notes, ts, "gsheets")
        st.success(f"Reading saved to {target_used}.")
    else:
        df, _ = load_data()

# ----------------- Data table -----------------
st.subheader("Recent readings")
if df.empty:
    st.info("No data yet. Add your first reading above.")
else:
    df_view = df.sort_values("timestamp", ascending=False).copy()
    df_view["timestamp"] = df_view["timestamp"].dt.strftime("%Y-%m-%d %H:%M")
    st.dataframe(df_view.head(25), use_container_width=True)

# ----------------- Visualizations -----------------
if not df.empty:
    st.subheader("Trends")

    df_plot = df.copy().sort_values("timestamp")
    df_plot["date"] = df_plot["timestamp"].dt.date

    df_plot.set_index("timestamp", inplace=True)
    for col in ["systolic", "diastolic"]:
        df_plot[f"{col}_7d_avg"] = df_plot[col].rolling("7D").mean()

    st.markdown("**Systolic & Diastolic over time** (with 7-day rolling average)")
    fig1, ax1 = plt.subplots()
    ax1.plot(df_plot.index, df_plot["systolic"], label="Systolic")
    ax1.plot(df_plot.index, df_plot["diastolic"], label="Diastolic")
    if df_plot["systolic_7d_avg"].notna().any() or df_plot["diastolic_7d_avg"].notna().any():
        ax1.plot(df_plot.index, df_plot["systolic_7d_avg"], linestyle="--", label="Systolic (7d avg)")
        ax1.plot(df_plot.index, df_plot["diastolic_7d_avg"], linestyle="--", label="Diastolic (7d avg)")
    ax1.set_xlabel("Date")
    ax1.set_ylabel("mmHg")
    ax1.legend()
    st.pyplot(fig1)

    st.markdown("**Systolic vs Diastolic** (each point = a reading)")
    fig2, ax2 = plt.subplots()
    ax2.scatter(df["systolic"], df["diastolic"])
    ax2.set_xlabel("Systolic (mmHg)")
    ax2.set_ylabel("Diastolic (mmHg)")
    ax2.set_xlim(left=min(80, df["systolic"].min() - 5) if not df["systolic"].isna().all() else 80,
                 right=max(180, df["systolic"].max() + 5) if not df["systolic"].isna().all() else 180)
    ax2.set_ylim(bottom=min(50, df["diastolic"].min() - 5) if not df["diastolic"].isna().all() else 50,
                 top=max(120, df["diastolic"].max() + 5) if not df["diastolic"].isna().all() else 120)
    st.pyplot(fig2)

    st.subheader("Weekly summary")
    df_week = df.copy()
    df_week["week"] = df_week["timestamp"].dt.to_period("W").apply(lambda p: p.start_time.date())
    summary = (
        df_week.groupby("week")[["systolic", "diastolic", "pulse", "map", "pulse_pressure"]]
        .agg(["count", "mean", "min", "max"])
    )
    summary.columns = ['_'.join(col).strip() for col in summary.columns.values]
    st.dataframe(summary, use_container_width=True)

# ----------------- Info -----------------
with st.expander("How are categories defined?"):
    st.markdown(
        """
- **Normal:** Systolic < 120 and Diastolic < 80  
- **Elevated:** Systolic 120-129 and Diastolic < 80  
- **Hypertension Stage 1:** Systolic 130-139 or Diastolic 80-89  
- **Hypertension Stage 2:** Systolic >= 140 or Diastolic >= 90
        """
    )

st.caption("Tip: Take two readings each time and log the average. Measure at consistent times daily, seated, with arm at heart level.")