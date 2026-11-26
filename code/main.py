
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import requests
from io import BytesIO
from urllib.parse import quote

# --------------------------------------------------
# 기본 설정
# --------------------------------------------------

st.set_page_config(
    page_title="연도별 수도권과 비수도권 학교의 재학생 차이",
    page_icon="🏫",
    layout="wide"
)

st.title("🏫 연도별 수도권과 비수도권 학교의 재학생 차이")
st.caption("2010년과 2026년 학교별 학생 수를 비교하는 데이터 분석")

OWNER = "jmj0125-data"
REPO = "st_project"
COMMIT = "7089ef486e3436ba181ae594cb2e0bd022b83fe6"

FOLDERS = {
    2010: "data/10년도",
    2026: "data/26년도"
}

REQUIRED_COLUMNS = [
    "시도교육청",
    "지역",
    "학교명",
    "설립구분",
    "1학년 학생수",
    "2학년 학생수",
    "3학년 학생수",
    "학생수(계)"
]

REGION_COLUMN = "지역구분"

# --------------------------------------------------
# 데이터 불러오기
# --------------------------------------------------

@st.cache_data(ttl=3600)
def load_github_files():

    api_url = (
        f"https://api.github.com/repos/{OWNER}/{REPO}"
        f"/git/trees/{COMMIT}?recursive=1"
    )

    response = requests.get(api_url, timeout=30)
    response.raise_for_status()

    tree = response.json()["tree"]

    all_data = {}

    for year, folder in FOLDERS.items():

        files = [
            item["path"]
            for item in tree
            if item["type"] == "blob"
            and item["path"].startswith(folder + "/")
            and item["path"].lower().endswith(
                (".csv", ".xlsx", ".xls")
            )
        ]

        if not files:
            raise ValueError(
                f"{year}년 폴더에서 CSV 또는 엑셀 파일을 찾지 못했습니다: {folder}"
            )

        frames = []

        for file_path in files:

            raw_url = (
                f"https://raw.githubusercontent.com/"
                f"{OWNER}/{REPO}/{COMMIT}/"
                f"{quote(file_path, safe='/')}"
            )

            file_response = requests.get(raw_url, timeout=60)
            file_response.raise_for_status()

            file_bytes = BytesIO(file_response.content)

            if file_path.lower().endswith(".csv"):

                df = None
                last_error = None

                for encoding in [
                    "utf-8-sig",
                    "cp949",
                    "euc-kr",
                    "utf-8"
                ]:
                    try:
                        file_bytes.seek(0)
                        df = pd.read_csv(
                            file_bytes,
                            encoding=encoding,
                            sep=None,
                            engine="python"
                        )
                        break
                    except Exception as e:
                        last_error = e

                if df is None:
                    raise ValueError(
                        f"{file_path} 읽기 실패: {last_error}"
                    )

            else:
                df = pd.read_excel(file_bytes)

            # 열 이름 공백 제거
            df.columns = df.columns.astype(str).str.strip()

            missing = [
                col for col in REQUIRED_COLUMNS
                if col not in df.columns
            ]

            if missing:
                raise ValueError(
                    f"{file_path}에 필요한 열이 없습니다: {missing}"
                )

            df = df[REQUIRED_COLUMNS].copy()
            df["원본파일"] = file_path

            frames.append(df)

        combined = pd.concat(frames, ignore_index=True)

        # 동일한 자료가 중복 수집된 경우 제거
        combined = combined.drop_duplicates(
            subset=REQUIRED_COLUMNS
        )

        combined["연도"] = year

        all_data[year] = combined

    return all_data


# --------------------------------------------------
# 데이터 전처리
# --------------------------------------------------

@st.cache_data
def prepare_data(data_dict):

    frames = []

    for year, df in data_dict.items():

        temp = df.copy()

        # 학생 수 숫자 변환
        student_columns = [
            "1학년 학생수",
            "2학년 학생수",
            "3학년 학생수",
            "학생수(계)"
        ]

        for col in student_columns:
            temp[col] = pd.to_numeric(
                temp[col]
                .astype(str)
                .str.replace(",", "", regex=False)
                .str.replace("명", "", regex=False)
                .str.strip()
                .replace(["", "-", "nan", "None"], np.nan),
                errors="coerce"
            )

        # 문자열 정리
        for col in [
            "시도교육청",
            "지역",
            "학교명",
            "설립구분"
        ]:
            temp[col] = (
                temp[col]
                .astype(str)
                .str.strip()
            )

        temp = temp.dropna(
            subset=["학생수(계)", "학교명", "시도교육청"]
        )

        # 수도권 / 비수도권 구분
        def classify_region(value):

            value = str(value)

            if any(x in value for x in [
                "서울", "경기", "인천"
            ]):
                return "수도권"

            return "비수도권"

        temp[REGION_COLUMN] = (
            temp["시도교육청"].apply(classify_region)
        )

        frames.append(temp)

    result = pd.concat(frames, ignore_index=True)

    # 학교 식별용 이름
    result["학교식별"] = (
        result["시도교육청"].astype(str) + " | " +
        result["지역"].astype(str) + " | " +
        result["학교명"].astype(str) + " | " +
        result["설립구분"].astype(str)
    )

    return result


# --------------------------------------------------
# 데이터 로딩 오류 처리
# --------------------------------------------------

try:
    with st.spinner("GitHub에서 2010년과 2026년 데이터를 불러오는 중입니다..."):
        raw_data = load_github_files()
        df = prepare_data(raw_data)

except Exception as e:
    st.error("데이터를 불러오는 중 오류가 발생했습니다.")
    st.exception(e)
    st.stop()


# --------------------------------------------------
# 데이터 확인
# --------------------------------------------------

st.success("2010년과 2026년 데이터 불러오기가 완료되었습니다.")

with st.expander("데이터 기본 정보 확인"):

    for year in [2010, 2026]:

        year_df = df[df["연도"] == year]

        st.write(f"### {year}년")

        col1, col2, col3 = st.columns(3)

        col1.metric("학교 수", f"{year_df['학교식별'].nunique():,}개")
        col2.metric("전체 재학생", f"{year_df['학생수(계)'].sum():,.0f}명")
        col3.metric("데이터 행 수", f"{len(year_df):,}개")


# --------------------------------------------------
# 수도권과 비수도권 산점도 및 회귀 분석
# --------------------------------------------------

st.divider()

st.header("1. 수도권과 비수도권 학생 수 변화")

st.write(
    "각 학교의 2010년과 2026년 학생 수를 산점도로 나타내고, "
    "연도와 학생 수 사이의 회귀 직선을 비교합니다."
)

region_colors = {
    "수도권": "#2878B5",
    "비수도권": "#E87532"
}

fig = go.Figure()

correlation_results = {}

for region in ["수도권", "비수도권"]:

    region_df = df[
        df[REGION_COLUMN] == region
    ].copy()

    if len(region_df) < 2:
        continue

    x = region_df["연도"].to_numpy(dtype=float)
    y = region_df["학생수(계)"].to_numpy(dtype=float)

    # 상관계수
    if np.std(x) > 0 and np.std(y) > 0:
        corr = np.corrcoef(x, y)[0, 1]
    else:
        corr = np.nan

    correlation_results[region] = corr

    # 산점도
    fig.add_trace(
        go.Scatter(
            x=x,
            y=y,
            mode="markers",
            name=f"{region} 학교",
            marker=dict(
                color=region_colors[region],
                size=6,
                opacity=0.45
            ),
            customdata=region_df[
                ["학교명", "시도교육청", "지역", "학생수(계)"]
            ].to_numpy(),
            hovertemplate=(
                "연도: %{x}년<br>"
                "학교: %{customdata[0]}<br>"
                "시도교육청: %{customdata[1]}<br>"
                "지역: %{customdata[2]}<br>"
                "학생 수: %{y:,.0f}명"
                "<extra></extra>"
            )
        )
    )

    # 회귀 직선
    slope, intercept = np.polyfit(x, y, 1)

    x_line = np.array([2010, 2026])
    y_line = slope * x_line + intercept

    fig.add_trace(
        go.Scatter(
            x=x_line,
            y=y_line,
            mode="lines",
            name=f"{region} 회귀 직선",
            line=dict(
                color=region_colors[region],
                width=4
            ),
            hovertemplate=(
                "연도: %{x}년<br>"
                "회귀 예측 학생 수: %{y:,.1f}명"
                "<extra></extra>"
            )
        )
    )

fig.update_layout(
    title="2010년과 2026년 수도권·비수도권 학교 학생 수 비교",
    xaxis_title="연도",
    yaxis_title="학생 수(명)",
    xaxis=dict(
        tickmode="array",
        tickvals=[2010, 2026],
        ticktext=["2010년", "2026년"]
    ),
    hovermode="closest",
    legend_title="지역 구분",
    height=650,
    template="plotly_white"
)

st.plotly_chart(fig, use_container_width=True)


# --------------------------------------------------
# 상관계수 표시
# --------------------------------------------------

st.subheader("상관계수 비교")

col1, col2 = st.columns(2)

for col, region in zip(
    [col1, col2],
    ["수도권", "비수도권"]
):

    value = correlation_results.get(region, np.nan)

    with col:
        if pd.notna(value):
            st.metric(
                f"{region} 상관계수",
                f"{value:.4f}"
            )
        else:
            st.metric(
                f"{region} 상관계수",
                "계산 불가"
            )

st.caption(
    "상관계수는 -1부터 1까지의 값을 가지며, "
    "1에 가까울수록 양의 상관관계, -1에 가까울수록 음의 상관관계를 의미합니다."
)


# --------------------------------------------------
# 회귀 분석 결과 표
# --------------------------------------------------

st.subheader("회귀 직선 분석 결과")

regression_rows = []

for region in ["수도권", "비수도권"]:

    part = df[df[REGION_COLUMN] == region]

    if len(part) < 2:
        continue

    x = part["연도"].to_numpy(dtype=float)
    y = part["학생수(계)"].to_numpy(dtype=float)

    slope, intercept = np.polyfit(x, y, 1)

    regression_rows.append({
        "지역 구분": region,
        "기울기(연간 변화량)": slope,
        "2010년 회귀 예측": slope * 2010 + intercept,
        "2026년 회귀 예측": slope * 2026 + intercept,
        "16년간 예측 변화량": slope * 16
    })

regression_df = pd.DataFrame(regression_rows)

st.dataframe(
    regression_df.style.format({
        "기울기(연간 변화량)": "{:,.2f}명",
        "2010년 회귀 예측": "{:,.2f}명",
        "2026년 회귀 예측": "{:,.2f}명",
        "16년간 예측 변화량": "{:,.2f}명"
    }),
    use_container_width=True,
    hide_index=True
)

st.caption(
    "회귀 직선은 각 연도에 속한 학교별 학생 수를 하나의 관측값으로 사용합니다. "
    "기울기는 학교별 관측값을 기준으로 한 연간 평균 변화 추세입니다."
)


# --------------------------------------------------
# 학교별 학생 수 비교
# --------------------------------------------------

st.divider()

st.header("2. 학교별 2010년과 2026년 학생 수 비교")

st.write(
    "학교를 선택하면 두 연도의 학생 수와 증감 인원을 확인할 수 있습니다."
)

# 두 연도 모두 존재하는 학교만 비교 대상으로 설정
school_year_counts = (
    df.groupby("학교식별")["연도"]
    .nunique()
)

available_schools = school_year_counts[
    school_year_counts == 2
].index.tolist()

if not available_schools:

    st.warning(
        "두 연도에 모두 존재하는 학교를 찾지 못했습니다. "
        "학교명이나 지역명이 변경되었는지 확인해 주세요."
    )

else:

    school_labels = {
        school: school
        for school in sorted(available_schools)
    }

    selected_schools = st.multiselect(
        "비교할 학교 선택",
        options=available_schools,
        format_func=lambda x: school_labels[x],
        placeholder="학교를 검색하거나 선택하세요."
    )

    if selected_schools:

        school_df = df[
            df["학교식별"].isin(selected_schools)
        ].copy()

        # 학교별, 연도별 학생 수
        pivot = school_df.pivot_table(
            index="학교식별",
            columns="연도",
            values="학생수(계)",
            aggfunc="sum"
        )

        pivot = pivot.reindex(columns=[2010, 2026])

        pivot = pivot.dropna(
            subset=[2010, 2026]
        )

        pivot["학생 수 증감"] = (
            pivot[2026] - pivot[2010]
        )

        pivot["증감률(%)"] = np.where(
            pivot[2010] != 0,
            pivot["학생 수 증감"] / pivot[2010] * 100,
            np.nan
        )

        result = pivot.reset_index()

        result = result.rename(columns={
            "학교식별": "학교",
            2010: "2010년 학생 수",
            2026: "2026년 학생 수"
        })

        st.dataframe(
            result.style.format({
                "2010년 학생 수": "{:,.0f}명",
                "2026년 학생 수": "{:,.0f}명",
                "학생 수 증감": "{:+,.0f}명",
                "증감률(%)": "{:+.2f}%"
            }),
            use_container_width=True,
            hide_index=True
        )

        # 전체 선택 학교 증감
        total_2010 = pivot[2010].sum()
        total_2026 = pivot[2026].sum()
        total_change = total_2026 - total_2010

        a, b, c = st.columns(3)

        a.metric(
            "2010년 학생 수 합계",
            f"{total_2010:,.0f}명"
        )

        b.metric(
            "2026년 학생 수 합계",
            f"{total_2026:,.0f}명"
        )

        c.metric(
            "학생 수 증감",
            f"{total_change:+,.0f}명"
        )

        # 선택 학교 비교 그래프
        compare_fig = go.Figure()

        compare_fig.add_trace(
            go.Bar(
                x=result["학교"],
                y=result["2010년 학생 수"],
                name="2010년"
            )
        )

        compare_fig.add_trace(
            go.Bar(
                x=result["학교"],
                y=result["2026년 학생 수"],
                name="2026년"
            )
        )

        compare_fig.update_layout(
            title="선택한 학교의 연도별 학생 수 비교",
            xaxis_title="학교",
            yaxis_title="학생 수(명)",
            barmode="group",
            template="plotly_white",
            height=550
        )

        st.plotly_chart(
            compare_fig,
            use_container_width=True
        )

    else:
        st.info(
            "위에서 비교할 학교를 선택해 주세요."
        )


# --------------------------------------------------
# 학년별 학생 수 비교
# --------------------------------------------------

st.divider()

st.header("3. 학년별 학생 수 변화")

grade_columns = [
    "1학년 학생수",
    "2학년 학생수",
    "3학년 학생수"
]

grade_summary = (
    df.groupby(["연도", REGION_COLUMN])[grade_columns]
    .mean()
    .reset_index()
)

grade_summary = grade_summary.rename(columns={
    "1학년 학생수": "1학년",
    "2학년 학생수": "2학년",
    "3학년 학생수": "3학년"
})

selected_region = st.selectbox(
    "학년별 비교 지역",
    ["수도권", "비수도권"]
)

grade_part = grade_summary[
    grade_summary[REGION_COLUMN] == selected_region
]

grade_fig = go.Figure()

for grade in ["1학년", "2학년", "3학년"]:

    grade_fig.add_trace(
        go.Bar(
            x=grade_part["연도"],
            y=grade_part[grade],
            name=grade
        )
    )

grade_fig.update_layout(
    title=f"{selected_region} 학교의 학년별 평균 학생 수",
    xaxis_title="연도",
    yaxis_title="평균 학생 수(명)",
    xaxis=dict(
        tickmode="array",
        tickvals=[2010, 2026],
        ticktext=["2010년", "2026년"]
    ),
    barmode="group",
    template="plotly_white",
    height=500
)

st.plotly_chart(
    grade_fig,
    use_container_width=True
)


# --------------------------------------------------
# 데이터 해석 안내
# --------------------------------------------------

st.divider()

st.header("4. 분석 시 유의사항")

st.markdown("""
- 수도권은 서울특별시, 경기도, 인천광역시로 구분합니다.
- 비수도권은 그 외 지역으로 구분합니다.
- 산점도의 한 점은 한 학교의 한 연도 학생 수를 의미합니다.
- 회귀 직선은 학교별 학생 수 관측값을 바탕으로 계산합니다.
- 학교별 증감 비교는 두 연도에 모두 존재하는 학교만 대상으로 합니다.
- 학교명이나 지역명이 바뀐 경우 동일 학교로 자동 연결되지 않을 수 있습니다.
- 학년별 그래프는 학교당 평균 학생 수를 나타냅니다.
- 이 분석은 2010년과 2026년 두 시점의 비교이므로, 중간 연도의 변화까지 설명하지는 않습니다.
""")

st.caption(
    "데이터 출처: jmj0125-data/st_project GitHub 저장소"
)

