from datetime import datetime, date, timedelta
import json
import pandas as pd
import requests
import streamlit as st

st.set_page_config(page_title="管理替え・進行管理ポータル", layout="wide")

# ==========================================
# 🔐 簡易ログイン認証
# ==========================================
def check_password():
    """パスワード認証を行う関数"""
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    if st.session_state.authenticated:
        return True

    _, col_center, _ = st.columns([1, 2, 1])
    with col_center:
        st.markdown("### 🔒 ログイン認証")
        password = st.text_input("パスワードを入力してください", type="password")
        
        if st.button("ログイン", use_container_width=True):
            if password == "PM77":
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("パスワードが間違っています。")
    return False

if not check_password():
    st.stop()

# ==========================================
# 🏠 メインアプリケーション
# ==========================================
GAS_URL = "https://script.google.com/macros/s/AKfycbzADsde-SbZ_tmc4_p2lM7HjRLiuCqyDfD6v_deho-siZKQOhky8UC_OldMtLTxJ2PG/exec"


@st.cache_data(ttl=300)
def fetch_data(sheet_name="引き継ぎ書"):
  try:
    url = f"{GAS_URL}?sheet={sheet_name}"
    res = requests.get(url)
    return res.json()
  except Exception as e:
    st.error(f"データ取得エラー ({sheet_name}): {e}")
    return {"schema": [], "headers": [], "data": []}


st.title("🏠 管理替え・進行管理ポータル")

mode = st.radio(
    "操作モード",
    ["📋 引き継ぎ書・管理", "🏁 管理終了案件", "🔄 オーナーチェンジ案件", "➕ 新規物件追加", "⚙️ 部署別・進捗ステータスビュー"],
    horizontal=True,
)


def parse_fixed_date(val):
  if val is None:
    return None
  if isinstance(val, (int, float)):
    if val < 10000:
      return None
    try:
      base_date = date(1899, 12, 30)
      return base_date + timedelta(days=int(val))
    except Exception:
      pass

  v_str = str(val).strip()
  if v_str in ["-", "", "未選択", "nan", "None", "未定"]:
    return None

  if v_str.isdigit():
    val_int = int(v_str)
    if val_int < 10000:
      return None
    try:
      base_date = date(1899, 12, 30)
      return base_date + timedelta(days=val_int)
    except Exception:
      pass

  try:
    if "T" in v_str:
      clean_iso = v_str.replace("Z", "")
      dt = datetime.fromisoformat(clean_iso)
      dt = dt + timedelta(hours=9)
      return dt.date()

    v_str = v_str.replace("-", "/")
    parts = v_str.split("/")
    if len(parts) == 3:
      return date(int(parts[0]), int(parts[1]), int(parts[2]))
  except Exception:
    pass
  return None


# 🌟 保存確認用のモーダルダイアログ
@st.dialog("📋 変更内容の確認")
def show_confirm_dialog(property_name, selected_row_id, edited_payload, target_row, sheet_name="引き継ぎ書"):
    st.markdown(f"## 🏠 {property_name}")
    st.markdown(f"**対象行番号**: {selected_row_id}")
    st.markdown("---")
    
    validated_payload = {}
    for k, v in edited_payload.items():
        if v is None or str(v).strip() == "":
            validated_payload[k] = "済"
        else:
            validated_payload[k] = v

    st.markdown("以下の内容で変更を保存します。内容を確認してください。")

    diff_items = []
    for k, new_v in validated_payload.items():
        old_v = str(target_row.get(k, "")).strip()
        if old_v in ["", "-", "未選択", "None", "nan"]:
            old_v = "未"
        if new_v != old_v:
            diff_items.append({"title": k, "old": old_v, "new": new_v})

    if diff_items:
        st.markdown("### 🔍 変更される項目")
        for item in diff_items:
            cols = st.columns([2, 3, 3])
            with cols[0]:
                st.markdown(f"**{item['title']}**")
            with cols[1]:
                st.markdown(f"変更前: <span style='color: #ff9800;'>{item['old']}</span>", unsafe_allow_html=True)
            with cols[2]:
                st.markdown(f"変更後: <span style='color: #4caf50;'>**{item['new']}**</span>", unsafe_allow_html=True)
            st.markdown("")
    else:
        st.info("変更された項目はありません。")

    st.markdown("---")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("❌ キャンセル", use_container_width=True):
            st.rerun()
    with c2:
        if st.button("🚀 この内容で保存する", type="primary", use_container_width=True):
            payload = {
                "action": "update",
                "sheet": sheet_name,
                "rowId": selected_row_id,
                "payload": validated_payload,
            }
            try:
              res = requests.post(GAS_URL, json=payload)
              if res.status_code == 200:
                st.success("正常に更新されました！")
                st.cache_data.clear()
                st.rerun()
              else:
                st.error("更新に失敗しました。")
            except Exception as e:
              st.error(f"通信エラー: {e}")


# ==========================================
# 📋 モード1：引き継ぎ書・管理
# ==========================================
if mode == "📋 引き継ぎ書・管理":
  response_data = fetch_data("引き継ぎ書")
  schema = response_data.get("schema", [])
  data = response_data.get("data", [])

  if data:
    filtered_data = []
    for row in data:
      filtered_data.append(row)

    col_selectors, col_table = st.columns([4, 6])

    with col_selectors:
      st.markdown("### 🔍 検索・フィルター選択")
      
      def get_sort_key(row):
        date_val = parse_fixed_date(row.get("集金開始月", ""))
        if date_val:
          return (0, date_val)
        return (1, date.max)

      sorted_filtered_data = sorted(filtered_data, key=get_sort_key)
      
      property_options = ["未選択（物件を選んでください）"]
      property_map = {}
      for row in sorted_filtered_data:
        p_name = str(row.get("物件名称", row.get("物件名", "（物件名未設定）"))).strip()
        raw_date = row.get("集金開始月", "")
        parsed_d = parse_fixed_date(raw_date)
        date_str = parsed_d.strftime("%Y/%m/%d") if parsed_d else (str(raw_date) if raw_date else "日付未設定")
        
        label = f"{p_name} （集金開始月: {date_str}）"
        property_options.append(label)
        property_map[label] = row

      selected_prop_label = st.selectbox(
          "🏠 物件を選択（日付順）",
          property_options,
          key="direct_property_select_hiki"
      )

      available_depts = sorted(list(set(s.get("department", "") for s in schema if s.get("department") and s.get("department") != "総合")))
      dep_options = ["すべて（総合）"] + available_depts

      filter_dep = st.selectbox(
          "📂 部署を選択",
          dep_options,
          key="filter_dep_select_hiki"
      )

    if filter_dep != "すべて（総合）":
      target_schema = [s for s in schema if s.get("department") == filter_dep or s.get("department") == "総合"]
    else:
      target_schema = schema

    with col_table:
      st.markdown(f"### 📊 対象データ一覧（全 {len(filtered_data)} 件）")

      display_data = []
      for row in filtered_data:
        new_row = row.copy()
        for k, v in new_row.items():
          if k in ["管理契約開始日", "集金開始月"] and v:
            fixed_date = parse_fixed_date(v)
            if fixed_date:
              new_row[k] = fixed_date.strftime("%Y/%m/%d")
          if k != "_rowId" and (v is None or str(v).strip() in ["", "-", "未選択", "None", "nan"]):
            new_row[k] = "未"
        display_data.append(new_row)

      df_display = pd.DataFrame(display_data)

      valid_titles = [s["title"] for s in target_schema]
      columns_to_show = ["_rowId"] + [t for t in df_display.columns if t != "_rowId"]
      
      seen = set()
      unique_columns_to_show = []
      for c in columns_to_show:
        if c not in seen and c in df_display.columns:
          seen.add(c)
          unique_columns_to_show.append(c)

      df_display_filtered = df_display[unique_columns_to_show]

      st.dataframe(
          df_display_filtered,
          use_container_width=True,
          height=250,
          hide_index=True,
      )

    st.markdown("---")

    if selected_prop_label == "未選択（物件を選んでください）":
      st.info("👆 左上のセレクトボックスから物件を選択すると、ここに詳細な編集フォーム（4列表示）が展開されます。")
    else:
      target_row = property_map[selected_prop_label]
      selected_row_id = target_row["_rowId"]
      property_name = str(target_row.get("物件名称", target_row.get("物件名", "（物件名未設定）"))).strip()
      if not property_name:
        property_name = "（物件名未設定）"

      head_col1, head_col3 = st.columns([4, 1])

      with head_col1:
        st.subheader(f"✏️ 選択中：{property_name} （行番号 {selected_row_id}）")

      with head_col3:
        top_save_clicked = st.button(
            "💾 変更を保存", type="primary", use_container_width=True, key="save_hiki"
        )

      form_version_key = f"row_{selected_row_id}_dep_{filter_dep}"

      with st.container(height=600):
        edited_payload = {}

        grouped_items = {}
        for s in target_schema:
          g = s["group"]
          if g not in grouped_items:
            grouped_items[g] = []
          grouped_items[g].append(s)

        for group_name, items in grouped_items.items():
          st.markdown(f"### 📌 【 {group_name} 】")
          form_cols = st.columns(4)

          for i, s in enumerate(items):
            title = s["title"]
            raw_val = target_row.get(title, "")
            options = s["options"]
            unique_key = f"{form_version_key}_{group_name}_{i}_{title}"

            target_col = form_cols[i % 4]
            with target_col:
              label_col, status_col = st.columns([2, 1])
              with label_col:
                is_mi_form = str(raw_val).strip() in ["", "-", "未選択", "None", "nan", "未"]
                if is_mi_form:
                  st.markdown(f"<span style='color: #ffeb3b; font-size: 0.9em;'>**{title}**</span>", unsafe_allow_html=True)
                else:
                  st.markdown(f"<span style='font-size: 0.9em;'>**{title}**</span>", unsafe_allow_html=True)

              with status_col:
                current_status = "済" if str(raw_val).strip() not in ["", "-", "未選択", "None", "nan", "未"] else "未"
                status_choice = st.radio(
                    f"状態_{unique_key}",
                    ["未", "済"],
                    index=0 if current_status == "未" else 1,
                    horizontal=True,
                    key=f"status_{unique_key}",
                    label_visibility="collapsed"
                )

              if title in ["管理契約開始日", "集金開始月"]:
                if status_choice == "未":
                  edited_payload[title] = "未"
                else:
                  parsed_d = parse_fixed_date(raw_val)
                  d_default = parsed_d if parsed_d else date.today()
                  chosen_date = st.date_input(
                      f"{title} (日付)",
                      value=d_default,
                      key=f"date_{unique_key}",
                      label_visibility="collapsed",
                  )
                  edited_payload[title] = chosen_date.strftime("%Y/%m/%d")

              elif len(options) > 0:
                if status_choice == "未":
                  edited_payload[title] = "未"
                else:
                  current_val = str(raw_val).strip()
                  if current_val in ["-", "", "未選択", "未"]:
                    current_val = options[0]

                  try:
                    default_idx = options.index(current_val)
                  except ValueError:
                    default_idx = 0

                  chosen_radio = st.radio(
                      f"{title} (選択)",
                      options,
                      index=default_idx,
                      key=f"rad_{unique_key}",
                      horizontal=True,
                      label_visibility="collapsed",
                  )
                  edited_payload[title] = chosen_radio

              else:
                if status_choice == "未":
                  edited_payload[title] = "未"
                else:
                  typed_val = st.text_input(
                      f"{title} (自由記述)",
                      value=str(raw_val).strip() if raw_val and str(raw_val) != "未" else "",
                      placeholder="入力",
                      key=f"txt_{unique_key}",
                      label_visibility="collapsed",
                  )
                  edited_payload[title] = typed_val.strip()

          st.markdown("---")

        if top_save_clicked:
          show_confirm_dialog(property_name, selected_row_id, edited_payload, target_row, "引き継ぎ書")
  else:
    st.info("データがありません。")


# ==========================================
# 🏁 モード2：管理終了案件
# ==========================================
elif mode == "🏁 管理終了案件":
  response_data = fetch_data("管理終了")
  schema = response_data.get("schema", [])
  data = response_data.get("data", [])

  st.subheader("🏁 管理終了案件 管理モード")
  if data:
    def get_kanryo_sort_key(row):
      d = parse_fixed_date(row.get("終了日", "")) or parse_fixed_date(row.get("終了予定日", ""))
      if d:
        return (0, d)
      return (1, date.max)

    sorted_data = sorted(data, key=get_kanryo_sort_key)
    prop_options = ["未選択（物件を選んでください）"]
    prop_map = {}

    for row in sorted_data:
      # 🌟 「物件名」と「物件名称」の両方に対応
      p_name = str(row.get("物件名", row.get("物件名称", "（物件名未設定）"))).strip()
      end_d = parse_fixed_date(row.get("終了日", ""))
      if not end_d:
        end_d = parse_fixed_date(row.get("終了予定日", ""))
      
      date_str = end_d.strftime("%Y/%m/%d") if end_d else "未定"
      label = f"{p_name} （終了日: {date_str}）"
      prop_options.append(label)
      prop_map[label] = row

    col_s1, col_s2 = st.columns([4, 6])
    with col_s1:
      selected_label = st.selectbox("🏠 管理終了物件を選択", prop_options, key="select_kanryo")

    if selected_label != "未選択（物件を選んでください）":
      target_row = prop_map[selected_label]
      row_id = target_row["_rowId"]
      p_name = str(target_row.get("物件名", target_row.get("物件名称", ""))).strip()

      with col_s2:
        st.markdown(f"**選択中**: {p_name} (行番号: {row_id})")
        save_btn = st.button("💾 管理終了データを保存", type="primary", key="save_kanryo")

      with st.container(height=500):
        edited_payload = {}
        grouped = {}
        for s in schema:
          g = s.get("group", "基本情報")
          if g not in grouped:
            grouped[g] = []
          grouped[g].append(s)

        if not schema:
          items = [{"title": k, "options": [], "group": "基本情報"} for k in target_row.keys() if k != "_rowId"]
          grouped = {"基本情報": items}

        for g_name, items in grouped.items():
          st.markdown(f"### 📌 【 {g_name} 】")
          f_cols = st.columns(4)
          for i, s in enumerate(items):
            title = s["title"]
            raw_val = target_row.get(title, "")
            opts = s.get("options", [])
            u_key = f"kanryo_{row_id}_{i}_{title}"

            with f_cols[i % 4]:
              st.markdown(f"<span style='font-size: 0.9em;'>**{title}**</span>", unsafe_allow_html=True)
              if len(opts) > 0:
                cur = str(raw_val).strip()
                idx = opts.index(cur) if cur in opts else 0
                val = st.selectbox(title, opts, index=idx, key=f"sel_{u_key}", label_visibility="collapsed")
                edited_payload[title] = val
              elif "日" in title or "月" in title:
                parsed = parse_fixed_date(raw_val)
                d_val = parsed if parsed else date.today()
                chosen_d = st.date_input(title, value=d_val, key=f"date_{u_key}", label_visibility="collapsed")
                edited_payload[title] = chosen_d.strftime("%Y/%m/%d")
              else:
                txt = st.text_input(title, value=str(raw_val) if raw_val and str(raw_val)!="nan" else "", key=f"txt_{u_key}", label_visibility="collapsed")
                edited_payload[title] = txt.strip()
          st.markdown("---")

        if save_btn:
          show_confirm_dialog(p_name, row_id, edited_payload, target_row, "管理終了")
    else:
      st.info("👆 上のセレクトボックスから管理終了物件を選択してください。")
  else:
    st.info("「管理終了」シートにデータがありません。")


# ==========================================
# 🔄 モード3：オーナーチェンジ案件
# ==========================================
elif mode == "🔄 オーナーチェンジ案件":
  response_data = fetch_data("オーナーチェンジ")
  schema = response_data.get("schema", [])
  data = response_data.get("data", [])

  st.subheader("🔄 オーナーチェンジ案件 管理モード")
  if data:
    def get_oc_sort_key(row):
      d = parse_fixed_date(row.get("決済日", ""))
      if d:
        return (0, d)
      return (1, date.max)

    sorted_data = sorted(data, key=get_oc_sort_key)
    prop_options = ["未選択（物件を選んでください）"]
    prop_map = {}

    for row in sorted_data:
      # 🌟 「物件名」と「物件名称」の両方に対応
      p_name = str(row.get("物件名", row.get("物件名称", "（物件名未設定）"))).strip()
      pay_d = parse_fixed_date(row.get("決済日", ""))
      date_str = pay_d.strftime("%Y/%m/%d") if pay_d else "未定"
      
      label = f"{p_name} （決済日: {date_str}）"
      prop_options.append(label)
      prop_map[label] = row

    col_s1, col_s2 = st.columns([4, 6])
    with col_s1:
      selected_label = st.selectbox("🏠 オーナーチェンジ物件を選択", prop_options, key="select_oc")

    if selected_label != "未選択（物件を選んでください）":
      target_row = prop_map[selected_label]
      row_id = target_row["_rowId"]
      p_name = str(target_row.get("物件名", target_row.get("物件名称", ""))).strip()

      with col_s2:
        st.markdown(f"**選択中**: {p_name} (行番号: {row_id})")
        save_btn = st.button("💾 オーナーチェンジデータを保存", type="primary", key="save_oc")

      with st.container(height=500):
        edited_payload = {}
        grouped = {}
        for s in schema:
          g = s.get("group", "基本情報")
          if g not in grouped:
            grouped[g] = []
          grouped[g].append(s)

        if not schema:
          items = [{"title": k, "options": [], "group": "基本情報"} for k in target_row.keys() if k != "_rowId"]
          grouped = {"基本情報": items}

        for g_name, items in grouped.items():
          st.markdown(f"### 📌 【 {g_name} 】")
          f_cols = st.columns(4)
          for i, s in enumerate(items):
            title = s["title"]
            raw_val = target_row.get(title, "")
            opts = s.get("options", [])
            u_key = f"oc_{row_id}_{i}_{title}"

            with f_cols[i % 4]:
              st.markdown(f"<span style='font-size: 0.9em;'>**{title}**</span>", unsafe_allow_html=True)
              if len(opts) > 0:
                cur = str(raw_val).strip()
                idx = opts.index(cur) if cur in opts else 0
                val = st.selectbox(title, opts, index=idx, key=f"sel_{u_key}", label_visibility="collapsed")
                edited_payload[title] = val
              elif "日" in title or "月" in title:
                parsed = parse_fixed_date(raw_val)
                d_val = parsed if parsed else date.today()
                chosen_d = st.date_input(title, value=d_val, key=f"date_{u_key}", label_visibility="collapsed")
                edited_payload[title] = chosen_d.strftime("%Y/%m/%d")
              else:
                txt = st.text_input(title, value=str(raw_val) if raw_val and str(raw_val)!="nan" else "", key=f"txt_{u_key}", label_visibility="collapsed")
                edited_payload[title] = txt.strip()
          st.markdown("---")

        if save_btn:
          show_confirm_dialog(p_name, row_id, edited_payload, target_row, "オーナーチェンジ")
    else:
      st.info("👆 上のセレクトボックスからオーナーチェンジ物件を選択してください。")
  else:
    st.info("「オーナーチェンジ」シートにデータがありません。")


# ==========================================
# ➕ 新規物件追加
# ==========================================
elif mode == "➕ 新規物件追加":
  st.subheader("➕ 新規物件の追加登録")
  st.info("※現在「引き継ぎ書」への新規追加機能が有効です。")


# ==========================================
# ⚙️ 部署別・進捗ステータスビュー
# ==========================================
elif mode == "⚙️ 部署別・進捗ステータスビュー":
  st.subheader("⚙️ 部署別・進捗ステータス確認モード")
  st.info("※サイドの機能は一覧画面に統合されました。")