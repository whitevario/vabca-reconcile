import sqlite3
import hashlib
from datetime import datetime
from pathlib import Path
import pandas as pd
import streamlit as st
from supabase import create_client, Client

# ==========================================
# KONFIGURASI SUPABASE
# ==========================================
SUPABASE_URL = st.secrets.get("supabase", {}).get("url", "URL_SUPABASE_KAMU")
SUPABASE_KEY = st.secrets.get("supabase", {}).get("key", "KEY_SUPABASE_KAMU")

@st.cache_resource
def get_supabase() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_KEY)

def get_conn():
    """Fungsi dummy agar tidak error saat dipanggil kode lama."""
    return get_supabase()

def init_db():
    """Tabel sudah dibuat lewat SQL Editor, jadi fungsi ini kosong."""
    pass

@st.cache_data(ttl=3600)
def get_db_size_mb() -> float:
    supabase = get_supabase()
    try:
        response = supabase.rpc("get_db_size").execute()
        return float(response.data)
    except Exception:
        return 0.0

# ==========================================
# FUNGSI BACA DATA
# ==========================================
@st.cache_data(ttl=10)
def load_all_transaksi() -> pd.DataFrame:
    supabase = get_supabase()
    all_data = []
    limit = 1000
    start = 0
    
    while True:
        response = supabase.table("transaksi").select("*").range(start, start + limit - 1).execute()
        if not response.data:
            break
        all_data.extend(response.data)
        start += limit
        
    df = pd.DataFrame(all_data)
    if not df.empty:
        df = df.sort_values(by="id", ascending=False).reset_index(drop=True)
    return df

@st.cache_data(ttl=3600)
def get_list_bulan() -> list:
    supabase = get_supabase()
    response = supabase.table("transaksi").select("bulan").execute()
    df = pd.DataFrame(response.data)
    if df.empty: return []
    return sorted(df["bulan"].dropna().unique().tolist(), reverse=True)

@st.cache_data(ttl=3600)
def get_existing_files() -> set[str]:
    supabase = get_supabase()
    response = supabase.table("upload_log").select("file_name").execute()
    return {r["file_name"] for r in response.data}

@st.cache_data(ttl=3600)
def load_master(table: str) -> pd.DataFrame:
    supabase = get_supabase()
    response = supabase.table(table).select("*").execute()
    return pd.DataFrame(response.data)

@st.cache_data(ttl=3600)
def load_alias_sekolah() -> pd.DataFrame:
    supabase = get_supabase()
    response = supabase.table("master_alias_sekolah").select("*").execute()
    return pd.DataFrame(response.data)

@st.cache_data(ttl=3600)
def load_alias_bayar() -> pd.DataFrame:
    supabase = get_supabase()
    response = supabase.table("master_alias_bayar").select("*").execute()
    return pd.DataFrame(response.data)

@st.cache_data(ttl=3600)
def get_all_log_files() -> pd.DataFrame:
    supabase = get_supabase()
    response = supabase.table("upload_log").select("*").order("uploaded_at", desc=True).execute()
    return pd.DataFrame(response.data)

# ==========================================
# FUNGSI TULIS DATA
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
    df_all["bulan"] = pd.to_datetime(df_all["date"], format="%d/%m/%Y", errors="coerce").dt.strftime("%Y-%m")
    
    for col in df_all.select_dtypes(include=['object']).columns:
        df_all[col] = df_all[col].astype(str).str.replace('\x00', '', regex=False)
        
    df_all = df_all.astype(object).where(pd.notna(df_all), None)
    records = df_all.to_dict(orient="records")
    
    # Hapus file lama (jika replace) secara sekaligus
    for fname, _ in file_info_list:
        supabase.table("transaksi").delete().eq("asal_file", fname).execute()
        supabase.table("upload_log").delete().eq("file_name", fname).execute()
        
    # Insert transaksi (Perbesar chunk_size menjadi 1000 agar cepat)
    chunk_size = 1000 
    for i in range(0, len(records), chunk_size):
        try:
            supabase.table("transaksi").insert(records[i:i+chunk_size]).execute()
        except Exception as e:
            st.error(f"Error detail dari Supabase (Transaksi): {str(e)}")
            raise e
        
    # Insert log
    log_data = []
    for df, (fname, content) in zip(df_list, file_info_list):
        clean_fname = str(fname).replace('\x00', '')
        log_data.append({
            "file_name": clean_fname, 
            "file_hash": hashlib.md5(content).hexdigest(), 
            "total_baris": len(df), 
            "uploaded_at": now
        })
    
    for log in log_data:
        supabase.table("upload_log").upsert(log).execute()
        
    st.cache_data.clear()

def upsert_master(table: str, df: pd.DataFrame):
    supabase = get_supabase()
    pk_col = "prefix_va" if table == "master_kategori" else "kode"
    supabase.table(table).delete().neq(pk_col, "___").execute()
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
    
    records = updates_df[["id", "no_va", "prefix_va", "tahun_bayar", "bulan_tp", "kode_sekolah", "kode_bayar"]].to_dict(orient="records")
    
    chunk_size = 500
    for i in range(0, len(records), chunk_size):
        try:
            supabase.table("transaksi").upsert(records[i:i+chunk_size]).execute()
        except Exception as e:
            st.error(f"Error detail dari Supabase: {str(e)}")
            raise e
        
    st.cache_data.clear()

# ==========================================
# FUNGSI REKONSILIASI
# ==========================================
def get_rekap_bank(bulan_filter: str) -> pd.DataFrame:
    supabase = get_supabase()
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
