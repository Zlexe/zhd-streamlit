import streamlit as st
import pandas as pd
import sqlite3
import os
import requests

# --- Скачивание базы данных с Google Диска (при первом запуске) ---
DB_PATH = "зсжд.db"
DB_URL = "https://drive.google.com/uc?export=download&id=1hJqrdYiL-pEqvMXYA_yLG2WNB_WofH0w"

if not os.path.exists(DB_PATH):
    with st.spinner("⏳ Загрузка базы данных (997 МБ)... Это может занять несколько минут."):
        try:
            response = requests.get(DB_URL, stream=True)
            response.raise_for_status()
            total_size = int(response.headers.get('content-length', 0))
            with open(DB_PATH, "wb") as f:
                if total_size == 0:
                    f.write(response.content)
                else:
                    downloaded = 0
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            if downloaded % (1024 * 1024) == 0:  # Каждые 1 МБ
                                st.progress(min(downloaded / total_size, 1.0))
            st.success("✅ База данных загружена!")
        except Exception as e:
            st.error(f"❌ Ошибка загрузки базы данных: {e}")
            st.stop()

# --- Подключение к БД ---
@st.cache_resource
def get_conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

conn = get_conn()

# --- Список столбцов для фильтров ---
FILTER_COLUMNS = [
    "Дата",
    "Дистанция",
    "Перегон",
    "Код устройства",
    "Диагностика/устранение",
    "Категория"
]

# --- Функция для получения уникальных значений ---
@st.cache_data
def get_distinct_values(col_name):
    quoted = f'"{col_name}"'
    query = f"SELECT DISTINCT {quoted} FROM incidents WHERE {quoted} IS NOT NULL AND {quoted} != '' ORDER BY {quoted} COLLATE NOCASE"
    try:
        df = pd.read_sql_query(query, conn)
        return df[col_name].tolist()
    except Exception as e:
        st.error(f"Ошибка при получении значений для {col_name}: {e}")
        return []

# --- Получение общего количества записей ---
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

# --- Пагинация ---
where_sql = " AND ".join(where_clauses)
total_rows = get_total_count(where_sql, params)
PAGE_SIZE = 200
total_pages = max(1, (total_rows + PAGE_SIZE - 1) // PAGE_SIZE)

page = st.sidebar.number_input("Страница", min_value=1, max_value=total_pages, value=1, step=1)
offset = (page - 1) * PAGE_SIZE

# --- Запрос данных ---
query = "SELECT * FROM incidents"
if where_sql:
    query += " WHERE " + where_sql
query += f" LIMIT {PAGE_SIZE} OFFSET {offset}"

df_page = pd.read_sql_query(query, conn, params=params)

if not df_page.empty and "Дата" in df_page.columns:
    df_page["Дата"] = pd.to_datetime(df_page["Дата"], errors="coerce")

df_page = df_page.fillna("")

# --- Отображение ---
st.subheader(f"📋 Данные (всего {total_rows:,}, показаны {offset+1}–{min(offset+PAGE_SIZE, total_rows)})")
st.dataframe(df_page, use_container_width=True, height=600)