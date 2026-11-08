import hashlib
from datetime import datetime
import pandas as pd
import streamlit as st
from supabase import create_client, Client

# ==========================================
# KONFIGURASI SUPABASE
# ==========================================
# Saat online di Streamlit Cloud, ambil dari secrets
SUPABASE_URL = st.secrets["supabase"]["url"]
SUPABASE_KEY = st.secrets["supabase"]["key"]

@st.cache_resource
def get_supabase() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_KEY)

def get_conn():
    """Fungsi dummy agar tidak error saat dipanggil kode lama."""
    return get_supabase()

def init_db():
    """Tabel sudah dibuat lewat SQL Editor, jadi fungsi ini kosong."""
    pass

# ==========================================
# FUNGSI BACA DATA
# ==========================================
#@st.cache_data(ttl=60)
def load_all_transaksi() -> pd.DataFrame:
    supabase = get_supabase()
    # Ambil semua data (limit 100.000 baris untuk keamanan memori)
    response = supabase.table("transaksi").select("*").limit(100000).execute()
    return pd.DataFrame(response.data)

@st.cache_data(ttl=60)
def get_list_bulan() -> list:
    supabase = get_supabase()
    response = supabase.table("transaksi").select("bulan").execute()
    df = pd.DataFrame(response.data)
    if df.empty: return []
    return sorted(df["bulan"].dropna().unique().tolist(), reverse=True)

@st.cache_data(ttl=60)
def get_existing_files() -> set[str]:
    supabase = get_supabase()
    response = supabase.table("upload_log").select("file_name").execute()
    return {r["file_name"] for r in response.data}

@st.cache_data(ttl=60)
def load_master(table: str) -> pd.DataFrame:
    supabase = get_supabase()
    response = supabase.table(table).select("*").execute()
    return pd.DataFrame(response.data)

@st.cache_data(ttl=60)
def load_alias_sekolah() -> pd.DataFrame:
    supabase = get_supabase()
    response = supabase.table("master_alias_sekolah").select("*").execute()
    return pd.DataFrame(response.data)

@st.cache_data(ttl=60)
def load_alias_bayar() -> pd.DataFrame:
    supabase = get_supabase()
    response = supabase.table("master_alias_bayar").select("*").execute()
    return pd.DataFrame(response.data)

@st.cache_data(ttl=60)
def get_all_log_files() -> pd.DataFrame:
    supabase = get_supabase()
    response = supabase.table("upload_log").select("*").order("uploaded_at", desc=True).execute()
    return pd.DataFrame(response.data)

# ==========================================
# FUNGSI TULIS DATA (INSERT / UPDATE / DELETE)
# ==========================================
def delete_file(file_name: str):
    supabase = get_supabase()
    supabase.table("transaksi").delete().eq("asal_file", file_name).execute()
    supabase.table("upload_log").delete().eq("file_name", file_name).execute()
    st.cache_data.clear()

def insert_transaksi_bulk(df_list: list, file_info_list: list):
    if not df_list: return
    supabase = get_supabase()
    now = datetime.now().isoformat(timespec="seconds")
    
    df_all = pd.concat(df_list, ignore_index=True)
    df_all["uploaded_at"] = now
    df_all["bulan"] = pd.to_datetime(df_all["date"], dayfirst=True, errors="coerce").dt.strftime("%Y-%m")
    
    # Bersihkan karakter NUL (\x00) yang bisa membuat Supabase error
    for col in df_all.select_dtypes(include=['object']).columns:
        df_all[col] = df_all[col].astype(str).str.replace('\x00', '', regex=False)
        
    # Ubah NaN menjadi None agar valid saat jadi JSON
    df_all = df_all.astype(object).where(pd.notna(df_all), None)
    records = df_all.to_dict(orient="records") # <--- INI YANG TADI HILANG
    
    # 1. Hapus file lama (jika replace)
    for fname, _ in file_info_list:
        supabase.table("transaksi").delete().eq("asal_file", fname).execute()
        supabase.table("upload_log").delete().eq("file_name", fname).execute()
        
    # 2. Insert transaksi (Bagi jadi potongan kecil)
    chunk_size = 50
    for i in range(0, len(records), chunk_size):
        try:
            supabase.table("transaksi").insert(records[i:i+chunk_size]).execute()
        except Exception as e:
            st.error(f"Error detail dari Supabase: {str(e)}")
            raise e
        
    # 3. Insert log
    log_data = []
    for df, (fname, content) in zip(df_list, file_info_list):
        log_data.append({
            "file_name": fname, 
            "file_hash": hashlib.md5(content).hexdigest(), 
            "total_baris": len(df), 
            "uploaded_at": now
        })
    
    supabase.table("upload_log").upsert(log_data).execute()
    st.cache_data.clear()

def upsert_master(table: str, df: pd.DataFrame):
    supabase = get_supabase()
    
    # Tentukan nama kolom PRIMARY KEY untuk masing-masing tabel
    if table == "master_kategori":
        pk_col = "prefix_va"
    else:
        pk_col = "kode" # Untuk master_sekolah dan master_bayar
        
    # Hapus semua data lama menggunakan kolom yang benar
    supabase.table(table).delete().neq(pk_col, "___").execute()
    
    # Masukkan data baru
    if not df.empty:
        records = df.where(pd.notna(df), None).to_dict(orient="records")
        supabase.table(table).insert(records).execute()
        
    st.cache_data.clear()

def save_alias_sekolah(df: pd.DataFrame):
    supabase = get_supabase()
    supabase.table("master_alias_sekolah").delete().neq("kode_bank", "___").execute()
    if not df.empty:
        supabase.table("master_alias_sekolah").insert(df.to_dict(orient="records")).execute()
    st.cache_data.clear()

def save_alias_bayar(df: pd.DataFrame):
    supabase = get_supabase()
    supabase.table("master_alias_bayar").delete().neq("kode_bank", "___").execute()
    if not df.empty:
        supabase.table("master_alias_bayar").insert(df.to_dict(orient="records")).execute()
    st.cache_data.clear()

def update_no_va_bulk_vector(df_target: pd.DataFrame, updates_df: pd.DataFrame):
    if updates_df.empty: return
    supabase = get_supabase()
    
    # Update data satu per satu (Supabase tidak mendukung update bulk kompleks dari dataframe)
    # Tapi kita bisa melakukan update secara paralel/cepat menggunakan upsert jika ID-nya ada
    records = updates_df[["id", "no_va", "prefix_va", "tahun_bayar", "bulan_tp", "kode_sekolah", "kode_bayar"]].to_dict(orient="records")
    
    chunk_size = 100
    for i in range(0, len(records), chunk_size):
        supabase.table("transaksi").upsert(records[i:i+chunk_size]).execute()
        
    st.cache_data.clear()

# ==========================================
# FUNGSI REKONSILIASI
# ==========================================
def get_rekap_bank(bulan_filter: str) -> pd.DataFrame:
    supabase = get_supabase()
    response = supabase.rpc("get_rekap_bank", {"bulan_param": bulan_filter}).execute()
    # Karena kita tidak buat fungsi RPC, kita pakai cara manual (ambil datanya)
    # Tapi cara paling aman adalah ambil semua datanya sesuai bulan, lalu groupby di Pandas
    response = supabase.table("transaksi").select("kode_sekolah, kode_bayar, credit").eq("bulan", bulan_filter).execute()
    df = pd.DataFrame(response.data)
    if df.empty: return pd.DataFrame(columns=["kode_sekolah", "kode_bayar", "total_bank"])
    
    return df.groupby(["kode_sekolah", "kode_bayar"])["credit"].sum().reset_index().rename(columns={"credit": "total_bank"})

def get_detail_bank(bulan: str, kode_sekolah: str, kode_bayar: str) -> pd.DataFrame:
    supabase = get_supabase()
    response = supabase.table("transaksi").select("date, no_va, remark, credit")\
        .eq("bulan", bulan).eq("kode_sekolah", kode_sekolah).eq("kode_bayar", kode_bayar)\
        .order("date", desc=False).execute()
    return pd.DataFrame(response.data)

def get_detail_pic(df_pic_asli: pd.DataFrame, kode_sekolah: str, kode_bayar: str) -> pd.DataFrame:
    return df_pic_asli[(df_pic_asli["kode_sekolah"] == kode_sekolah) & (df_pic_asli["kode_bayar"] == kode_bayar)]

# ==========================================
# FUNGSI BACKUP & RESTORE (Dihilangkan di Cloud)
# ==========================================
def backup_db_bytes() -> bytes:
    return b"" # Tidak dipakai di Cloud

@st.cache_data(ttl=3600) # Cache 1 jam agar tidak membebani database
def get_db_size_mb() -> float:
    """Mengambil ukuran database Supabase dalam MB."""
    supabase = get_supabase()
    try:
        # Menggunakan RPC atau query langsung. 
        # Karena Supabase Python client tidak punya fungsi bawaan untuk ini,
        # kita gunakan query raw ke sistem PostgreSQL.
        response = supabase.rpc("get_db_size").execute()
        return float(response.data)
    except Exception as e:
        # Jika RPC belum dibuat, kita pakai estimasi dari jumlah baris (opsional)
        return 0.0
