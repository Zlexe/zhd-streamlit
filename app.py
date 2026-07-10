import streamlit as st
import pandas as pd
import sqlite3
import os
import gdown

st.set_page_config(page_title="Журнал ШЧ", layout="wide")
st.title("📊 Журнал ситуаций ШЧ")

# --- Загрузка БД ---
DB_PATH = "зсжд.db"
FILE_ID = "1cYa6voTVf2OIk6K9rMMv8td8p_NLWXgi"
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

# --- Проверка и создание filter_cache (без вывода) ---
cursor = conn.cursor()
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='filter_cache'")
has_cache = cursor.fetchone() is not None

if not has_cache:
    cursor.execute("CREATE TABLE filter_cache (filter_name TEXT, value TEXT)")
    conn.commit()
    filter_columns = ["Дата", "Дистанция", "Перегон", "Код устройства", "Категория"]
    for col in filter_columns:
        cursor.execute("PRAGMA table_info(incidents)")
        existing_cols = [row[1] for row in cursor.fetchall()]
        if col not in existing_cols:
            continue
        query = f'INSERT INTO filter_cache (filter_name, value) SELECT "{col}", "{col}" FROM incidents WHERE "{col}" != "" GROUP BY "{col}" ORDER BY "{col}" COLLATE NOCASE'
        cursor.execute(query)
    conn.commit()
    has_cache = True
else:
    # Проверяем, есть ли данные в кеше (если пуст, заполняем)
    cursor.execute("SELECT COUNT(*) FROM filter_cache")
    count = cursor.fetchone()[0]
    if count == 0:
        filter_columns = ["Дата", "Дистанция", "Перегон", "Код устройства", "Категория"]
        for col in filter_columns:
            cursor.execute("PRAGMA table_info(incidents)")
            existing_cols = [row[1] for row in cursor.fetchall()]
            if col not in existing_cols:
                continue
            query = f'INSERT INTO filter_cache (filter_name, value) SELECT "{col}", "{col}" FROM incidents WHERE "{col}" != "" GROUP BY "{col}" ORDER BY "{col}" COLLATE NOCASE'
            cursor.execute(query)
        conn.commit()

# --- Фильтры (берём данные из кеша или напрямую) ---
FILTER_COLUMNS = ["Дата", "Дистанция", "Перегон", "Код устройства", "Категория"]

@st.cache_data
def get_distinct_values(col_name):
    # Сначала пробуем из кеша
    if has_cache:
        query = f'SELECT value FROM filter_cache WHERE filter_name = "{col_name}" ORDER BY value COLLATE NOCASE'
        try:
            df = pd.read_sql_query(query, conn)
            if not df.empty:
                return df["value"].tolist()
        except:
            pass
    # Если кеш пуст или нет таблицы, берём напрямую (медленно, но хоть что-то)
    quoted = f'"{col_name}"'
    query = f"SELECT DISTINCT {quoted} FROM incidents WHERE {quoted} IS NOT NULL AND {quoted} != '' ORDER BY {quoted} COLLATE NOCASE"
    try:
        df = pd.read_sql_query(query, conn)
        return df[col_name].tolist()
    except Exception as e:
        st.error(f"Ошибка при получении значений для {col_name}: {e}")
        return []

# --- Инициализация состояния фильтров ---
for col in FILTER_COLUMNS:
    if col == "Дата":
        if f"use_date_{col}" not in st.session_state:
            st.session_state[f"use_date_{col}"] = False
            values = get_distinct_values(col)
            if values:
                try:
                    min_date = pd.to_datetime(min(values)).date()
                    max_date = pd.to_datetime(max(values)).date()
                    st.session_state[f"date_range_{col}"] = (min_date, max_date)
                except:
                    pass
    else:
        if f"filter_{col}" not in st.session_state:
            st.session_state[f"filter_{col}"] = ["(Все)"]

# --- Боковая панель с фильтрами ---
st.sidebar.header("🔍 Фильтры")

for col in FILTER_COLUMNS:
    if col == "Дата":
        values = get_distinct_values(col)
        if values:
            try:
                min_date = pd.to_datetime(min(values)).date()
                max_date = pd.to_datetime(max(values)).date()
                use_date = st.sidebar.checkbox(
                    f"Фильтр по {col}",
                    key=f"use_date_{col}"
                )
                if use_date:
                    st.sidebar.date_input(
                        "Диапазон дат",
                        value=st.session_state.get(f"date_range_{col}", (min_date, max_date)),
                        min_value=min_date,
                        max_value=max_date,
                        key=f"date_range_{col}"
                    )
            except Exception as e:
                st.sidebar.warning(f"Ошибка с датой: {e}")
    else:
        distinct_vals = get_distinct_values(col)
        if distinct_vals:
            st.sidebar.multiselect(
                f"Фильтр по {col}",
                options=["(Все)"] + distinct_vals,
                default=st.session_state.get(f"filter_{col}", ["(Все)"]),
                key=f"filter_{col}"
            )
        else:
            st.sidebar.warning(f"Нет значений для {col}")

# --- Кнопки ---
col1, col2 = st.sidebar.columns(2)
with col1:
    apply_button = st.button("🔎 Применить", type="primary", use_container_width=True)
with col2:
    reset_button = st.button("🔄 Сбросить", type="secondary", use_container_width=True)

if reset_button:
    for col in FILTER_COLUMNS:
        if col == "Дата":
            st.session_state[f"use_date_{col}"] = False
            values = get_distinct_values(col)
            if values:
                try:
                    min_date = pd.to_datetime(min(values)).date()
                    max_date = pd.to_datetime(max(values)).date()
                    st.session_state[f"date_range_{col}"] = (min_date, max_date)
                except:
                    pass
        else:
            st.session_state[f"filter_{col}"] = ["(Все)"]
    st.session_state["data_loaded"] = False
    st.rerun()

if apply_button:
    st.session_state["data_loaded"] = True

# --- Загрузка данных ---
if st.session_state.get("data_loaded", False):
    where_clauses = []
    params = []

    for col in FILTER_COLUMNS:
        if col == "Дата":
            if st.session_state.get(f"use_date_{col}", False):
                date_range = st.session_state.get(f"date_range_{col}")
                if date_range and len(date_range) == 2:
                    start_date, end_date = date_range
                    where_clauses.append(f'"{col}" BETWEEN ? AND ?')
                    params.extend([start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d")])
        else:
            selected = st.session_state.get(f"filter_{col}", ["(Все)"])
            if "(Все)" not in selected and selected:
                placeholders = ",".join(["?"] * len(selected))
                where_clauses.append(f'"{col}" IN ({placeholders})')
                params.extend(selected)

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

    where_sql = " AND ".join(where_clauses)
    total_rows = get_total_count(where_sql, params)
    PAGE_SIZE = 200
    total_pages = max(1, (total_rows + PAGE_SIZE - 1) // PAGE_SIZE)

    page = st.sidebar.number_input("Страница", min_value=1, max_value=total_pages, value=1, step=1)
    offset = (page - 1) * PAGE_SIZE

    query = "SELECT * FROM incidents"
    if where_sql:
        query += " WHERE " + where_sql
    query += f" LIMIT {PAGE_SIZE} OFFSET {offset}"

    df_page = pd.read_sql_query(query, conn, params=params)
    if not df_page.empty and "Дата" in df_page.columns:
        df_page["Дата"] = pd.to_datetime(df_page["Дата"], errors="coerce")
    df_page = df_page.fillna("")

    st.subheader(f"📋 Данные (всего {total_rows:,}, показаны {offset+1}–{min(offset+PAGE_SIZE, total_rows)})")
    st.dataframe(df_page, use_container_width=True, height=600)
else:
    st.info("👈 Выберите фильтры в боковой панели и нажмите **«Применить»**, чтобы загрузить данные.")