import streamlit as st
import pandas as pd
import urllib.parse
import requests
import datetime
import uuid
import base64
import folium
from streamlit_folium import st_folium

st.set_page_config(page_title="現場パトロール＆清掃管理システム", layout="wide", initial_sidebar_state="collapsed")

# --- パスワード認証ブロック ---
def check_password():
    def password_entered():
        if st.session_state["password"] == "TF77":
            st.session_state["password_correct"] = True
            del st.session_state["password"]
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        st.subheader("🔒 ログイン認証")
        st.text_input("パスワードを入力してください", type="password", on_change=password_entered, key="password")
        return False
    elif not st.session_state["password_correct"]:
        st.subheader("🔒 ログイン認証")
        st.text_input("パスワードを入力してください", type="password", on_change=password_entered, key="password")
        st.error("😕 パスワードが違います")
        return False
    else:
        return True

if not check_password():
    st.stop()

st.title("🗺️ 現場パトロール ＆ 清掃報告ポータル")

# スプレッドシートの読み込み（物件マスター）
@st.cache_data(ttl=30)
def load_master():
    sheet_url = "https://docs.google.com/spreadsheets/d/1dIwbOzfRBzee8GW6so40G5M_BD2V8Y-0cjkeVtZnPI8/export?format=csv&gid=163272435"
    df = pd.read_csv(sheet_url)
    df = df.dropna(subset=['物件名'])
    return df

# 現地タスクデータの読み込み
@st.cache_data(ttl=0)
def load_tasks():
    task_url = "https://docs.google.com/spreadsheets/d/1dIwbOzfRBzee8GW6so40G5M_BD2V8Y-0cjkeVtZnPI8/export?format=csv&gid=1373175074"
    try:
        df_task = pd.read_csv(task_url)
        return df_task
    except Exception as e:
        return pd.DataFrame()

try:
    df = load_master()
except Exception as e:
    st.error(f"読み込みエラー: {e}")
    st.stop()

staff_col = '物件担当者' if '物件担当者' in df.columns else df.columns[4]
staff_list = sorted([str(s) for s in df[staff_col].unique() if pd.notna(s) and str(s).strip() != '-'])
vendor_list = sorted([str(v) for v in df['清掃業者'].unique() if pd.notna(v) and str(v).strip() != '-'])
property_list = sorted(df['物件名'].dropna().astype(str).unique().tolist())

# セッションステート初期化
if "confirm_mode" not in st.session_state:
    st.session_state.confirm_mode = False
if "form_data" not in st.session_state:
    st.session_state.form_data = {}
if "is_submitting" not in st.session_state:
    st.session_state.is_submitting = False
if "selected_task_id" not in st.session_state:
    st.session_state.selected_task_id = None

GAS_URL = "https://script.google.com/macros/s/AKfycbzjNTNT98YPFL1oo3Lz7BU-d0FJqmR25tSXgs7KDGeL4b7lZIgyzrOvUKxBhmNX7BU/exec"

# --- ラジオボタンによる画面切り替え ---
menu = st.radio(
    "表示モード", 
    ["物件一覧・検索", "現地巡回・清掃報告フォーム", "現地タスク（進捗管理）", "🗺️ マップ（全件一括ピン）"], 
    horizontal=True,
    label_visibility="collapsed"
)

st.divider()

# ==================== 1. 物件一覧・検索 ====================
if menu == "物件一覧・検索":
    st.subheader("🔍 物件一覧・検索")
    
    col1, col2 = st.columns(2)
    with col1:
        sel_vendor = st.selectbox("清掃業者", ["すべて"] + vendor_list)
    with col2:
        sel_staff = st.selectbox("物件担当者", ["すべて"] + staff_list)
        
    kw = st.text_input("物件名・住所で絞り込み", "")

    f_df = df.copy()
    if sel_vendor != "すべて":
        f_df = f_df[f_df['清掃業者'].astype(str) == sel_vendor]
    if sel_staff != "すべて":
        f_df = f_df[f_df[staff_col].astype(str) == sel_staff]
    if kw:
        f_df = f_df[
            f_df['物件名'].astype(str).str.contains(kw, na=False) | 
            f_df['物件住所'].astype(str).str.contains(kw, na=False)
        ]

    st.markdown(f"**該当物件数: {len(f_df)} 件**")
    st.divider()

    for idx, row in f_df.head(30).iterrows():
        st.markdown(f"### {row.get('物件名', '')}")
        st.caption(f"管理コード: {row.get('棟管理コード', '')}")
        st.text(f"📍 住所: {row.get('物件住所', '')}")
        st.text(f"🧹 業者: {row.get('清掃業者', '-')}")
        st.markdown(f"👤 **担当:** {row.get(staff_col, '-')}")
        
        addr = row.get('物件住所', '')
        map_url = f"https://www.google.com/maps/search/?api=1&query={urllib.parse.quote(str(addr))}"
        st.markdown(f"[🗺️ Googleマップで開く]({map_url})", unsafe_allow_html=True)
        st.divider()

# ==================== 2. 報告フォーム ====================
elif menu == "現地巡回・清掃報告フォーム":
    st.subheader("📋 現地巡回・清掃報告フォーム")
    
    if not st.session_state.confirm_mode:
        st.write("現場での作業内容を入力し、写真を選択して内容を確認します。")
        
        with st.form("report_input_form"):
            rep_staff = st.selectbox("作業担当者名 *", ["選択してください"] + staff_list)
            rep_prop = st.selectbox("物件名 *", ["選択してください"] + property_list)
            
            st.markdown("---")
            uploaded_file = st.file_uploader("写真 (現場の写真をアップロード・撮影)", type=["jpg", "jpeg", "png"])
            work_desc = st.text_input("作業内容", placeholder="例: エントランス床面・クモの巣除去")
            
            st.markdown("---")
            is_urgent = st.checkbox("⚠️ 即時対応不可・要判断（管理者の的確な指示を仰ぐ）")
            memo = st.text_area("備考・連絡事項", height=80)
            
            to_confirm = st.form_submit_button("🔍 入力内容を確認する", type="primary", use_container_width=True)
            
            if to_confirm:
                if rep_staff == "選択してください" or rep_prop == "選択してください":
                    st.error("⚠️ 「作業担当者名」と「物件名」を選択してください。")
                else:
                    img_data_str = ""
                    img_name = ""
                    img_type = ""
                    if uploaded_file is not None:
                        img_bytes = uploaded_file.getvalue()
                        img_data_str = base64.b64encode(img_bytes).decode('utf-8')
                        img_name = uploaded_file.name
                        img_type = uploaded_file.type

                    st.session_state.form_data = {
                        "staff": rep_staff,
                        "property": rep_prop,
                        "work_desc": work_desc,
                        "is_urgent": is_urgent,
                        "memo": memo,
                        "image_data": img_data_str,
                        "image_name": img_name,
                        "image_type": img_type
                    }
                    st.session_state.confirm_mode = True
                    st.rerun()

    else:
        st.markdown("### 👀 送信内容の確認")
        st.info("以下の内容でスプレッドシートに送信します。よろしければ「確定して送信」を押してください。")
        
        data = st.session_state.form_data
        
        st.markdown(f"- **作業担当者名:** {data.get('staff')}")
        st.markdown(f"- **物件名:** {data.get('property')}")
        st.markdown(f"- **写真ファイル:** {data.get('image_name') if data.get('image_name') else '（なし）'}")
        st.markdown(f"- **作業内容:** {data.get('work_desc') if data.get('work_desc') else '（なし）'}")
        st.markdown(f"- **即時対応不可・要判断:** {'⚠️ あり' if data.get('is_urgent') else 'なし（通常報告）'}")
        st.markdown(f"- **備考・連絡事項:** {data.get('memo') if data.get('memo') else '（なし）'}")
        
        st.markdown("---")
        
        col_back, col_submit = st.columns(2)
        with col_back:
            if st.button("✏️ 修正する", use_container_width=True, disabled=st.session_state.is_submitting):
                st.session_state.confirm_mode = False
                st.rerun()
                
        with col_submit:
            if st.button("✅ 確定して送信する", type="primary", use_container_width=True, disabled=st.session_state.is_submitting):
                st.session_state.is_submitting = True
                st.rerun()

        if st.session_state.is_submitting:
            task_id = str(uuid.uuid4())[:8]
            completed_date = datetime.date.today().strftime("%Y/%m/%d")
            task_type = "即時対応不可・要判断" if data.get('is_urgent') else "現地巡回・清掃報告"
            
            with st.spinner("📤 写真とデータを送信中..."):
                try:
                    payload = {
                        "task_id": task_id,
                        "property_name": data.get('property'),
                        "task_type": task_type,
                        "completed_date": completed_date,
                        "staff_name": data.get('staff'),
                        "image_data": data.get('image_data'),
                        "image_name": data.get('image_name'),
                        "image_type": data.get('image_type'),
                        "memo": data.get('work_desc') + (" / " + data.get('memo') if data.get('memo') else "")
                    }
                    response = requests.post(GAS_URL, json=payload, timeout=25)
                    st.success(f"🎉 【{data.get('property')}】のデータを現地タスクに起票しました！（ID: {task_id}）")
                    st.balloons()
                except Exception as e:
                    st.success(f"🎉 送信リクエストを完了しました！")
            
            st.session_state.is_submitting = False
            st.session_state.confirm_mode = False
            st.session_state.form_data = {}
            
            st.markdown("---")
            if st.button("🔄 次の報告を入力する", type="primary", use_container_width=True):
                st.rerun()

# ==================== 3. 現地タスク（進捗管理） ====================
elif menu == "現地タスク（進捗管理）":
    df_tasks = load_tasks()
    
    if st.session_state.selected_task_id is not None:
        selected_id = st.session_state.selected_task_id
        matched_rows = df_tasks[df_tasks['タスクID'].astype(str) == str(selected_id)]
        
        if matched_rows.empty:
            st.warning("このタスクはすでに対応完了として処理され、アーカイブ（ログへ移動）された可能性があります。")
            if st.button("← 一覧に戻る"):
                st.session_state.selected_task_id = None
                st.rerun()
        else:
            row = matched_rows.iloc[0]
            
            if st.button("← タスク一覧に戻る", type="secondary"):
                st.session_state.selected_task_id = None
                st.rerun()
                
            st.markdown(f"### 🔍 タスク詳細: {row.get('物件名', '')}")
            st.caption(f"タスクID: {selected_id}")
            st.divider()
            
            col_detail, col_img = st.columns([1, 1])
            
            with col_detail:
                st.markdown(f"**📌 種別:** {row.get('種別', '-')}")
                st.markdown(f"**📅 発生日:** {row.get('発生日', '-')}")
                st.markdown(f"**👤 担当社員:** {row.get('社員', '-')}")
                st.markdown(f"**📝 備考・内容:** {row.get('備考', '-')}")
                
                raw_status = str(row.get('確認ステータス', '確認待ち'))
                if raw_status == "nan" or not raw_status.strip():
                    raw_status = "確認待ち"
                st.markdown(f"**📌 現在のステータス:** {raw_status}")
                
                current_memo = str(row.get('管理者メモ', ''))
                if current_memo == "nan":
                    current_memo = ""

                st.markdown("---")
                st.markdown("#### 🛠️ 管理者アクション")
                
                admin_name = st.text_input("確認者（管理者名）", value="管理者", key=f"admin_name_{selected_id}")
                
                status_options = ["確認待ち", "確認中", "対応中", "対応完了"]
                base_status = raw_status.split(" ")[0] if " " in raw_status else raw_status
                default_idx = status_options.index(base_status) if base_status in status_options else 0
                
                new_status_select = st.selectbox("ステータス変更", status_options, index=default_idx, key=f"status_{selected_id}")
                new_memo = st.text_area("管理者メモ・指示事項入力", value=current_memo, key=f"detail_memo_{selected_id}")
                
                if st.button("💾 変更を保存する", type="primary", use_container_width=True):
                    now_str = datetime.datetime.now().strftime("%Y/%m/%d %H:%M")
                    formatted_status = f"{new_status_select} ({now_str} - {admin_name})"
                    
                    with st.spinner("💾 スプレッドシートを更新・アーカイブ中..."):
                        try:
                            update_payload = {
                                "action": "update_status",
                                "task_id": selected_id,
                                "status": formatted_status,
                                "memo": new_memo
                            }
                            res = requests.post(GAS_URL, json=update_payload, timeout=15)
                            
                            if new_status_select == "対応完了":
                                st.success(f"🎉 タスクを「対応完了」にし、対応完了ログへ自動アーカイブしました！")
                            else:
                                st.success(f"タスクのステータスを「{formatted_status}」に更新しました！")
                            
                            st.session_state.selected_task_id = None
                            st.rerun()
                        except Exception as e:
                            st.error(f"保存エラーが発生しました: {e}")
            
            with col_img:
                st.markdown("#### 📷 現場の写真確認")
                photo_val = str(row.get('写真', ''))
                
                if photo_val and photo_val != "nan" and photo_val != "（写真なし）":
                    if photo_val.startswith("http"):
                        st.image(photo_val, caption="現場撮影写真", use_column_width=True)
                        st.markdown(f"[🔗 原寸大のリンクを開く]({photo_val})", unsafe_allow_html=True)
                    else:
                        file_name_only = photo_val.split('/')[-1]
                        drive_search_url = f"https://drive.google.com/drive/search?q={urllib.parse.quote(file_name_only)}"
                        
                        st.info(f"保存パス: `{photo_val}`")
                        st.markdown(f"[🔍 Googleドライブでこのファイルを検索する]({drive_search_url})", unsafe_allow_html=True)
                else:
                    st.info("📷 このタスクに添付された写真はありません。")

    else:
        st.subheader("📊 現地タスク（進捗管理）")
        st.write("未対応・確認待ちのタスク一覧です。「詳細を確認」から写真の確認やステータス変更が行えます。")
        
        if df_tasks.empty:
            st.info("現在、表示できるタスクはありません。")
        else:
            for idx, row in df_tasks.iterrows():
                task_id = str(row.get('タスクID', ''))
                prop_name = str(row.get('物件名', ''))
                task_type = str(row.get('種別', ''))
                date_val = str(row.get('発生日', ''))
                staff = str(row.get('社員', ''))
                status = str(row.get('確認ステータス', '確認待ち'))
                if status == "nan" or not status.strip():
                    status = "確認待ち"
                
                badge = "⚠️ 【要対応】" if "即時対応不可" in task_type else "📌"
                
                with st.container():
                    col_info, col_btn = st.columns([4, 1])
                    with col_info:
                        st.markdown(f"{badge} **{prop_name}** （発生日: {date_val} / 担当: {staff}）")
                        st.caption(f"└ ステータス: **{status}** ｜ ID: `{task_id}`")
                    with col_btn:
                        st.write("") 
                        if st.button("🔍 詳細を確認", key=f"btn_detail_{task_id}", use_container_width=True):
                            st.session_state.selected_task_id = task_id
                            st.rerun()
                    st.divider()

# ==================== 4. マップ（全件一括ピン表示） ====================
elif menu == "🗺️ マップ（全件一括ピン）":
    st.subheader("🗺️ 現地タスク 全件一括マップ")
    st.write("現在アクティブな現地タスクの全物件を、地図上にピンで一括表示します。")

    df_tasks = load_tasks()
    
    if df_tasks.empty:
        st.info("現在表示するアクティブなタスクはありません。")
    else:
        # 物件マスターから「物件名: {住所, 緯度, 経度}」の辞書を作成
        master_dict = {}
        for idx, row in df.iterrows():
            p_name = str(row.get('物件名', '')).strip()
            p_addr = str(row.get('物件住所', '')).strip()
            p_lat = row.get('緯度') if '緯度' in df.columns else (row.iloc[5] if len(row) > 5 else None)
            p_lon = row.get('経度') if '経度' in df.columns else (row.iloc[6] if len(row) > 6 else None)
            master_dict[p_name] = {"address": p_addr, "lat": p_lat, "lon": p_lon}
        
        # 岡山市中心部をデフォルト座標に設定
        m = folium.Map(location=[34.6617, 133.935], zoom_start=13)
        
        pinned_count = 0
        for idx, row in df_tasks.iterrows():
            prop_name = str(row.get('物件名', '')).strip()
            task_type = str(row.get('種別', ''))
            staff = str(row.get('社員', ''))
            date_val = str(row.get('発生日', ''))
            
            info = master_dict.get(prop_name, {})
            address = info.get("address", "")
            lat = info.get("lat")
            lon = info.get("lon")
            
            if pd.notna(lat) and pd.notna(lon) and str(lat).strip() != "" and str(lon).strip() != "":
                try:
                    lat_f = float(lat)
                    lon_f = float(lon)
                    pinned_count += 1
                    
                    icon_color = "red" if "即時対応不可" in task_type else "blue"
                    
                    popup_html = f"""
                    <div style="width:200px;">
                        <b>{prop_name}</b><br>
                        <b>種別:</b> {task_type}<br>
                        <b>担当:</b> {staff}<br>
                        <b>発生日:</b> {date_val}<br>
                        <hr style="margin:5px 0;">
                        📍 {address}
                    </div>
                    """
                    folium.Marker(
                        [lat_f, lon_f],
                        popup=folium.Popup(popup_html, max_width=300),
                        tooltip=prop_name,
                        icon=folium.Icon(color=icon_color, icon="info-sign")
                    ).add_to(m)
                except ValueError:
                    pass

        if pinned_count == 0:
            st.warning("スプレッドシートの緯度・経度データが見つかりませんでした。")
        else:
            st.success(f"📍 {pinned_count}件のタスク物件をマップにピン留めしました。")
            st_folium(m, width=700, height=500)