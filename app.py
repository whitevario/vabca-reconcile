import streamlit as st
import pandas as pd
import plotly.express as px

import db
from parser import parse_txt_content, nama_bulan_tp
from excel_helper import to_excel, pivot_to_excel

# --- SET PAGE CONFIG (HANYA BOLEH 1 KALI) ---
st.set_page_config(page_title="VABCA Reconcile SBY1", page_icon="⚖️", layout="wide")
db.init_db()

# --- INISIALISASI SESSION STATE (WAJIB DI PALING ATAS) ---
if "uploader_key" not in st.session_state: 
    st.session_state.uploader_key = 0
if "upload_success" not in st.session_state: 
    st.session_state.upload_success = None
if "upload_error" not in st.session_state: 
    st.session_state.upload_error = None

# --- BLOKIR AKSES JIKA BELUM LOGIN / DOMAIN SALAH ---
if not st.user.is_logged_in:
    st.warning("🔒 Aplikasi ini hanya untuk internal Yayasan Yohannes Gabriel. Silakan login.")
    if st.button("Login dengan Google"):
        st.login("google")
    st.stop() # Hentikan aplikasi jika belum login

# --- CEK DOMAIN EMAIL ---
email_user = st.user.get("email", "")
if not email_user.endswith("@yohannesgabriel.org"):
    st.error(f"Akses Ditolak. Email {email_user} tidak diizinkan. Gunakan email @yohannesgabriel.org.")
    if st.button("Logout"):
        st.logout()
    st.stop() # Hentikan aplikasi jika domain salah

# --- JIKA LOLOS, TAMPILKAN TOMBOL LOGOUT DI SIDEBAR ---
with st.sidebar:
    st.write(f"Login sebagai: **{email_user}**")
    if st.button("Logout"):
        st.logout()

st.set_page_config(page_title="VABCA Reconcile", page_icon="⚖️", layout="wide")
db.init_db()
if "uploader_key" not in st.session_state: st.session_state.uploader_key = 0
if "upload_success" not in st.session_state: st.session_state.upload_success = None
if "upload_error" not in st.session_state: st.session_state.upload_error = None

# Proteksi Password (Opsional, hapus blok ini jika tidak ingin pakai password)
def check_password():
    if st.session_state.get("auth"): return True
    pwd = st.text_input("🔒 Masukkan Password", type="password")
    if pwd == st.secrets.get("password", {}).get("rahasia", "admin123"):
        st.session_state.auth = True
        return True
    elif pwd: st.error("Password salah")
    return False

# if not check_password(): st.stop() # <--- Buka komentar ini jika ingin pakai password

#st.title("⚖️ VABCA Reconcile PWK SURABAYA 1")

st.markdown(
    """
    <div style="display: flex; align-items: center; gap: 15px; margin-bottom: 20px;">
        <img src="https://raw.githubusercontent.com/whitevario/vabca-reconcile/main/maskot.png" width="60">
        <h1 style="margin: 0; padding: 0; color: #2c3e50;">VABCA Reconcile PWK SURABAYA 1</h1>
    </div>
    """,
    unsafe_allow_html=True
)

# Tampilkan info kuota di bawah judul
db_size = db.get_db_size_mb()
if db_size > 0:
    # Batas gratis Supabase adalah 500 MB
    sisa = 500 - db_size
    persen = (db_size / 500) * 100
    
    st.caption(f"💾 **Penggunaan Database:** {db_size:.2f} MB dari 500 MB ({persen:.1f}%). Sisa: {sisa:.2f} MB")
    
    # Beri peringatan jika sudah di atas 80%
    if persen > 80:
        st.warning("⚠️ Kuota database hampir penuh! Segera hapus data lama atau upgrade paket Supabase.")
###==        
st.markdown("👩‍💻 Created by **Tri**© Oct 2026 | *Sistem Pencocokkan RK VA & Data PIC*")
st.info("ℹ️ **DISCLAIMER:** This application is a personal tool for internal reconciliation. It is NOT an official enterprise system provided by the company. The user assumes full responsibility for the data.")

# ============================================================
# HELPER FUNCTIONS
# ============================================================
def enrich_df(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty: return df
    m_sekolah = db.load_master("master_sekolah").set_index("kode")["nama"].to_dict() if not db.load_master("master_sekolah").empty else {}
    m_bayar = db.load_master("master_bayar").set_index("kode")["nama"].to_dict() if not db.load_master("master_bayar").empty else {}
    m_kat = db.load_master("master_kategori").set_index("prefix_va")["kategori"].to_dict() if not db.load_master("master_kategori").empty else {}
    
    df = df.copy()
    df["nama_sekolah"] = df["kode_sekolah"].map(m_sekolah).fillna("(?)")
    df["nama_bayar"] = df["kode_bayar"].map(m_bayar).fillna("(?)")
    df["kategori"] = df["prefix_va"].map(m_kat).fillna("(?)")
    df["bulan_nama"] = df["bulan_tp"].apply(nama_bulan_tp)
    return df

def format_rp(val):
    if pd.isna(val) or val == "": return val
    if isinstance(val, (int, float)): return f"Rp\u00A0{val:,.0f}".replace(",", ".")
    return val

def apply_filters(df: pd.DataFrame, key_prefix: str) -> pd.DataFrame:
    if df.empty: return df
    st.markdown("#### 🔎 Filter Laporan")
    c1, c2, c3 = st.columns(3)
    tp_opts = sorted(df["tahun_bayar"].dropna().unique())
    f_tp = c1.multiselect("TP (Tahun Bayar)", tp_opts, default=tp_opts, key=f"{key_prefix}_tp")
    comp_opts = sorted(df["company_code"].dropna().unique())
    f_comp = c2.multiselect("Company Code", comp_opts, default=comp_opts, key=f"{key_prefix}_comp")
    kat_opts = sorted(df["kategori"].dropna().unique())
    f_kat = c3.multiselect("Kategori", kat_opts, default=kat_opts, key=f"{key_prefix}_kat")
    c4, c5 = st.columns(2)
    sek_opts = sorted(df["nama_sekolah"].dropna().unique())
    f_sek = c4.multiselect("Sekolah", sek_opts, default=sek_opts, key=f"{key_prefix}_sek")
    bayar_opts = sorted(df["nama_bayar"].dropna().unique())
    f_bayar = c5.multiselect("Jenis Bayar", bayar_opts, default=bayar_opts, key=f"{key_prefix}_bayar")
    return df[
        df["tahun_bayar"].isin(f_tp) & df["company_code"].isin(f_comp) & 
        df["kategori"].isin(f_kat) & df["nama_sekolah"].isin(f_sek) & df["nama_bayar"].isin(f_bayar)
    ]

def apply_filters_edit(df: pd.DataFrame, key_prefix: str) -> pd.DataFrame:
    if df.empty: return df
    st.markdown("##### 🔎 Filter Data")
    c1, c2, c3 = st.columns(3)
    f_tp = c1.multiselect("TP (Tahun Bayar)", sorted(df["tahun_bayar"].dropna().unique()), key=f"{key_prefix}_tp")
    f_bulan = c2.multiselect("Bulan Transaksi", sorted(df["bulan"].dropna().unique()), key=f"{key_prefix}_bulan")
    f_file = c3.multiselect("Asal File", sorted(df["asal_file"].dropna().unique()), key=f"{key_prefix}_file")
    c4, c5, c6 = st.columns(3)
    f_kat = c4.multiselect("Kategori", sorted(df["prefix_va"].dropna().unique()), key=f"{key_prefix}_kat")
    f_sek = c5.multiselect("Kode Sekolah", sorted(df["kode_sekolah"].dropna().unique()), key=f"{key_prefix}_sek")
    
    bayar_col = "nama_bayar" if "nama_bayar" in df.columns else "kode_bayar"
    bayar_opts = sorted(df[bayar_col].dropna().unique())
    f_bayar = c6.multiselect("Jenis Bayar", bayar_opts, key=f"{key_prefix}_bayar")
    
    res = df.copy()
    if f_tp: res = res[res["tahun_bayar"].isin(f_tp)]
    if f_bulan: res = res[res["bulan"].isin(f_bulan)]
    if f_file: res = res[res["asal_file"].isin(f_file)]
    if f_kat: res = res[res["prefix_va"].isin(f_kat)]
    if f_sek: res = res[res["kode_sekolah"].isin(f_sek)]
    if f_bayar: res = res[res[bayar_col].isin(f_bayar)]
    return res

# ============================================================
# FUNGSI RENDER TIAP TAB
# ============================================================

@st.fragment
def render_upload():
    if "upload_success" not in st.session_state:
        st.session_state.upload_success = None
    if "upload_error" not in st.session_state:
        st.session_state.upload_error = None
    st.subheader("📤 Upload File TXT")
    
    if st.session_state.upload_success:
        s = st.session_state.upload_success
        st.success(f"✅ Selesai! {s['saved']} file baru, {s['replaced']} diganti. {s['total_rows']} baris tersimpan.")
        if st.button("🗑️ Bersihkan Tampilan"): 
            st.session_state.upload_success = None
            st.rerun()

    if st.session_state.get("upload_error"):
        st.error(st.session_state.upload_error)

    uploaded_files = st.file_uploader("Pilih file TXT", type="txt", accept_multiple_files=True, key=f"uploader_{st.session_state.uploader_key}")
    
    if uploaded_files:
        existing = db.get_existing_files()
        dup_files = [f for f in uploaded_files if f.name in existing]
        
        mode_duplikat = "skip"
        if dup_files:
            st.warning(f"⚠️ {len(dup_files)} file duplikat.")
            mode_duplikat = st.radio("Aksi duplikat?", ["skip", "replace", "tolak"], format_func=lambda x: {"skip": "⏭️ Skip", "replace": "🔄 Replace", "tolak": "❌ Tolak"}[x], horizontal=True, key="mode_dup")
            
        if st.button("💾 Simpan ke Database", type="primary"):
            if mode_duplikat == "tolak" and dup_files:
                st.error("❌ Upload dibatalkan karena ada file duplikat.")
            else:
                saved = replaced = total_rows = 0
                df_list = []
                file_info_list = []
                
                for f in uploaded_files:
                    if f.name in existing and mode_duplikat == "skip": continue
                    df, _, _ = parse_txt_content(f.getvalue(), f.name)
                    if df.empty: continue
                    
                    df_list.append(df)
                    file_info_list.append((f.name, f.getvalue()))
                    total_rows += len(df)
                    if f.name in existing: replaced += 1
                    else: saved += 1
                    
                if df_list:
                    with st.spinner("Menyimpan ke Cloud Supabase..."):
                        db.insert_transaksi_bulk(df_list, file_info_list)
                # --- TAMBAHAN UNTUK DEBUG ---
                st.warning(f"DEBUG: Mencoba menyimpan {total_rows} baris data ke Supabase...")
                # ----------------------------
                st.session_state.upload_success = {"saved": saved, "replaced": replaced, "total_rows": total_rows}
                st.session_state.upload_error = None
                st.session_state.uploader_key += 1
                st.cache_data.clear()
                st.rerun()

    st.divider()
    
    # --- FITUR HAPUS FILE (MULTI-SELECT) ---
    st.subheader("🗑️ Hapus Data File")
    df_log = db.get_all_log_files()
    
    if not df_log.empty:
        st.markdown("Pilih file yang ingin dihapus (bisa lebih dari satu).")
        
        # Tampilkan multiselect (bisa centang banyak)
        file_to_delete = st.multiselect(
            "Pilih File yang Akan Dihapus:",
            options=df_log["file_name"].tolist(),
            key="file_hapus_multi"
        )
        
        if st.button("❌ Hapus File Terpilih", type="primary"):
            if not file_to_delete:
                st.warning("Pilih minimal satu file terlebih dahulu.")
            else:
                with st.spinner(f"Menghapus {len(file_to_delete)} file dari Cloud..."):
                    for fname in file_to_delete:
                        db.delete_file(fname)
                st.success(f"✅ Berhasil menghapus {len(file_to_delete)} file!")
                st.rerun()
    else:
        st.info("Belum ada file yang tersimpan di database.")
        

@st.fragment
def render_dashboard():
    st.subheader("📊 Dashboard Ringkasan")
    df = db.load_all_transaksi()
    if not df.empty:
        df = enrich_df(df)
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("💰 Total Nominal", format_rp(df['credit'].sum()))
        k2.metric("🧾 Total Transaksi", f"{len(df):,}")
        k3.metric("🆔 VA Unik", f"{df['no_va'].nunique():,}")
        k4.metric("📅 Jumlah TP", df["tahun_bayar"].nunique())
        
        st.divider()
        st.markdown("### 📈 Tren Nominal per Bulan Transaksi")
        tren = df.groupby("bulan").agg(Nominal=("credit", "sum"), Jumlah=("no_va", "count")).reset_index().sort_values("bulan")
        fig = px.bar(tren, x="bulan", y="Nominal", text="Jumlah")
        st.plotly_chart(fig, use_container_width=True)
        
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("### 🏫 Top 10 Sekolah")
            top_sek = df.groupby("nama_sekolah")["credit"].sum().sort_values(ascending=False).head(10).reset_index()
            if not top_sek.empty: st.plotly_chart(px.bar(top_sek, x="credit", y="nama_sekolah", orientation="h"), use_container_width=True)
        with c2:
            st.markdown("### 🥧 Distribusi Kategori")
            dist = df.groupby("kategori")["credit"].sum().reset_index()
            if not dist.empty: st.plotly_chart(px.pie(dist, names="kategori", values="credit", hole=0.5), use_container_width=True)


@st.fragment
def render_laporan():
    st.subheader("📈 Laporan")
    df = db.load_all_transaksi()
    if not df.empty:
        df = enrich_df(df)
        
        with st.expander("🔎 Filter Global Laporan", expanded=True):
            col1, col2 = st.columns(2)
            pilih_tp = col1.multiselect("Filter TP (Global)", sorted(df["tahun_bayar"].dropna().unique()))
            pilih_file = col2.multiselect("Filter Asal File", sorted(df["asal_file"].dropna().unique()))
            if pilih_tp: df = df[df["tahun_bayar"].isin(pilih_tp)]
            if pilih_file: df = df[df["asal_file"].isin(pilih_file)]
            
        sub_bank, sub_tp, sub_sek_bayar, sub_sek_tp, sub_siswa, sub_detail = st.tabs([
            "📥 Bank", "📤 Per TP", "🏫 Sekolah × Bayar", "🏫 Sekolah × TP", "🏆 Top Siswa", "📋 Detail"
        ])

        with sub_bank:
            df_bank = apply_filters(df, key_prefix="bank")
            if not df_bank.empty:
                tbl_bulan = df_bank.groupby("bulan").agg(Nominal=("credit", "sum"), Transaksi=("no_va", "count"), VA_Unik=("no_va", "nunique")).reset_index().sort_values("bulan")
                tbl_bulan_tampil = tbl_bulan.copy(); tbl_bulan_tampil["Nominal"] = tbl_bulan_tampil["Nominal"].apply(lambda x: format_rp(x))
                st.dataframe(tbl_bulan_tampil, use_container_width=False, hide_index=True)
                
                pivot_bank = df_bank.pivot_table(index="bulan", columns="tahun_bayar", values="credit", aggfunc="sum", fill_value=0).sort_index()
                pivot_bank["TOTAL"] = pivot_bank.sum(axis=1); pivot_bank.loc["TOTAL"] = pivot_bank.sum()
                st.dataframe(pivot_bank.style.format(lambda x: f"Rp {x:,.0f}".replace(",", ".")), use_container_width=False)

        with sub_tp:
            df_tp = apply_filters(df, key_prefix="tp")
            if not df_tp.empty:
                tbl_tp = df_tp.groupby("tahun_bayar").agg(Nominal=("credit", "sum"), Transaksi=("no_va", "count"), VA_Unik=("no_va", "nunique")).reset_index().sort_values("tahun_bayar")
                tbl_tp_tampil = tbl_tp.copy(); tbl_tp_tampil["Nominal"] = tbl_tp_tampil["Nominal"].apply(lambda x: format_rp(x))
                st.dataframe(tbl_tp_tampil, use_container_width=False, hide_index=True)
                
                pivot_tp = df_tp.pivot_table(index="tahun_bayar", columns="bulan_tp", values="credit", aggfunc="sum", fill_value=0).sort_index()
                pivot_tp.columns = [f"B{int(c)}" for c in pivot_tp.columns]
                for i in range(1, 13):
                    if f"B{i}" not in pivot_tp.columns: pivot_tp[f"B{i}"] = 0
                pivot_tp = pivot_tp[[f"B{i}" for i in range(1, 13)]]; pivot_tp["TOTAL"] = pivot_tp.sum(axis=1)
                st.dataframe(pivot_tp.style.format(lambda x: f"Rp {x:,.0f}".replace(",", ".")), use_container_width=False)

        with sub_sek_bayar:
            df_sb = apply_filters(df, key_prefix="sekbayar")
            if not df_sb.empty:
                tp_pilih = st.selectbox("Pilih TP", options=["(Semua)"] + sorted(df_sb["tahun_bayar"].unique()))
                df_pivot = df_sb if tp_pilih == "(Semua)" else df_sb[df_sb["tahun_bayar"] == tp_pilih]
                pivot_sb = df_pivot.pivot_table(index="nama_sekolah", columns="nama_bayar", values="credit", aggfunc="sum", fill_value=0)
                pivot_sb["TOTAL"] = pivot_sb.sum(axis=1); pivot_sb = pivot_sb.sort_values("TOTAL", ascending=False); pivot_sb.loc["TOTAL"] = pivot_sb.sum()
                st.dataframe(pivot_sb.style.format(lambda x: f"Rp {x:,.0f}".replace(",", ".")), use_container_width=False)

        with sub_sek_tp:
            df_st = apply_filters(df, key_prefix="sektp")
            if not df_st.empty:
                pivot_st = df_st.pivot_table(index="nama_sekolah", columns="tahun_bayar", values="credit", aggfunc="sum", fill_value=0)
                pivot_st["TOTAL"] = pivot_st.sum(axis=1); pivot_st = pivot_st.sort_values("TOTAL", ascending=False); pivot_st.loc["TOTAL"] = pivot_st.sum()
                st.dataframe(pivot_st.style.format(lambda x: f"Rp {x:,.0f}".replace(",", ".")), use_container_width=False)

        with sub_siswa:
            df_sw = apply_filters(df, key_prefix="siswa")
            if not df_sw.empty:
                tbl_siswa = df_sw.groupby(["nama_sekolah", "remark"]).agg(Nominal=("credit", "sum"), Transaksi=("no_va", "count")).reset_index().sort_values("Nominal", ascending=False).head(50)
                tbl_siswa.columns = ["Sekolah", "Siswa", "Nominal", "Transaksi"]
                tbl_siswa_tampil = tbl_siswa.copy(); tbl_siswa_tampil["Nominal"] = tbl_siswa_tampil["Nominal"].apply(lambda x: format_rp(x))
                st.dataframe(tbl_siswa_tampil, use_container_width=False, hide_index=True)

        with sub_detail:
            df_dt = apply_filters(df, key_prefix="detail")
            if not df_dt.empty:
                df_show_tampil = df_dt[["date", "no_va", "remark", "tahun_bayar", "kategori", "credit"]].sort_values("date", ascending=False).copy()
                df_show_tampil["credit"] = df_show_tampil["credit"].apply(lambda x: format_rp(x))
                st.dataframe(df_show_tampil, use_container_width=False, hide_index=True)


@st.fragment
def render_rekon():
    st.subheader("⚖️ Rekonsiliasi (Bank vs Data PIC)")
    
    list_bulan = db.get_list_bulan()
    if not list_bulan:
        st.warning("Belum ada data transaksi di database.")
    else:
        periode_pilih = st.selectbox("1️⃣ Pilih Periode Bulan (Bank & PIC)", options=list_bulan)
        
        up_pic = st.file_uploader("2️⃣ Upload File Rekap PIC (Excel/CSV)", type=["csv", "xlsx"], key="rekon_pic")
        
        if up_pic:
            try:
                df_pic_asli = pd.read_csv(up_pic) if up_pic.name.endswith(".csv") else pd.read_excel(up_pic)
                df_pic_asli.columns = [str(c).lower().strip() for c in df_pic_asli.columns]
                
                col_sek = next((c for c in df_pic_asli.columns if "sekolah" in c or "kode sek" in c), None)
                col_bayar = next((c for c in df_pic_asli.columns if "bayar" in c or "jenis" in c), None)
                col_nom = next((c for c in df_pic_asli.columns if "nominal" in c or "credit" in c or "jumlah" in c), None)
                
                if not col_sek or not col_bayar or not col_nom:
                    st.error("❌ Format file salah. Pastikan ada kolom Sekolah, Jenis Bayar, dan Nominal.")
                else:
                    df_pic = df_pic_asli[[col_sek, col_bayar, col_nom]].copy()
                    df_pic.columns = ["kode_sekolah", "kode_bayar", "nominal_pic"]
                    df_pic["kode_sekolah"] = df_pic["kode_sekolah"].astype(str).str.strip().str.zfill(2)
                    df_pic["kode_bayar"] = df_pic["kode_bayar"].astype(str).str.strip().str.zfill(2)
                    df_pic["nominal_pic"] = pd.to_numeric(df_pic["nominal_pic"], errors="coerce").fillna(0)
                    
                    df_pic_group = df_pic.groupby(["kode_sekolah", "kode_bayar"])["nominal_pic"].sum().reset_index()
                    st.success(f"✅ File PIC terbaca. Siap dicocokkan dengan data Bank periode **{periode_pilih}**.")
                    
                    if st.button("🔍 Mulai Pencocokkan", type="primary"):
                        with st.spinner("Mencocokkan data..."):
                            df_bank = db.get_rekap_bank(periode_pilih)
                            
                            df_alias_sek = db.load_alias_sekolah()
                            if not df_alias_sek.empty:
                                map_sek = dict(zip(df_alias_sek["kode_bank"], df_alias_sek["kode_pic"]))
                                df_bank["kode_sekolah"] = df_bank["kode_sekolah"].replace(map_sek)
                                
                            df_alias_bay = db.load_alias_bayar()
                            if not df_alias_bay.empty:
                                map_bay = dict(zip(df_alias_bay["kode_bank"], df_alias_bay["kode_pic"]))
                                df_bank["kode_bayar"] = df_bank["kode_bayar"].replace(map_bay)
                                
                            df_bank = df_bank.groupby(["kode_sekolah", "kode_bayar"])["total_bank"].sum().reset_index()
                            
                            df_compare = pd.merge(df_pic_group, df_bank, on=["kode_sekolah", "kode_bayar"], how="outer").fillna(0)
                            df_compare["Selisih"] = df_compare["total_bank"] - df_compare["nominal_pic"]
                            
                            m_sek = db.load_master("master_sekolah").set_index("kode")["nama"].to_dict()
                            m_bay = db.load_master("master_bayar").set_index("kode")["nama"].to_dict()
                            df_compare["Nama Sekolah"] = df_compare["kode_sekolah"].map(m_sek).fillna(df_compare["kode_sekolah"])
                            df_compare["Nama Bayar"] = df_compare["kode_bayar"].map(m_bay).fillna(df_compare["kode_bayar"])
                            
                            st.session_state["rekon_beda"] = df_compare[(df_compare["total_bank"] > 0) & (df_compare["nominal_pic"] > 0) & (df_compare["Selisih"] != 0)]
                            st.session_state["rekon_hanya_bank"] = df_compare[(df_compare["total_bank"] > 0) & (df_compare["nominal_pic"] == 0)]
                            st.session_state["rekon_hanya_pic"] = df_compare[(df_compare["total_bank"] == 0) & (df_compare["nominal_pic"] > 0)]
                            st.session_state["rekon_cocok"] = df_compare[(df_compare["total_bank"] > 0) & (df_compare["nominal_pic"] > 0) & (df_compare["Selisih"] == 0)]
                            st.session_state["rekon_pic_asli"] = df_pic
                            st.session_state["rekon_bulan"] = periode_pilih

            except Exception as e:
                st.error(f"Terjadi kesalahan: {e}")

        if "rekon_beda" in st.session_state:
            beda = st.session_state["rekon_beda"]
            hanya_bank = st.session_state["rekon_hanya_bank"]
            hanya_pic = st.session_state["rekon_hanya_pic"]
            cocok = st.session_state["rekon_cocok"]
            df_pic_asli = st.session_state["rekon_pic_asli"]
            bulan_aktif = st.session_state["rekon_bulan"]
            
            df_alias_sek = db.load_alias_sekolah()
            df_alias_bay = db.load_alias_bayar()

            st.divider()
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("✅ Cocok", len(cocok))
            c2.metric("⚠️ Beda Nominal", len(beda))
            c3.metric("🔴 Hanya di Bank", len(hanya_bank))
            c4.metric("🟡 Hanya di PIC", len(hanya_pic))
            
            r1, r2, r3, r4 = st.tabs(["⚠️ Beda Nominal", "🔴 Hanya di Bank", "🟡 Hanya di PIC", "✅ Cocok"])
            kolom_tampil = ["kode_sekolah", "kode_bayar", "Nama Sekolah", "Nama Bayar", "total_bank", "nominal_pic", "Selisih"]
            
            def tampilkan_tabel_rekon(df_target, key_prefix):
                if df_target.empty:
                    st.info("Tidak ada data.")
                    return None, None
                
                df_tampil = df_target[kolom_tampil].copy()
                total_row = {
                    "kode_sekolah": "", "kode_bayar": "", "Nama Sekolah": "TOTAL", "Nama Bayar": "",
                    "total_bank": df_tampil["total_bank"].sum(),
                    "nominal_pic": df_tampil["nominal_pic"].sum(),
                    "Selisih": df_tampil["Selisih"].sum()
                }
                df_tampil = pd.concat([df_tampil, pd.DataFrame([total_row])], ignore_index=True)
                
                format_dict = {"total_bank": "Rp {:,.0f}", "nominal_pic": "Rp {:,.0f}", "Selisih": "Rp {:,.0f}"}
                st.dataframe(df_tampil.style.format(format_dict, na_rep=""), use_container_width=False, hide_index=True)
                
                df_pilihan = df_target.copy()
                opsi = df_pilihan.apply(lambda x: f"{x['kode_sekolah']} - {x['kode_bayar']}", axis=1).tolist()
                if opsi:
                    pilih_opsi = st.selectbox("Pilih baris untuk lihat detail:", opsi, key=f"sel_{key_prefix}")
                    if pilih_opsi:
                        sek, bay = pilih_opsi.split(" - ")
                        return sek, bay
                return None, None

            def tampilkan_detail(sekolah, bayar, jenis):
                if not sekolah: return
                st.markdown("---")
                st.markdown(f"#### 📋 Detail Transaksi: {sekolah} - {bayar} (Sumber: {jenis})")
                
                if jenis == "Bank":
                    kode_sek_asli = df_alias_sek[df_alias_sek["kode_pic"] == sekolah]["kode_bank"].tolist() if not df_alias_sek.empty else []
                    kode_bay_asli = df_alias_bay[df_alias_bay["kode_pic"] == bayar]["kode_bank"].tolist() if not df_alias_bay.empty else []
                    kode_sek_asli.append(sekolah)
                    kode_bay_asli.append(bayar)
                    
                    list_detail = []
                    for sk in kode_sek_asli:
                        for by in kode_bay_asli:
                            det = db.get_detail_bank(bulan_aktif, sk, by)
                            if not det.empty:
                                list_detail.append(det)
                                
                    if not list_detail:
                        st.info("Data tidak ditemukan di database.")
                    else:
                        det_final = pd.concat(list_detail, ignore_index=True)
                        det_final["credit"] = det_final["credit"].apply(lambda x: format_rp(x))
                        st.dataframe(det_final, use_container_width=False, hide_index=True)
                else:
                    det = db.get_detail_pic(df_pic_asli, sekolah, bayar)
                    if det.empty: st.info("Data tidak ditemukan.")
                    else:
                        det_format = det.copy()
                        det_format["nominal_pic"] = det_format["nominal_pic"].apply(lambda x: format_rp(x))
                        st.dataframe(det_format, use_container_width=False, hide_index=True)

            with r1:
                sek, bay = tampilkan_tabel_rekon(beda, "beda")
                if sek: tampilkan_detail(sek, bay, "Bank"); tampilkan_detail(sek, bay, "PIC")

            with r2:
                sek, bay = tampilkan_tabel_rekon(hanya_bank, "bank")
                if sek: tampilkan_detail(sek, bay, "Bank")
                        
            with r3:
                sek, bay = tampilkan_tabel_rekon(hanya_pic, "pic")
                if sek: tampilkan_detail(sek, bay, "PIC")

            with r4:
                tampilkan_tabel_rekon(cocok, "cocok")


@st.fragment
def render_edit():
    st.subheader("✏️ Edit Data (Koreksi NO.VA)")
    df_edit = enrich_df(db.load_all_transaksi())
    
    if not df_edit.empty:
        df_filtered = apply_filters_edit(df_edit, key_prefix="edit")
        
        with st.expander("🛠️ Ganti Karakter Massal"):
            c1, c2, c3 = st.columns(3)
            posisi = c1.number_input("Karakter ke-", min_value=1, value=3)
            jml_karakter = c2.number_input("Jumlah diganti", min_value=1, value=2)
            pengganti = c3.text_input("Diganti jadi", value="00")
            
            def replace_massal(no_va):
                no_va = str(no_va); start_idx = int(posisi) - 1; end_idx = start_idx + int(jml_karakter)
                return no_va[:start_idx] + pengganti + no_va[end_idx:]
                
            if st.button("👀 Preview", key="prev_massal"):
                df_prev = df_filtered.head(10).copy(); df_prev["Lama"] = df_prev["no_va"]; df_prev["Baru"] = df_prev["no_va"].apply(replace_massal)
                st.dataframe(df_prev[["remark", "Lama", "Baru"]], use_container_width=False, hide_index=True)

            if st.button("💾 Terapkan Massal", type="primary"):
                df_updates = df_filtered.copy()
                df_updates["no_va_baru"] = df_updates["no_va"].astype(str).apply(replace_massal)
                df_updates = df_updates[df_updates["no_va"] != df_updates["no_va_baru"]].copy()
                
                if not df_updates.empty:
                    df_updates["prefix_va"] = df_updates["no_va_baru"].str[:2]
                    df_updates["kode_sekolah"] = df_updates["no_va_baru"].str[-4:-2]
                    df_updates["kode_bayar"] = df_updates["no_va_baru"].str[-2:]
                    
                    date_dt = pd.to_datetime(df_updates["date"], format="%d/%m/%Y", errors="coerce")
                    tahun_awal = date_dt.dt.year.where(date_dt.dt.month >= 7, date_dt.dt.year - 1)
                    tp_dari_tanggal = tahun_awal.astype(str) + "-" + (tahun_awal + 1).astype(str)
                    
                    prefix_digit = df_updates["prefix_va"].str.isdigit() & (df_updates["prefix_va"] != "00") & (df_updates["prefix_va"] != "")
                    th_prefix = pd.to_numeric("20" + df_updates["prefix_va"], errors="coerce")
                    
                    df_updates["tahun_bayar"] = tp_dari_tanggal
                    df_updates.loc[prefix_digit, "tahun_bayar"] = (
                        th_prefix[prefix_digit].astype('Int64').astype(str) + "-" + 
                        (th_prefix[prefix_digit] + 1).astype('Int64').astype(str)
                    )
                    
                    bulan_dari_tanggal = date_dt.dt.month.apply(lambda m: m - 6 if m >= 7 else m + 6)
                    df_updates["bulan_tp"] = bulan_dari_tanggal
                    df_updates.loc[prefix_digit, "bulan_tp"] = 1
                    
                    with st.spinner("Menyimpan perubahan massal ke Cloud..."):
                        db.update_no_va_bulk_vector(df_filtered, df_updates)
                    st.success(f"✅ {len(df_updates)} data diubah secara instan!")
                    st.rerun()

        st.divider()
        edited_df = st.data_editor(
            df_filtered[["id", "date", "no_va", "remark", "credit", "tahun_bayar"]],
            disabled=["id", "date", "remark", "credit", "tahun_bayar"], key="editor_no_va", use_container_width=False, hide_index=True
        )
        
        if st.button("💾 Simpan Perubahan Satuan", type="primary"):
            df_merged = pd.merge(df_filtered[["id", "no_va"]], edited_df[["id", "no_va"]], on="id", suffixes=("_asli", "_baru"))
            df_changed = df_merged[df_merged["no_va_asli"] != df_merged["no_va_baru"]].copy()
            
            if not df_changed.empty:
                df_changed = df_changed.merge(df_filtered[["id", "date"]], on="id", how="left")
                df_updates = df_changed.rename(columns={"no_va_baru": "no_va"})
                
                df_updates["prefix_va"] = df_updates["no_va"].astype(str).str[:2]
                df_updates["kode_sekolah"] = df_updates["no_va"].astype(str).str[-4:-2]
                df_updates["kode_bayar"] = df_updates["no_va"].astype(str).str[-2:]
                
                date_dt = pd.to_datetime(df_updates["date"], format="%d/%m/%Y", errors="coerce")
                tahun_awal = date_dt.dt.year.where(date_dt.dt.month >= 7, date_dt.dt.year - 1)
                tp_dari_tanggal = tahun_awal.astype(str) + "-" + (tahun_awal + 1).astype(str)
                
                prefix_digit = df_updates["prefix_va"].str.isdigit() & (df_updates["prefix_va"] != "00") & (df_updates["prefix_va"] != "")
                th_prefix = pd.to_numeric("20" + df_updates["prefix_va"], errors="coerce")
                
                df_updates["tahun_bayar"] = tp_dari_tanggal
                df_updates.loc[prefix_digit, "tahun_bayar"] = (
                    th_prefix[prefix_digit].astype('Int64').astype(str) + "-" + 
                    (th_prefix[prefix_digit] + 1).astype('Int64').astype(str)
                )
                
                bulan_dari_tanggal = date_dt.dt.month.apply(lambda m: m - 6 if m >= 7 else m + 6)
                df_updates["bulan_tp"] = bulan_dari_tanggal
                df_updates.loc[prefix_digit, "bulan_tp"] = 1
                
                with st.spinner("Menyimpan ke Cloud..."):
                    db.update_no_va_bulk_vector(df_filtered, df_updates)
                st.success(f"✅ {len(df_updates)} perubahan disimpan secara instan!")
                st.rerun()
            else:
                st.info("Tidak ada perubahan yang perlu disimpan.")


@st.fragment
def render_master():
    st.subheader("⚙️ Master Data")
    
    # --- 1. MASTER SEKOLAH ---
    st.markdown("#### 🏫 Master Sekolah")
    df_sekolah = db.load_master("master_sekolah")
    up_sek = st.file_uploader("Upload CSV/Excel Sekolah (kolom: kode, nama)", type=["csv", "xlsx"], key="up_sek_v3")
    if up_sek:
        if st.session_state.get("done_up_sek") != up_sek.name:
            df_up = pd.read_csv(up_sek) if up_sek.name.endswith(".csv") else pd.read_excel(up_sek)
            if {"kode", "nama"}.issubset(df_up.columns):
                db.upsert_master("master_sekolah", df_up[["kode", "nama"]].dropna())
                st.session_state["done_up_sek"] = up_sek.name
                st.success(f"✅ File {up_sek.name} berhasil diupload!")
                st.rerun()
            else:
                st.error("❌ Format salah. Harus ada kolom 'kode' dan 'nama'.")
    edited_sek = st.data_editor(df_sekolah, num_rows="dynamic", key="edit_sek_v3", use_container_width=False)
    if st.button("💾 Simpan Master Sekolah"):
        db.upsert_master("master_sekolah", edited_sek.dropna()); st.success("✅ Tersimpan."); st.rerun()

    st.divider()

    # --- 2. MASTER JENIS BAYAR ---
    st.markdown("#### 💳 Master Jenis Bayar")
    df_bayar = db.load_master("master_bayar")
    up_bayar = st.file_uploader("Upload CSV/Excel Jenis Bayar (kolom: kode, nama)", type=["csv", "xlsx"], key="up_bayar_v3")
    if up_bayar:
        if st.session_state.get("done_up_bayar") != up_bayar.name:
            df_up = pd.read_csv(up_bayar) if up_bayar.name.endswith(".csv") else pd.read_excel(up_bayar)
            if {"kode", "nama"}.issubset(df_up.columns):
                db.upsert_master("master_bayar", df_up[["kode", "nama"]].dropna())
                st.session_state["done_up_bayar"] = up_bayar.name
                st.success(f"✅ File {up_bayar.name} berhasil diupload!")
                st.rerun()
            else:
                st.error("❌ Format salah. Harus ada kolom 'kode' dan 'nama'.")
    edited_bayar = st.data_editor(df_bayar, num_rows="dynamic", key="edit_bayar_v3", use_container_width=False)
    if st.button("💾 Simpan Master Jenis Bayar"):
        db.upsert_master("master_bayar", edited_bayar.dropna()); st.success("✅ Tersimpan."); st.rerun()

    st.divider()

    # --- 3. MASTER KATEGORI ---
    st.markdown("#### 🗂️ Master Kategori TP (KODE TP--2 digit pertama VA)")
    df_kat = db.load_master("master_kategori")
    
    # Fitur Upload Kategori
    up_kat = st.file_uploader("Upload CSV/Excel Kategori (kolom: Kode TP, Kategori)", type=["csv", "xlsx"], key="up_kat_v3")
    if up_kat:
        if st.session_state.get("done_up_kat") != up_kat.name:
            df_up = pd.read_csv(up_kat) if up_kat.name.endswith(".csv") else pd.read_excel(up_kat)
            if {"prefix_va", "kategori"}.issubset(df_up.columns):
                db.upsert_master("master_kategori", df_up[["prefix_va", "kategori"]].dropna())
                st.session_state["done_up_kat"] = up_kat.name
                st.success(f"✅ File {up_kat.name} berhasil diupload!")
                st.rerun()
            else:
                st.error("❌ Format salah. Harus ada kolom 'kode TP' dan 'kategori'.")
                
    # Trik agar tabel bisa diedit manual jika kosong
    if df_kat.empty:
        df_kat = pd.DataFrame(columns=["prefix_va", "kategori"])
        
    edited_kat = st.data_editor(
        df_kat, num_rows="dynamic", use_container_width=False, key="edit_kat_v3",
        column_config={
            "prefix_va": st.column_config.TextColumn("Kode TP", width="large"),
            "kategori": st.column_config.TextColumn("Kategori", width="large")
        }
    )
    if st.button("💾 Simpan Master Kategori"):
        db.upsert_master("master_kategori", edited_kat.dropna())
        st.success("✅ Tersimpan.")
        st.rerun()

    st.divider()

    # --- 4. MASTER ALIAS SEKOLAH ---
    st.markdown("#### 🔄 Master Alias (Penggabungan Kode Sekolah)")
    df_alias_sek = db.load_alias_sekolah()
    up_alias_sek = st.file_uploader("Upload CSV/Excel Alias Sekolah (kolom: kode_bank, kode_pic)", type=["csv", "xlsx"], key="up_alias_sek_v1")
    if up_alias_sek:
        if st.session_state.get("done_up_alias_sek") != up_alias_sek.name:
            df_up = pd.read_csv(up_alias_sek) if up_alias_sek.name.endswith(".csv") else pd.read_excel(up_alias_sek)
            if {"kode_bank", "kode_pic"}.issubset(df_up.columns):
                db.save_alias_sekolah(df_up[["kode_bank", "kode_pic"]].dropna())
                st.session_state["done_up_alias_sek"] = up_alias_sek.name
                st.success(f"✅ File {up_alias_sek.name} berhasil diupload!")
                st.rerun()
            else:
                st.error("❌ Format salah. Harus ada kolom 'kode_bank' dan 'kode_pic'.")

    if df_alias_sek.empty:
        df_alias_sek = pd.DataFrame(columns=["kode_bank", "kode_pic"])
        
    edited_alias_sek = st.data_editor(
        df_alias_sek, num_rows="dynamic", use_container_width=False, key="edit_alias_sek_v1",
        column_config={
            "kode_bank": st.column_config.TextColumn("Kode Bank", width="large"),
            "kode_pic": st.column_config.TextColumn("Kode PIC", width="large")
        }
    )
    if st.button("💾 Simpan Master Alias Sekolah"):
        db.save_alias_sekolah(edited_alias_sek.dropna())
        st.success("✅ Tersimpan.")
        st.rerun()

    st.divider()

    # --- 5. MASTER ALIAS BAYAR ---
    st.markdown("#### 🔄 Master Alias (Penggabungan Kode Bayar)")
    df_alias_bay = db.load_alias_bayar()
    up_alias_bay = st.file_uploader("Upload CSV/Excel Alias Bayar (kolom: kode_bank, kode_pic)", type=["csv", "xlsx"], key="up_alias_bay_v1")
    if up_alias_bay:
        if st.session_state.get("done_up_alias_bay") != up_alias_bay.name:
            df_up = pd.read_csv(up_alias_bay) if up_alias_bay.name.endswith(".csv") else pd.read_excel(up_alias_bay)
            if {"kode_bank", "kode_pic"}.issubset(df_up.columns):
                db.save_alias_bayar(df_up[["kode_bank", "kode_pic"]].dropna())
                st.session_state["done_up_alias_bay"] = up_alias_bay.name
                st.success(f"✅ File {up_alias_bay.name} berhasil diupload!")
                st.rerun()
            else:
                st.error("❌ Format salah. Harus ada kolom 'kode_bank' dan 'kode_pic'.")

    if df_alias_bay.empty:
        df_alias_bay = pd.DataFrame(columns=["kode_bank", "kode_pic"])

    edited_alias_bay = st.data_editor(
        df_alias_bay, num_rows="dynamic", use_container_width=False, key="edit_alias_bay_v1",
        column_config={
            "kode_bank": st.column_config.TextColumn("Kode Bank", width="large"),
            "kode_pic": st.column_config.TextColumn("Kode PIC", width="large")
        }
    )
    if st.button("💾 Simpan Master Alias Bayar"):
        db.save_alias_bayar(edited_alias_bay.dropna())
        st.success("✅ Tersimpan.")
        st.rerun()

# ============================================================
# EKSEKUSI TAB
# ============================================================
tab_upload, tab_dashboard, tab_laporan, tab_rekon, tab_edit, tab_master = st.tabs(
    ["📤 Upload", "📊 Dashboard", "📈 Laporan", "⚖️ Rekon", "✏️ Edit", "⚙️ Master"]
)

with tab_upload:
    render_upload()

with tab_dashboard:
    render_dashboard()

with tab_laporan:
    render_laporan()

with tab_rekon:
    render_rekon()

with tab_edit:
    render_edit()

with tab_master:
    render_master()
