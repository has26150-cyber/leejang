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
                        st.progress(min(done / total, 1.0), text=f"읽은 페이지 {min(done, total):,} / {total:,}쪽")
                    else:
                        st.caption(f"읽은 페이지 {done:,}쪽")
                with middle:
                    new_status = st.selectbox(
                        "독서 상태",
                        ["읽을 예정", "읽는 중", "완독", "중단"],
                        index=["읽을 예정", "읽는 중", "완독", "중단"].index(b["status"]),
                        key=f"status_{b['id']}",
                    )
                    if new_status != b["status"]:
                        execute("UPDATE books SET status = ? WHERE id = ?", (new_status, int(b["id"])))
                        st.rerun()
                with right:
                    if st.button("수정", key=f"edit_{b['id']}"):
                        st.session_state.editing_book_id = int(b["id"])
                        st.rerun()
                    if st.button("삭제", key=f"delete_{b['id']}"):
                        st.session_state[f"confirm_delete_{b['id']}"] = True
                if st.session_state.get(f"confirm_delete_{b['id']}", False):
                    st.warning("이 책과 연결된 독서 기록 및 노트도 함께 삭제됩니다.")
                    yes, no = st.columns(2)
                    if yes.button("정말 삭제", key=f"yes_delete_{b['id']}", type="primary"):
                        execute("DELETE FROM books WHERE id = ?", (int(b["id"]),))
                        st.session_state[f"confirm_delete_{b['id']}"] = False
                        st.success("삭제했습니다.")
                        st.rerun()
                    if no.button("취소", key=f"no_delete_{b['id']}"):
                        st.session_state[f"confirm_delete_{b['id']}"] = False
                        st.rerun()

        edit_id = st.session_state.editing_book_id
        if edit_id is not None:
            selected = books[books["id"] == edit_id]
            if not selected.empty:
                b = selected.iloc[0]
                st.divider()
                st.subheader("책 정보 수정")
                with st.form("edit_book_form"):
                    new_title = st.text_input("책 제목", value=b["title"])
                    new_author = st.text_input("저자", value=b["author"] or "")
                    new_publisher = st.text_input("출판사", value=b["publisher"] or "")
                    genres = ["", "소설", "에세이", "인문", "사회", "경제·경영", "자기계발", "과학", "역사", "예술", "기타"]
                    old_genre = b["genre"] or ""
                    new_genre = st.selectbox("장르", genres, index=genres.index(old_genre) if old_genre in genres else 0)
                    new_total = st.number_input("총 페이지 수", min_value=0, value=int(b["total_pages"] or 0), step=1)
                    save, cancel = st.columns(2)
                    save_edit = save.form_submit_button("변경 사항 저장", type="primary")
                    cancel_edit = cancel.form_submit_button("수정 취소")
                    if save_edit:
                        if not new_title.strip():
                            st.error("책 제목은 비워 둘 수 없습니다.")
                        else:
                            execute(
                                "UPDATE books SET title=?, author=?, publisher=?, genre=?, total_pages=? WHERE id=?",
                                (
                                    new_title.strip(),
                                    new_author.strip(),
                                    new_publisher.strip(),
                                    new_genre,
                                    int(new_total),
                                    edit_id,
                                ),
                            )
                            st.session_state.editing_book_id = None
                            st.success("수정했습니다.")
                            st.rerun()
                    if cancel_edit:
                        st.session_state.editing_book_id = None
                        st.rerun()


# ---------------------------------------------------------
# 3. READING LOGS (독서 기록)
# ---------------------------------------------------------
elif st.session_state.page == "독서 기록":
    st.title("📝 독서 기록")
    st.write("책을 읽은 날짜와 페이지, 읽으면서 떠오른 생각을 기록하세요.")
    books = get_books()
    if books.empty:
        st.info("먼저 나의 책장에서 책을 등록해 주세요.")
    else:
        options = {book_label(row): int(row["id"]) for _, row in books.iterrows()}
        with st.form("reading_log_form", clear_on_submit=True):
            selected_label = st.selectbox("책 선택", list(options.keys()))
            read_date = st.date_input("읽은 날짜", value=date.today())
            a, b = st.columns(2)
            pages_read = a.number_input(
                "이번에 읽은 페이지 수",
                min_value=1,
                max_value=100000,
                value=10,
                step=1,
            )
            minutes = b.number_input(
                "읽은 시간(분)",
                min_value=0,
                max_value=1440,
                value=0,
                step=5,
            )
            memo = st.text_area("독서 메모", placeholder="오늘 읽은 내용이나 떠오른 생각을 적어 보세요.")
            save_log = st.form_submit_button("독서 기록 저장", type="primary")
            if save_log:
                book_id = options[selected_label]
                book_row = books.loc[books["id"] == book_id].iloc[0]
                total = int(book_row["total_pages"] or 0)
                already = get_progress(book_id)
                new_total_read = already + int(pages_read)

                if total > 0 and new_total_read > total:
                    st.error(f"기록한 페이지가 총 페이지 수({total}쪽)를 초과합니다. 현재 누적 {already}쪽입니다.")
                else:
                    execute(
                        """INSERT INTO reading_logs(book_id, read_date, pages_read, reading_minutes, memo)
                           VALUES (?, ?, ?, ?, ?)""",
                        (book_id, read_date.isoformat(), int(pages_read), int(minutes), memo.strip()),
                    )
                    if total > 0 and new_total_read == total and book_row["status"] != "완독":
                        execute("UPDATE books SET status = '완독' WHERE id = ?", (book_id,))
                        st.success("독서 기록을 저장했으며, 총 페이지에 도달하여 '완독'으로 자동 변경되었습니다! 🎉")
                    else:
                        if book_row["status"] == "읽을 예정":
                            execute("UPDATE books SET status = '읽는 중' WHERE id = ?", (book_id,))
                        st.success("독서 기록을 저장했습니다.")
                    st.rerun()

        st.subheader("기록 목록")
        logs = query_df(
            """SELECT r.id, r.read_date, b.title, r.pages_read, r.reading_minutes, r.memo
               FROM reading_logs r JOIN books b ON b.id=r.book_id
               ORDER BY r.read_date DESC, r.id DESC"""
        )
        if logs.empty:
            st.caption("아직 저장된 독서 기록이 없습니다.")
        else:
            st.dataframe(
                logs.rename(
                    columns={
                        "read_date": "날짜",
                        "title": "책 제목",
                        "pages_read": "읽은 페이지",
                        "reading_minutes": "읽은 시간(분)",
                        "memo": "메모",
                        "id": "기록 번호",
                    }
                ),
                hide_index=True,
                use_container_width=True,
            )
            delete_id = st.selectbox(
                "삭제할 기록 선택",
                [None] + logs["id"].astype(int).tolist(),
                format_func=lambda x: "선택 안 함" if x is None else f"기록 번호 {x}",
            )
            if delete_id is not None and st.button("선택한 기록 삭제"):
                execute("DELETE FROM reading_logs WHERE id = ?", (int(delete_id),))
                st.success("기록을 삭제했습니다.")
                st.rerun()


# ---------------------------------------------------------
# 4. NOTES (독서 노트)
# ---------------------------------------------------------
elif st.session_state.page == "독서 노트":
    st.title("💭 독서 노트")
    st.write("책을 읽으며 인상 깊었던 문장과 나만의 감상평을 저장하세요.")
    books = get_books()
    if books.empty:
        st.info("먼저 나의 책장에 책을 등록해 주세요.")
    else:
        options = {book_label(row): int(row["id"]) for _, row in books.iterrows()}
        selected_label = st.selectbox("노트를 작성할 책", list(options.keys()))
        book_id = options[selected_label]
        old = query_df("SELECT * FROM book_notes WHERE book_id = ?", (book_id,))
        old_rating = int(old.iloc[0]["rating"]) if not old.empty else 0
        old_review = old.iloc[0]["review"] if not old.empty else ""
        old_quote = old.iloc[0]["quote"] if not old.empty else ""
        with st.form("book_note_form"):
            rating = st.slider(
                "별점",
                min_value=0,
                max_value=5,
                value=old_rating,
                help="0점은 아직 별점을 매기지 않은 상태입니다.",
            )
            review = st.text_area(
                "나의 감상평",
                value=old_review,
                height=150,
                placeholder="책을 읽고 느낀 점을 자유롭게 적어 보세요.",
            )
            quote = st.text_area(
                "인상 깊었던 문장",
                value=old_quote,
                height=110,
                placeholder="기억하고 싶은 문장을 적어 보세요.",
            )
            save_note = st.form_submit_button("노트 저장", type="primary")
            if save_note:
                execute(
                    """INSERT INTO book_notes(book_id, rating, review, quote, updated_at)
                       VALUES (?, ?, ?, ?, ?)
                       ON CONFLICT(book_id) DO UPDATE SET
                       rating=excluded.rating, review=excluded.review,
                       quote=excluded.quote, updated_at=excluded.updated_at""",
                    (
                        book_id,
                        int(rating),
                        review.strip(),
                        quote.strip(),
                        datetime.now().isoformat(timespec="seconds"),
                    ),
                )
                st.success("독서 노트를 저장했습니다.")
                st.rerun()

        st.subheader("저장된 독서 노트")
        notes = query_df(
            """SELECT b.title, n.rating, n.review, n.quote, n.updated_at
               FROM book_notes n JOIN books b ON b.id=n.book_id
               ORDER BY n.updated_at DESC"""
        )
        if notes.empty:
            st.caption("아직 저장된 노트가 없습니다.")
        else:
            for _, n in notes.iterrows():
                with st.container(border=True):
                    st.markdown(f"**{n['title']}**  ·  {'⭐' * int(n['rating']) if n['rating'] else '별점 없음'}")
                    if n["review"]:
                        st.write(n["review"])
                    if n["quote"]:
                        st.markdown(f"> “{n['quote']}”")
                    st.caption(f"마지막 수정: {n['updated_at'][:10]}")


# ---------------------------------------------------------
# 5. STATISTICS & GOALS (통계 및 목표)
# ---------------------------------------------------------
elif st.session_state.page == "통계 및 목표":
    st.title("📊 통계 및 목표")
    st.write("나의 독서 데이터를 확인하고 연간 및 일간 목표를 세워 보세요.")
    current_year = date.today().year
    today_iso = date.today().isoformat()

    goal_row = query_df("SELECT target_books FROM reading_goals WHERE year = ?", (current_year,))
    current_goal = int(goal_row.iloc[0]["target_books"]) if not goal_row.empty else 12
    completed_this_year = int(
        query_df(
            "SELECT COUNT(*) AS n FROM books WHERE status='완독' AND substr(created_at,1,4)=?",
            (str(current_year),),
        ).iloc[0]["n"]
    )

    daily_row = query_df("SELECT target_pages FROM daily_goals WHERE id = 1")
    current_daily_goal = int(daily_row.iloc[0]["target_pages"]) if not daily_row.empty else 30
    read_today_pages = int(
        query_df(
            "SELECT COALESCE(SUM(pages_read), 0) AS n FROM reading_logs WHERE read_date = ?",
            (today_iso,),
        ).iloc[0]["n"]
    )

    col_year, col_day = st.columns(2)

    with col_year:
        with st.container(border=True):
            st.subheader(f"🎯 {current_year}년 연간 독서 목표")
            with st.form("goal_form"):
                target = st.number_input("올해 완독 목표 (권)", min_value=1, max_value=500, value=current_goal, step=1)
                save_goal = st.form_submit_button("연간 목표 저장")
                if save_goal:
                    execute(
                        """INSERT INTO reading_goals(year, target_books) VALUES (?, ?)
                           ON CONFLICT(year) DO UPDATE SET target_books=excluded.target_books""",
                        (current_year, int(target)),
                    )
                    st.success("연간 목표를 저장했습니다.")
                    st.rerun()
            st.progress(
                min(completed_this_year / max(current_goal, 1), 1.0),
                text=f"완독 {completed_this_year}권 / 목표 {current_goal}권",
            )

    with col_day:
        with st.container(border=True):
            st.subheader(f"📅 오늘({today_iso})의 일간 독서 목표")
            with st.form("daily_goal_form"):
                daily_target = st.number_input(
                    "하루 목표 페이지 (쪽)", min_value=1, max_value=1000, value=current_daily_goal, step=5
                )
                save_daily = st.form_submit_button("일간 목표 저장")
                if save_daily:
                    execute(
                        """INSERT INTO daily_goals(id, target_pages) VALUES (1, ?)
                           ON CONFLICT(id) DO UPDATE SET target_pages=excluded.target_pages""",
                        (int(daily_target),),
                    )
                    st.success("일간 목표를 저장했습니다.")
                    st.rerun()
            st.progress(
                min(read_today_pages / max(current_daily_goal, 1), 1.0),
                text=f"오늘 읽은 페이지 {read_today_pages}쪽 / 목표 {current_daily_goal}쪽",
            )

    st.subheader("월별 독서 페이지")
    monthly = query_df(
        """SELECT substr(read_date,1,7) AS month, SUM(pages_read) AS pages
           FROM reading_logs GROUP BY substr(read_date,1,7) ORDER BY month"""
    )
    if monthly.empty:
        st.info("독서 기록을 저장하면 월별 통계가 표시됩니다.")
    else:
        fig = px.bar(
            monthly,
            x="month",
            y="pages",
            labels={"month": "월", "pages": "읽은 페이지"},
            title="월별 읽은 페이지 수",
        )
        st.plotly_chart(fig, use_container_width=True)

    col_chart1, col_chart2 = st.columns(2)
    with col_chart1:
        st.subheader("장르별 책 분포")
        genre_data = query_df(
            """SELECT CASE WHEN genre='' THEN '미분류' ELSE genre END AS genre,
                      COUNT(*) AS count
               FROM books GROUP BY genre ORDER BY count DESC"""
        )
        if genre_data.empty:
            st.caption("책을 등록하면 장르별 통계가 표시됩니다.")
        else:
            fig2 = px.pie(genre_data, names="genre", values="count", title="등록한 책의 장르 비율", hole=0.35)
            st.plotly_chart(fig2, use_container_width=True)

    with col_chart2:
        st.subheader("독서 상태")
        if books.empty:
            st.caption("책을 등록하면 독서 상태 차트가 표시됩니다.")
        else:
            status_data = books.groupby("status").size().reset_index(name="count")
            fig3 = px.bar(
                status_data,
                x="status",
                y="count",
                labels={"status": "독서 상태", "count": "책 수"},
                title="상태별 책 권수",
            )
            st.plotly_chart(fig3, use_container_width=True)

    st.divider()
    st.subheader("💾 독서 데이터 백업 (CSV 내보내기)")
    st.caption("클라우드 서버 재부팅으로 인한 데이터 초기화를 대비해 내 독서 기록을 파일로 저장할 수 있습니다.")
    dl1, dl2 = st.columns(2)
    if not books.empty:
        books_csv = books.to_csv(index=False).encode("utf-8-sig")
        dl1.download_button(
            label="📥 나의 책장 목록 다운로드 (.csv)",
            data=books_csv,
            file_name=f"booklog_books_{today_iso}.csv",
            mime="text/csv",
            use_container_width=True,
        )
    all_logs = query_df(
        """SELECT r.read_date AS 날짜, b.title AS 책제목, r.pages_read AS 읽은페이지,
                  r.reading_minutes AS 읽은시간_분, r.memo AS 메모
           FROM reading_logs r JOIN books b ON b.id = r.book_id
           ORDER BY r.read_date DESC"""
    )
    if not all_logs.empty:
        logs_csv = all_logs.to_csv(index=False).encode("utf-8-sig")
        dl2.download_button(
            label="📥 전체 독서 기록 다운로드 (.csv)",
            data=logs_csv,
            file_name=f"booklog_logs_{today_iso}.csv",
            mime="text/csv",
            use_container_width=True,
        )

st.divider()
st.caption("BOOKLOG · 나만의 독서 기록 공간")
