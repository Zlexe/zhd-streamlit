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

# --- Сборка WHERE-условия по текущим фильтрам (используется и таблицей, и графиками) ---
def build_where():
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

    return " AND ".join(where_clauses), params

# --- Загрузка данных ---
if st.session_state.get("data_loaded", False):
    where_sql, params = build_where()

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

    total_rows = get_total_count(where_sql, params)

    tab_table, tab_charts = st.tabs(["📋 Таблица", "📈 Графики"])

    # ==================== ТАБЛИЦА ====================
    with tab_table:
        PAGE_SIZE = 200
        total_pages = max(1, (total_rows + PAGE_SIZE - 1) // PAGE_SIZE)

        page = st.number_input("Страница", min_value=1, max_value=total_pages, value=1, step=1)
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

    # ==================== ГРАФИКИ ====================
    with tab_charts:
        st.subheader(f"📈 Статистика по всей выборке ({total_rows:,} записей)")

        if total_rows == 0:
            st.info("Нет данных под текущие фильтры.")
        else:
            # Кешируем агрегированные запросы по (where_sql, params) — считаются по ВСЕЙ выборке в БД,
            # а не только по текущей странице таблицы.
            @st.cache_data
            def get_group_counts(group_col, where_clause, params, limit=None):
                q = f'SELECT "{group_col}" AS val, COUNT(*) AS cnt FROM incidents'
                if where_clause:
                    q += " WHERE " + where_clause
                q += f' GROUP BY "{group_col}" ORDER BY cnt DESC'
                if limit:
                    q += f" LIMIT {limit}"
                return pd.read_sql_query(q, conn, params=params)

            @st.cache_data
            def get_monthly_counts(where_clause, params):
                # Группировка по Unix-времени, а не по строке "Дата" — надёжнее,
                # т.к. не зависит от текстового формата даты в разных источниках.
                q = (
                    'SELECT strftime(\'%Y-%m\', "Unix время", \'unixepoch\') AS month, COUNT(*) AS cnt '
                    'FROM incidents'
                )
                if where_clause:
                    q += " WHERE " + where_clause
                q += " GROUP BY month ORDER BY month"
                return pd.read_sql_query(q, conn, params=params)

            # Длительность инцидента (сек) из "Время окончания", если это ЧЧ:ММ:СС-длительность,
            # а не время суток. Формула безопасна: некорректные/пустые строки дадут NULL и уйдут из агрегатов.
            DURATION_EXPR = (
                '(CAST(substr("Время окончания",1,2) AS INTEGER)*3600 '
                '+ CAST(substr("Время окончания",4,2) AS INTEGER)*60 '
                '+ CAST(substr("Время окончания",7,2) AS INTEGER))'
            )

            @st.cache_data
            def get_duration_buckets(where_clause, params):
                q = f'''
                    SELECT bucket, cnt FROM (
                        SELECT
                            CASE
                                WHEN dur < 10 THEN '1: <10 сек'
                                WHEN dur < 60 THEN '2: 10–60 сек'
                                WHEN dur < 300 THEN '3: 1–5 мин'
                                WHEN dur < 1800 THEN '4: 5–30 мин'
                                ELSE '5: >30 мин'
                            END AS bucket,
                            COUNT(*) AS cnt
                        FROM (
                            SELECT {DURATION_EXPR} AS dur FROM incidents
                            {"WHERE " + where_clause if where_clause else ""}
                        )
                        WHERE dur IS NOT NULL
                        GROUP BY bucket
                    )
                    ORDER BY bucket
                '''
                df = pd.read_sql_query(q, conn, params=params)
                df["bucket"] = df["bucket"].str.slice(3)  # убрать сортировочный префикс "N: "
                return df

            @st.cache_data
            def get_duration_sum_by(group_col, where_clause, params, limit=None):
                q = f'''
                    SELECT val, SUM(dur) AS total_sec, COUNT(*) AS cnt FROM (
                        SELECT "{group_col}" AS val, {DURATION_EXPR} AS dur FROM incidents
                        {"WHERE " + where_clause if where_clause else ""}
                    )
                    WHERE dur IS NOT NULL
                    GROUP BY val
                    ORDER BY total_sec DESC
                '''
                if limit:
                    q += f" LIMIT {limit}"
                df = pd.read_sql_query(q, conn, params=params)
                df["total_min"] = df["total_sec"] / 60
                return df

            # --- Динамика по месяцам ---
            st.markdown("**Динамика количества инцидентов по месяцам**")
            df_monthly = get_monthly_counts(where_sql, params)
            df_monthly = df_monthly.dropna(subset=["month"])
            if not df_monthly.empty:
                st.line_chart(df_monthly.set_index("month")["cnt"])
            else:
                st.caption("Нет данных для построения динамики (проверьте формат столбца «Дата»).")

            col_a, col_b = st.columns(2)

            with col_a:
                st.markdown("**По категориям**")
                df_cat = get_group_counts("Категория", where_sql, params)
                if not df_cat.empty:
                    st.bar_chart(df_cat.set_index("val")["cnt"])
                else:
                    st.caption("Нет данных по категориям.")

            with col_b:
                st.markdown("**Топ-20 кодов устройств**")
                df_dev = get_group_counts("Код устройства", where_sql, params, limit=20)
                if not df_dev.empty:
                    st.bar_chart(df_dev.set_index("val")["cnt"])
                else:
                    st.caption("Нет данных по кодам устройств.")

            col_c, col_d = st.columns(2)

            with col_c:
                st.markdown("**Топ-20 перегонов**")
                df_seg = get_group_counts("Перегон", where_sql, params, limit=20)
                if not df_seg.empty:
                    st.bar_chart(df_seg.set_index("val")["cnt"])
                else:
                    st.caption("Нет данных по перегонам.")

            with col_d:
                st.markdown("**Топ-20 дистанций**")
                df_dist = get_group_counts("Дистанция", where_sql, params, limit=20)
                if not df_dist.empty:
                    st.bar_chart(df_dist.set_index("val")["cnt"])
                else:
                    st.caption("Нет данных по дистанциям.")

            st.markdown("**Топ-20 видов неисправностей**")
            df_kind = get_group_counts("Вид неисправности", where_sql, params, limit=20)
            if not df_kind.empty:
                st.bar_chart(df_kind.set_index("val")["cnt"])
            else:
                st.caption("Нет данных по видам неисправностей.")

            st.divider()
            st.markdown("### ⏱️ Длительность инцидентов")
            st.caption(
                "Предположение: столбец «Время окончания» хранит длительность инцидента в формате "
                "ЧЧ:ММ:СС, а не время суток. Если это не так — эти три графика будут некорректны, "
                "скажи, что там на самом деле хранится."
            )

            col_e, col_f = st.columns(2)

            with col_e:
                st.markdown("**Распределение по длительности**")
                df_buckets = get_duration_buckets(where_sql, params)
                if not df_buckets.empty:
                    st.bar_chart(df_buckets.set_index("bucket")["cnt"])
                else:
                    st.caption("Не удалось посчитать длительности.")

            with col_f:
                st.markdown("**Суммарный простой по категориям, мин**")
                df_dur_cat = get_duration_sum_by("Категория", where_sql, params)
                if not df_dur_cat.empty:
                    st.bar_chart(df_dur_cat.set_index("val")["total_min"])
                else:
                    st.caption("Не удалось посчитать длительности по категориям.")

            st.markdown("**Топ-20 видов неисправностей по суммарному простою, мин**")
            df_dur_kind = get_duration_sum_by("Вид неисправности", where_sql, params, limit=20)
            if not df_dur_kind.empty:
                st.bar_chart(df_dur_kind.set_index("val")["total_min"])
            else:
                st.caption("Не удалось посчитать длительности по видам неисправностей.")
else:
    st.info("👈 Выберите фильтры в боковой панели и нажмите **«Применить»**, чтобы загрузить данные.")