import sqlite3
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

# ---------------------------------------------------------
# BOOKLOG - 개인 독서 기록 서비스 (최종 완성본)
# ---------------------------------------------------------
st.set_page_config(
    page_title="BOOKLOG | 나의 독서 기록",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded",
)

DB_PATH = Path(__file__).with_name("booklog.db")


def get_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS books (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                author TEXT NOT NULL DEFAULT '',
                publisher TEXT DEFAULT '',
                genre TEXT DEFAULT '',
                total_pages INTEGER DEFAULT 0,
                status TEXT NOT NULL DEFAULT '읽을 예정',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS reading_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                book_id INTEGER NOT NULL,
                read_date TEXT NOT NULL,
                pages_read INTEGER NOT NULL DEFAULT 0,
                reading_minutes INTEGER DEFAULT 0,
                memo TEXT DEFAULT '',
                FOREIGN KEY(book_id) REFERENCES books(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS book_notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                book_id INTEGER NOT NULL UNIQUE,
                rating INTEGER DEFAULT 0,
                review TEXT DEFAULT '',
                quote TEXT DEFAULT '',
                updated_at TEXT NOT NULL,
                FOREIGN KEY(book_id) REFERENCES books(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS reading_goals (
                year INTEGER PRIMARY KEY,
                target_books INTEGER NOT NULL DEFAULT 12
            );

            CREATE TABLE IF NOT EXISTS daily_goals (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                target_pages INTEGER NOT NULL DEFAULT 30
            );
            """
        )
        conn.execute("PRAGMA foreign_keys = ON")


def query_df(sql, params=()):
    with get_connection() as conn:
        return pd.read_sql_query(sql, conn, params=params)


def execute(sql, params=()):
    with get_connection() as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute(sql, params)
        conn.commit()


def get_books():
    return query_df("SELECT * FROM books ORDER BY created_at DESC, id DESC")


def get_progress(book_id):
    row = query_df(
        "SELECT COALESCE(SUM(pages_read), 0) AS pages FROM reading_logs WHERE book_id = ?",
        (int(book_id),),
    )
    return int(row.iloc[0]["pages"]) if not row.empty else 0


def book_label(row):
    return f'{row["title"]} — {row["author"] or "작자 미상"}'


init_db()

if "page" not in st.session_state:
    st.session_state.page = "홈"
if "editing_book_id" not in st.session_state:
    st.session_state.editing_book_id = None

st.markdown(
    """
    <style>
    .main-title {font-size: 2.25rem; font-weight: 800; letter-spacing: -1px;}
    .subtle {color: #687386; font-size: .95rem;}
    div[data-testid="stMetric"] {
        background: #f7f9fc; border: 1px solid #e8edf5;
        padding: 14px 16px; border-radius: 12px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

with st.sidebar:
    st.markdown("# 📚 BOOKLOG")
    st.caption("읽고, 기록하고, 돌아보다.")
    st.divider()
    pages = ["홈", "나의 책장", "독서 기록", "독서 노트", "통계 및 목표"]
    for p in pages:
        if st.button(
            p,
            key=f"nav_{p}",
            use_container_width=True,
            type="primary" if st.session_state.page == p else "secondary",
        ):
            st.session_state.page = p
            st.rerun()
    st.divider()
    st.caption("나만의 독서 기록을 차곡차곡 쌓아 보세요.")

books = get_books()
book_count = len(books)
completed_count = int((books["status"] == "완독").sum()) if not books.empty else 0
reading_count = int((books["status"] == "읽는 중").sum()) if not books.empty else 0
total_pages_read = int(
    query_df("SELECT COALESCE(SUM(pages_read),0) AS n FROM reading_logs").iloc[0]["n"]
)
today_str = date.today().isoformat()


# ---------------------------------------------------------
# 1. HOME (독서 대시보드)
# ---------------------------------------------------------
if st.session_state.page == "홈":
    st.markdown('<div class="main-title">나의 독서 대시보드</div>', unsafe_allow_html=True)
    st.markdown('<div class="subtle">기록이 쌓이면, 나의 독서가 보입니다.</div>', unsafe_allow_html=True)
    st.write("")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("등록한 책", f"{book_count}권")
    c2.metric("완독한 책", f"{completed_count}권")
    c3.metric("읽는 중", f"{reading_count}권")
    c4.metric("누적 독서 페이지", f"{total_pages_read:,}쪽")

    daily_row = query_df("SELECT target_pages FROM daily_goals WHERE id = 1")
    current_daily_goal = int(daily_row.iloc[0]["target_pages"]) if not daily_row.empty else 30
    read_today_pages = int(
        query_df(
            "SELECT COALESCE(SUM(pages_read), 0) AS n FROM reading_logs WHERE read_date = ?",
            (today_str,),
        ).iloc[0]["n"]
    )
    pct_today = int(min(read_today_pages / max(current_daily_goal, 1) * 100, 100))
    st.write("")
    st.progress(
        min(read_today_pages / max(current_daily_goal, 1), 1.0),
        text=f"📅 오늘의 독서 달성률: {read_today_pages:,} / {current_daily_goal:,}쪽 ({pct_today}%)",
    )

    st.subheader("📖 지금 읽고 있는 책")
    current = books[books["status"] == "읽는 중"] if not books.empty else pd.DataFrame()
    if current.empty:
        st.info("현재 읽는 중인 책이 없습니다. 나의 책장에서 책을 등록하고 상태를 '읽는 중'으로 바꿔 보세요.")
    else:
        cols = st.columns(min(3, len(current)))
        for i, (_, b) in enumerate(current.head(3).iterrows()):
            done = get_progress(b["id"])
            total = int(b["total_pages"] or 0)
            pct = min(done / total, 1.0) if total > 0 else 0
            with cols[i]:
                with st.container(border=True):
                    st.markdown(f"**{b['title']}**")
                    st.caption(b["author"] or "작자 미상")
                    st.progress(pct, text=f"{done:,} / {total:,}쪽" if total else f"{done:,}쪽 기록")

    st.subheader("🕒 최근 독서 기록")
    recent = query_df(
        """SELECT r.read_date, b.title, r.pages_read, r.reading_minutes, r.memo
           FROM reading_logs r JOIN books b ON b.id = r.book_id
           ORDER BY r.read_date DESC, r.id DESC LIMIT 5"""
    )
    if recent.empty:
        st.caption("아직 기록이 없습니다. 독서 기록 메뉴에서 첫 기록을 남겨 보세요.")
    else:
        st.dataframe(
            recent.rename(
                columns={
                    "read_date": "날짜",
                    "title": "책 제목",
                    "pages_read": "읽은 페이지",
                    "reading_minutes": "읽은 시간(분)",
                    "memo": "메모",
                }
            ),
            hide_index=True,
            use_container_width=True,
        )


# ---------------------------------------------------------
# 2. BOOKSHELF (나의 책장)
# ---------------------------------------------------------
elif st.session_state.page == "나의 책장":
    st.title("📚 나의 책장")
    st.write("읽을 책과 읽고 있는 책, 완독한 책을 한곳에서 관리하세요.")
    with st.expander("➕ 새 책 등록하기", expanded=book_count == 0):
        with st.form("add_book_form", clear_on_submit=True):
            a, b = st.columns(2)
            title = a.text_input("책 제목 *")
            author = b.text_input("저자")
            publisher = a.text_input("출판사")
            genres_list = [
                "선택 안 함", "소설", "에세이", "인문", "사회",
                "경제·경영", "자기계발", "과학", "역사", "예술", "기타"
            ]
            genre = b.selectbox("장르", genres_list)
            total_pages = a.number_input("총 페이지 수", min_value=0, max_value=100000, value=0, step=1)
            status = b.selectbox("독서 상태", ["읽을 예정", "읽는 중", "완독", "중단"])
            submitted = st.form_submit_button("책 등록", type="primary")
            if submitted:
                if not title.strip():
                    st.error("책 제목을 입력해 주세요.")
                else:
                    execute(
                        """INSERT INTO books(title, author, publisher, genre, total_pages, status, created_at)
                           VALUES (?, ?, ?, ?, ?, ?, ?)""",
                        (
                            title.strip(),
                            author.strip(),
                            publisher.strip(),
                            "" if genre == "선택 안 함" else genre,
                            int(total_pages),
                            status,
                            datetime.now().isoformat(timespec="seconds"),
                        ),
                    )
                    st.success("책이 등록되었습니다.")
                    st.rerun()

    books = get_books()
    if books.empty:
        st.info("등록된 책이 없습니다. 위에서 첫 번째 책을 등록해 보세요.")
    else:
        col_search, col_filter = st.columns([2, 1])
        search = col_search.text_input("🔎 책 제목 또는 저자 검색")
        status_filter = col_filter.selectbox("독서 상태 필터", ["전체", "읽을 예정", "읽는 중", "완독", "중단"])
        filtered = books.copy()
        if search:
            filtered = filtered[
                filtered["title"].str.contains(search, case=False, na=False)
                | filtered["author"].str.contains(search, case=False, na=False)
            ]
        if status_filter != "전체":
            filtered = filtered[filtered["status"] == status_filter]
        st.caption(f"총 {len(filtered)}권")
        for _, b in filtered.iterrows():
            with st.container(border=True):
                left, middle, right = st.columns([4, 2, 1])
                with left:
                    st.markdown(f"**{b['title']}**")
                    st.caption(
                        f"{b['author'] or '저자 미입력'} · {b['publisher'] or '출판사 미입력'} · {b['genre'] or '장르 미입력'}"
                    )
                    done = get_progress(b["id"])
                    total = int(b["total_pages"] or 0)
                    if total > 0:
                        st.progress(min(done / total, 1.0), text=f"읽은 페이지 {min(done
