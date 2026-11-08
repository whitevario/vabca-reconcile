import re
import pandas as pd

def parse_amount(raw: str) -> float:
    raw = raw.strip()
    if "," in raw and "." in raw:
        if raw.rfind(",") > raw.rfind("."):
            return float(raw.replace(".", "").replace(",", "."))
        return float(raw.replace(",", ""))
    if "," in raw:
        tail = raw.split(",")[-1]
        if len(tail) == 2:
            return float(raw.replace(",", "."))
        return float(raw.replace(",", ""))
    return float(raw.replace(".", ""))

def parse_no_va(no_va: str) -> dict:
    no_va = (no_va or "").strip()
    result = {"prefix_va": "", "kode_sekolah": "", "kode_bayar": ""}
    if len(no_va) < 6:
        return result
    result["kode_bayar"] = no_va[-2:]
    result["kode_sekolah"] = no_va[-4:-2]
    result["prefix_va"] = no_va[:2]
    return result

def nama_bulan_tp(bulan_ke: int) -> str:
    names = ["Jul", "Ags", "Sep", "Okt", "Nov", "Des", "Jan", "Feb", "Mar", "Apr", "Mei", "Jun"]
    if 1 <= bulan_ke <= 12:
        return names[bulan_ke - 1]
    return ""

def parse_txt_content(content: bytes, file_name: str):
    text = content.decode("utf-8", errors="replace")
    lines = text.splitlines()

    rows = []
    failed_lines = []
    sub_comp = ""
    skipped = 0

    match = re.search(r"R-5401_(\d{5})_", file_name)
    comp_code = match.group(1) if match else ""

    for line_num, line in enumerate(lines, start=1):
        m_sc = re.search(r"SUB-COMP\s+(\d+)", line)
        if m_sc:
            sub_comp = m_sc.group(1)
            continue

        m = re.match(
            r"^\s*\d+\s+(\d{8,})\s+(.{1,30}?)\s+IDR\s+([\d\.,]+)\s+"
            r"(\d{2}/\d{2}/\d{2})\s+(\d{2}:\d{2}:\d{2})\s+(.*)$",
            line,
        )
        if not m:
            sampah = ["RETENSI", "SUB TOTAL", "TOTAL NILAI TRANSAKSI", "TOTAL TRANSAKSI", 
                      "LAPORAN", "CABANG", "NAMA PERUSAHAAN", "NO.PELANGGAN", "===", "HALAMAN"]
            
            if line.strip() and not any(x in line for x in sampah):
                skipped += 1
                failed_lines.append(f"Baris ke-{line_num}: {line.strip()}")
            continue

        no_va = m.group(1).strip()
        nama = m.group(2).rstrip()
        amount = parse_amount(m.group(3))
        date_raw = m.group(4)
        time = m.group(5)
        tail = m.group(6) or ""
        
        tail = re.sub(r"\d+", " ", tail).replace("-", " ")
        tail = re.sub(r"\s+", " ", tail).strip()
        remark = f"{nama} {tail}".strip()

        va = parse_no_va(no_va)

        rows.append([
            comp_code, sub_comp, no_va, remark, "IDR", amount, date_raw, time,
            file_name, va["prefix_va"], va["kode_sekolah"], va["kode_bayar"]
        ])

    df = pd.DataFrame(rows, columns=[
        "company_code", "subcompany", "no_va", "remark", "mata_uang", "credit",
        "date_raw", "time", "asal_file", "prefix_va", "kode_sekolah", "kode_bayar",
    ])

    if df.empty:
        return df, skipped, failed_lines

    # --- PROSES VEKTOR (SANGAT CEPAT & SUDAH DIPERBAIKI) ---
   # Bersihkan spasi tersembunyi di teks tanggal
df["date_raw"] = df["date_raw"].astype(str).str.strip()

# Paksa deteksi format. Pandas akan mencoba format umum secara otomatis.
date_dt = pd.to_datetime(df["date_raw"], dayfirst=True, errors="coerce")

# Jika ternyata Pandas gagal membacanya (NaT), kita coba paksa dengan format DD/MM/YY
# (Ini untuk mencegah data November/Desember yang formatnya beda agar tetap terbaca)
mask_gagal = date_dt.isna()
if mask_gagal.any():
    date_dt[mask_gagal] = pd.to_datetime(df.loc[mask_gagal, "date_raw"], format="%d/%m/%y", errors="coerce")
    
    df["date"] = date_dt.dt.strftime("%d/%m/%Y")

    tahun_awal = date_dt.dt.year.where(date_dt.dt.month >= 7, date_dt.dt.year - 1)
    tp_dari_tanggal = tahun_awal.astype(str) + "-" + (tahun_awal + 1).astype(str)

    prefix_digit = df["prefix_va"].str.isdigit() & (df["prefix_va"] != "00") & (df["prefix_va"] != "")
    # PERBAIKAN BUG: Hanya tempel "20" di depan
    th_prefix = pd.to_numeric("20" + df["prefix_va"], errors="coerce")
    
    df["tahun_bayar"] = tp_dari_tanggal
    df.loc[prefix_digit, "tahun_bayar"] = (
        th_prefix[prefix_digit].astype('Int64').astype(str) + "-" + 
        (th_prefix[prefix_digit] + 1).astype('Int64').astype(str)
    )

    bulan_dari_tanggal = date_dt.dt.month.apply(lambda m: m - 6 if m >= 7 else m + 6)
    df["bulan_tp"] = bulan_dari_tanggal
    df.loc[prefix_digit, "bulan_tp"] = 1

    df = df.drop(columns=["date_raw"])
    
    return df, skipped, failed_lines
