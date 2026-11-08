"""
Helper untuk export DataFrame ke Excel dengan format rapi:
- Header bold + background
- Lebar kolom otomatis
- Baris TOTAL (opsional)
- Format angka Rp
"""
import pandas as pd
from io import BytesIO
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter


HEADER_FILL = PatternFill("solid", fgColor="1F4E78")
HEADER_FONT = Font(bold=True, color="FFFFFF", size=11)
TOTAL_FILL = PatternFill("solid", fgColor="FFE699")
TOTAL_FONT = Font(bold=True)
BORDER = Border(
    left=Side(style="thin", color="BFBFBF"),
    right=Side(style="thin", color="BFBFBF"),
    top=Side(style="thin", color="BFBFBF"),
    bottom=Side(style="thin", color="BFBFBF"),
)


def to_excel(
    df: pd.DataFrame,
    sheet_name: str = "Laporan",
    total_row: bool = False,
    rp_columns: list[str] = None,
) -> bytes:
    """
    Konversi DataFrame ke bytes Excel dengan format rapi.
    
    Args:
        df: DataFrame
        sheet_name: nama sheet
        total_row: kalau True, tambah baris TOTAL di bawah
        rp_columns: kolom yang diformat Rp (misal ['credit', 'nominal'])
    """
    rp_columns = rp_columns or []
    buffer = BytesIO()

    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name=sheet_name, startrow=0)
        ws = writer.sheets[sheet_name]

        n_rows = len(df)
        n_cols = len(df.columns)

        # Header
        for col_idx in range(1, n_cols + 1):
            c = ws.cell(row=1, column=col_idx)
            c.fill = HEADER_FILL
            c.font = HEADER_FONT
            c.alignment = Alignment(horizontal="center", vertical="center")
            c.border = BORDER

        # Baris data
        for row_idx in range(2, n_rows + 2):
            for col_idx in range(1, n_cols + 1):
                c = ws.cell(row=row_idx, column=col_idx)
                c.border = BORDER
                col_name = df.columns[col_idx - 1]
                if col_name in rp_columns and isinstance(c.value, (int, float)):
                    c.number_format = 'Rp #,##0'
                    c.alignment = Alignment(horizontal="right")

        # Baris TOTAL
        if total_row and n_rows > 0:
            total_row_idx = n_rows + 2
            for col_idx in range(1, n_cols + 1):
                c = ws.cell(row=total_row_idx, column=col_idx)
                c.fill = TOTAL_FILL
                c.font = TOTAL_FONT
                c.border = BORDER
                col_name = df.columns[col_idx - 1]
                if col_idx == 1:
                    c.value = "TOTAL"
                elif col_name in rp_columns:
                    c.value = df[col_name].sum()
                    c.number_format = 'Rp #,##0'
                    c.alignment = Alignment(horizontal="right")

        # Lebar kolom otomatis
        for col_idx in range(1, n_cols + 1):
            col_letter = get_column_letter(col_idx)
            max_len = 0
            for row_idx in range(1, n_rows + 3):
                v = ws.cell(row=row_idx, column=col_idx).value
                if v is not None:
                    max_len = max(max_len, len(str(v)))
            ws.column_dimensions[col_letter].width = min(max_len + 4, 40)

    return buffer.getvalue()


def pivot_to_excel(
    pivot_df: pd.DataFrame,
    sheet_name: str = "Pivot",
    add_total: bool = True,
) -> bytes:
    """
    Export tabel pivot (dengan index) ke Excel.
    Tambah baris/kolom TOTAL kalau diminta.
    """
    buffer = BytesIO()

    # Reset index agar index jadi kolom biasa
    export_df = pivot_df.reset_index()

    # Tambah baris TOTAL
    if add_total:
        numeric_cols = export_df.select_dtypes(include="number").columns.tolist()
        if numeric_cols:
            total_row = {}
            for col in export_df.columns:
                if col in numeric_cols:
                    total_row[col] = export_df[col].sum()
                elif col == export_df.columns[0]:
                    total_row[col] = "TOTAL"
                else:
                    total_row[col] = ""
            export_df = pd.concat(
                [export_df, pd.DataFrame([total_row])],
                ignore_index=True,
            )

    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        export_df.to_excel(writer, index=False, sheet_name=sheet_name)
        ws = writer.sheets[sheet_name]

        n_rows = len(export_df)
        n_cols = len(export_df.columns)
        numeric_cols = export_df.select_dtypes(include="number").columns.tolist()

        # Header
        for col_idx in range(1, n_cols + 1):
            c = ws.cell(row=1, column=col_idx)
            c.fill = HEADER_FILL
            c.font = HEADER_FONT
            c.alignment = Alignment(horizontal="center", vertical="center")
            c.border = BORDER

        # Isi
        for row_idx in range(2, n_rows + 2):
            is_total_row = add_total and row_idx == n_rows + 1
            for col_idx in range(1, n_cols + 1):
                c = ws.cell(row=row_idx, column=col_idx)
                c.border = BORDER
                if is_total_row:
                    c.fill = TOTAL_FILL
                    c.font = TOTAL_FONT
                col_name = export_df.columns[col_idx - 1]
                if col_name in numeric_cols and isinstance(c.value, (int, float)):
                    c.number_format = 'Rp #,##0'
                    c.alignment = Alignment(horizontal="right")

        # Lebar kolom
        for col_idx in range(1, n_cols + 1):
            col_letter = get_column_letter(col_idx)
            max_len = 0
            for row_idx in range(1, n_rows + 2):
                v = ws.cell(row=row_idx, column=col_idx).value
                if v is not None:
                    max_len = max(max_len, len(str(v)))
            ws.column_dimensions[col_letter].width = min(max_len + 4, 40)

    return buffer.getvalue()
