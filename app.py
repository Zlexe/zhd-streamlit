import streamlit as st
import pandas as pd
import sqlite3
import os
import gdown

st.set_page_config(page_title="Журнал ШЧ", layout="wide")
st.title("📊 Журнал ситуаций ШЧ")

# --- Инициализация состояния ---
if "data_loaded" not in st.session_state:
    st.session_state.data_loaded = False

# --- Загрузка БД (один раз при старте) ---
DB_PATH = "зсжд.db"
FILE_ID = "1cYa6voTVf2OIk6K9rMMv8td8p_NLWXgi"  # <-- НОВЫЙ ID
DB_URL = f"https://drive.google.com/uc?id={FILE_ID}"

if not os.path.exists(DB_PATH):
    with st.spinner("⏳ Загрузка базы данных (997 МБ)... Это может занять несколько минут."):
        try:
            gdown.download(DB_URL, DB_PATH, quiet=False)
            st.success("✅ База данных загружена!")
        except Exception as e:
            st.error(f"❌ Ошибка загрузки базы данных: {e}")
            st.stop()

try:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='incidents'")
    if not cursor.fetchone():
        st.error("❌ Таблица 'incidents' не найдена.")
        st.stop()
except sqlite3.DatabaseError as e:
    st.error(f"❌ База данных повреждена: {e}")
    st.stop()

@st.cache_resource
def get_conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

conn = get_conn()

# --- Проверка наличия таблицы filter_cache ---
cursor = conn.cursor()
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='filter_cache'")
if not cursor.fetchone():
    st.error("❌ Таблица filter_cache не найдена. База данных устарела, пересоздайте её.")
    st.stop()

# --- Фильтры ---
FILTER_COLUMNS = [
    "Дата",
    "Дистанция",
    "Перегон",
    "Код устройства",
    "Диагностика/устранение",
    "Категория"
]

@st.cache_data
def get_distinct_values(col_name):
    """Берём уникальные значения из таблицы-кеша (мгновенно)"""
    query = f'SELECT value FROM filter_cache WHERE filter_name = "{col_name}" ORDER BY value COLLATE NOCASE'
    try:
        df = pd.read_sql_query(query, conn)
        return df["value"].tolist()
    except Exception as e:
        st.error(f"Ошибка при получении значений для {col_name}: {e}")
        return []

@st.cache_data
def get_total_count(where_clause="", params=None):
    if params is None:
        params = []
    c = conn.cursor()
    query = "SELECT COUNT(*) FROM incidents"
    if where_clause:
        query += " WHERE " + where_clause
    c.execute(query, params)
    return c.fetchone()[0]

# --- Боковая панель с фильтрами ---
st.sidebar.header("🔍 Фильтры")

if "filters" not in st.session_state:
    st.session_state.filters = {}

where_clauses = []
params = []

for col in FILTER_COLUMNS:
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(incidents)")
    existing_cols = [row[1] for row in cursor.fetchall()]
    if col not in existing_cols:
        continue

    if col == "Дата":
        try:
            values = get_distinct_values(col)
            if values:
                min_date = pd.to_datetime(min(values)).date()
                max_date = pd.to_datetime(max(values)).date()
                use_date_filter = st.sidebar.checkbox(f"Фильтр по {col}")
                if use_date_filter:
                    start_date, end_date = st.sidebar.date_input(
                        "Диапазон дат",
                        value=(min_date, max_date),
                        min_value=min_date,
                        max_value=max_date
                    )
                    st.session_state.filters["date_range"] = (start_date, end_date)
                    where_clauses.append(f'"{col}" BETWEEN ? AND ?')
                    params.extend([start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d")])
        except Exception as e:
            st.warning(f"Не удалось создать фильтр по дате: {e}")
    else:
        distinct_vals = get_distinct_values(col)
        if not distinct_vals:
            continue
        selected = st.sidebar.multiselect(
            f"Фильтр по {col}",
            options=["(Все)"] + distinct_vals,
            default=["(Все)"]
        )
        if "(Все)" not in selected and selected:
            placeholders = ",".join(["?"] * len(selected))
            where_clauses.append(f'"{col}" IN ({placeholders})')
            params.extend(selected)
            st.session_state.filters[col] = selected
        else:
            st.session_state.filters[col] = ["(Все)"]

# --- Кнопка "Применить" ---
apply_button = st.sidebar.button("🔎 Применить фильтры", type="primary")

if apply_button:
    st.session_state.data_loaded = True
    st.session_state.where_clauses = where_clauses
    st.session_state.params = params

# --- Отображение данных (только если нажата кнопка) ---
if st.session_state.data_loaded:
    where_sql = " AND ".join(st.session_state.where_clauses)
    total_rows = get_total_count(where_sql, st.session_state.params)
    PAGE_SIZE = 200
    total_pages = max(1, (total_rows + PAGE_SIZE - 1) // PAGE_SIZE)

    page = st.sidebar.number_input("Страница", min_value=1, max_value=total_pages, value=1, step=1)
    offset = (page - 1) * PAGE_SIZE

    query = "SELECT * FROM incidents"
    if where_sql:
        query += " WHERE " + where_sql
    query += f" LIMIT {PAGE_SIZE} OFFSET {offset}"

    df_page = pd.read_sql_query(query, conn, params=st.session_state.params)
    if not df_page.empty and "Дата" in df_page.columns:
        df_page["Дата"] = pd.to_datetime(df_page["Дата"], errors="coerce")
    df_page = df_page.fillna("")

    st.subheader(f"📋 Данные (всего {total_rows:,}, показаны {offset+1}–{min(offset+PAGE_SIZE, total_rows)})")
    st.dataframe(df_page, use_container_width=True, height=600)
else:
    st.info("👈 Выберите фильтры в боковой панели и нажмите **«Применить фильтры»**, чтобы загрузить данные.")