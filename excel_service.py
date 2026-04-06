import pandas as pd
import os
import datetime

EXCEL_FILE = 'Turnos.xlsx'

def normalize_planta(planta_str):
    """Normalize planta name to standard format"""
    if not planta_str:
        return "Planta Central"
    planta_str = str(planta_str)
    if 'PIBERA' in planta_str.upper() or 'LELOIR' in planta_str.upper() or '36-' in planta_str:
        return 'Pibera'
    elif 'BARRACAS' in planta_str.upper() or 'BIOSINTEX' in planta_str.upper() or '1-' in planta_str:
        return 'Barracas'
    return planta_str

def get_excel_last_modified():
    """Returns the last modification date of the Excel file"""
    if not os.path.exists(EXCEL_FILE):
        return None
    try:
        timestamp = os.path.getmtime(EXCEL_FILE)
        return datetime.datetime.fromtimestamp(timestamp).strftime('%d/%m/%Y %H:%M')
    except Exception:
        return None

def get_turnos_df():
    if not os.path.exists(EXCEL_FILE):
        return pd.DataFrame()
    try:
        df = pd.read_excel(EXCEL_FILE, header=2)
        return df
    except Exception as e:
        print(f"Error reading Excel: {e}")
        return pd.DataFrame()

def get_oc_details_list(proveedor_id, oc_number):
    """
    Returns a LIST of matching rows for a given OC prefix.
    If multiple subdivisions (/001, /002) exist, the provider will choose from this list.
    """
    df = get_turnos_df()
    if df.empty:
        return []

    # Find columns
    oc_col = next((c for c in df.columns if str(c).strip().lower() == 'orden de compra'), None)
    if not oc_col:
        oc_col = next((c for c in df.columns if 'Orden de Compra' in str(c) and 'Observaci' not in str(c)), None)
        
    prov_col = next((c for c in df.columns if str(c).strip().lower() == 'proveedor'), None)
    if not prov_col:
        prov_col = next((c for c in df.columns if 'Proveedor' in str(c) and 'Nombre' not in str(c) and 'Codigo' not in str(c)), None)
        
    planta_col = next((c for c in df.columns if 'Lugar' in str(c)), None)
    art_col = next((c for c in df.columns if 'Art' in str(c) and 'culo' in str(c) and 'Proveedor' not in str(c)), None)
    nom_col = next((c for c in df.columns if 'Nombre_1' in str(c)), None)
    
    qty_col = next((c for c in df.columns if 'Pendiente' in str(c) and 'Entrega' in str(c)), None)
    if not qty_col:
        qty_col = next((c for c in df.columns if 'Cantidad Pediente' in str(c)), None)

    # Column Q: Fecha Entrega (usually 17th column, index 16)
    # We find it by looking for 'Fecha Entrega' or 'Entrega' after the 10th column
    delivery_date_col = next((c for c in df.columns if 'Fecha Entrega' in str(c)), None)
    if not delivery_date_col:
        # Fallback to column index 16 if 'Fecha' is not obvious
        if len(df.columns) > 16:
            delivery_date_col = df.columns[16]

    if not all([oc_col, prov_col, planta_col, art_col, qty_col]):
        print(f"Missing mandatory columns for OC search.")
        return []
    
    # Matching
    matches = df[df[oc_col].astype(str).str.contains(str(oc_number), na=False)]
    
    results = []
    for _, row in matches.iterrows():
        row_prov = str(row[prov_col]).strip()
        # Authorization check
        if str(proveedor_id).strip() != row_prov and str(proveedor_id).strip() != "1000":
            continue
            
        delivery_date = row[delivery_date_col]
        delivery_date_str = ""
        if pd.notnull(delivery_date):
            if isinstance(delivery_date, datetime.datetime):
                delivery_date_str = delivery_date.strftime('%Y-%m-%d')
            else:
                delivery_date_str = str(delivery_date)

        results.append({
            'oc': str(row[oc_col]),
            'proveedor': row_prov,
            'planta': normalize_planta(row[planta_col]),
            'articulo': str(row[art_col]),
            'nombre_articulo': str(row[nom_col]),
            'cantidad_pendiente': str(row[qty_col]),
            'fecha_entrega_q': delivery_date_str  # Column Q limit
        })
    
    return results

def get_supplier_info(proveedor_id):
    """
    Given a supplier ID, get their Name_2 (Nombre del proveedor)
    """
    df = get_turnos_df()
    if df.empty:
        return None
        
    prov_col = next((c for c in df.columns if 'Proveedor' in c and 'Nombre' not in c and 'Codigo' not in c), None)
    name_col = next((c for c in df.columns if 'Nombre_2' in c), None)
    
    if not all([prov_col, name_col]):
        return None
        
    match = df[df[prov_col].astype(str) == str(proveedor_id).strip()]
    if match.empty:
        return None
        
    return str(match.iloc[0][name_col])
