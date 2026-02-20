from fastapi import FastAPI, UploadFile, File, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import JSONResponse
import pandas as pd
import io, os, tempfile
from datetime import datetime
from typing import Optional
from pydantic import BaseModel
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Templates
templates = Jinja2Templates(directory="templates")

# Temp file storage (shared across workers on same machine)
UPLOAD_TMP_DIR = tempfile.gettempdir()
UPLOAD_META_PATH = os.path.join(UPLOAD_TMP_DIR, "control_muestras_meta.txt")

def _get_tmp_path(filename: str) -> str:
    """Build the temp file path preserving original extension."""
    ext = ".xlsx" if filename.lower().endswith(".xlsx") else ".xls"
    return os.path.join(UPLOAD_TMP_DIR, f"control_muestras_upload{ext}")

def get_raw_contents():
    """Read uploaded file bytes from shared temp-file path."""
    try:
        fname = get_filename()
        if fname is None:
            return None
        path = _get_tmp_path(fname)
        if os.path.exists(path):
            with open(path, "rb") as f:
                return f.read()
    except Exception as e:
        logger.error(f"get_raw_contents error: {e}")
    return None

def get_filename():
    """Read the original filename from the shared meta text file."""
    try:
        if os.path.exists(UPLOAD_META_PATH):
            with open(UPLOAD_META_PATH, "r") as f:
                v = f.read().strip()
                return v if v else None
    except Exception as e:
        logger.error(f"get_filename error: {e}")
    return None


# In-memory storage (processed DataFrame & stats, single-process)
data_store = {
    "df": None,
    "filename": None,
    "config": {},
    "stats": {"total": 0, "scanned": 0, "missing": 0}
}


class ScanRequest(BaseModel):
    barcode: str
    user: str

class HeaderAnalysisRequest(BaseModel):
    header_row: int

class ConfigurationRequest(BaseModel):
    header_row: int
    data_start_row: int
    sample_col: str
    qaqc_col: Optional[str] = None
    crm_col: Optional[str] = None
    shipment_number: str
    operator_name: str

@app.get("/")
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    if not file.filename.endswith(('.xls', '.xlsx')):
        raise HTTPException(status_code=400, detail="Formato inv\u00e1lido. Use .xls o .xlsx")
    
    try:
        contents = await file.read()
        # Write to shared temp file so ALL workers can access it
        tmp_path = _get_tmp_path(file.filename)
        with open(tmp_path, "wb") as f:
            f.write(contents)
        with open(UPLOAD_META_PATH, "w") as f:
            f.write(file.filename)
        
        # Reset dataframe in case it's a new session
        data_store["df"] = None
        data_store["filename"] = file.filename
        
        return {
            "status": "success", 
            "filename": file.filename,
            "message": "Archivo cargado. Configure las filas."
        }

    except Exception as e:
        logger.error(f"Upload error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/analyze_headers")
async def analyze_headers(req: HeaderAnalysisRequest):
    contents = get_raw_contents()
    filename = get_filename()
    if contents is None or filename is None:
        raise HTTPException(status_code=400, detail="No se ha cargado el archivo. Suba el archivo primero.")
    
    try:
        engine = "openpyxl" if filename.endswith(".xlsx") else None
        header_idx = req.header_row - 1
        if header_idx < 0: header_idx = 0
        
        df = pd.read_excel(io.BytesIO(contents), header=header_idx, engine=engine, nrows=5)
        columns = [str(c).replace('\n', ' ').strip() for c in df.columns]
        
        return {
            "status": "success",
            "columns": columns
        }
    except Exception as e:
         logger.error(f"Header analysis error: {e}")
         raise HTTPException(status_code=400, detail=f"Error leyendo encabezados en fila {req.header_row}: {str(e)}")

@app.post("/configure")
async def configure_app(req: ConfigurationRequest):
    contents = get_raw_contents()
    filename = get_filename()
    if contents is None or filename is None:
        raise HTTPException(status_code=400, detail="No se ha cargado el archivo. Suba el archivo primero.")
    
    try:
        engine = "openpyxl" if filename.endswith(".xlsx") else None
        
        # 1. Read with specific header
        header_idx = req.header_row - 1
        df = pd.read_excel(io.BytesIO(contents), header=header_idx, engine=engine)
        
        # 2. Slice data from data_start_row
        # data_start_row is 1-based absolute row number in Excel
        # header_row is 1-based absolute row number
        # If header=18, data starts=19. 
        # In pandas: header is index 17. Index 0 of df corresponds to Excel Row 19.
        # So we usually don't need to slice if data starts immediately after header.
        # But if there is a gap, we need to handle it.
        # Excel Row N corresponds to DF index (N - HeaderRow - 2) if 0-based? 
        # Example: Header 1 (Index 0). Data Start 2. DF Index 0 is Data Start.
        # Example: Header 18 (Index 17). Data Start 19. DF Index 0 is Data Start.
        # Example: Header 18. Data Start 20. DF Index 0 is Row 19 (skipped). We want Row 20.
        
        rows_to_skip = req.data_start_row - req.header_row - 1
        if rows_to_skip > 0:
            df = df.iloc[rows_to_skip:]
            
        # 3. Rename columns standard
        df.columns = df.columns.astype(str).str.replace('\n', ' ').str.strip()
        
        if req.sample_col not in df.columns:
             raise HTTPException(status_code=400, detail=f"Columna de muestra '{req.sample_col}' no encontrada")
        
        rename_map = {req.sample_col: "N° Muestra"}
        if req.qaqc_col and req.qaqc_col in df.columns:
            rename_map[req.qaqc_col] = "QAQC_Type"
        if req.crm_col and req.crm_col in df.columns:
            rename_map[req.crm_col] = "CRM_Type"
            
        df.rename(columns=rename_map, inplace=True)
        
        # 4. Cleanup
        df["N° Muestra"] = df["N° Muestra"].astype(str).str.strip()
        # Remove NaNs, "nan", "None", empty strings, and ensure it's not just whitespace
        df = df[df["N° Muestra"].notna()]
        df = df[df["N° Muestra"] != "nan"]
        df = df[df["N° Muestra"] != "None"]
        df = df[df["N° Muestra"] != ""]
        # Strict filter: Must have at least one alphanumeric character
        # df = df[df["N° Muestra"].str.contains(r'[a-zA-Z0-9]', na=False)]
        
        # USER REQUEST: Only numbers. Text excluded.
        # We'll try to convert to numeric. If it fails (NaN), we drop it.
        # This allows integers and floats (e.g. 86761, 86761.0) but removes "Text", "86761A"
        df["is_numeric"] = pd.to_numeric(df["N° Muestra"], errors='coerce')
        df = df[df["is_numeric"].notna()]
        df = df.drop(columns=["is_numeric"])
        
        # Ensure it's treated as string string for ID consistency
        # (Though we filtered for numeric, we store ID as string '86761')
        df["N° Muestra"] = df["N° Muestra"].astype(str).str.replace(r'\.0$', '', regex=True) # Remove .0 if present
        
        # Add control columns
        if "Scanned" not in df.columns:
            df["Scanned"] = False
        else:
            # Ensure proper boolean type if re-uploading an exported file
            # Excel might save booleans as TRUE/FALSE strings or 1/0
            df["Scanned"] = df["Scanned"].astype(str).str.upper().map({
                'TRUE': True, 'FALSE': False, '1': True, '0': False, 'YES': True, 'NO': False
            }).fillna(False)
        if "Scan Date" not in df.columns:
            df["Scan Date"] = ""
        if "Scan Time" not in df.columns:
            df["Scan Time"] = ""
        if "Scan User" not in df.columns:
            df["Scan User"] = ""
        if "QAQC_Type" not in df.columns:
            df["QAQC_Type"] = None
        if "CRM_Type" not in df.columns:
            df["CRM_Type"] = None 
            
        # Add Shipment Number
        df["N° Envío"] = req.shipment_number
            
        data_store["df"] = df
        data_store["config"] = req.model_dump() if hasattr(req, 'model_dump') else req.dict()
        
        # Update stats
        data_store["stats"]["total"] = len(df)
        data_store["stats"]["scanned"] = int(df["Scanned"].sum())
        data_store["stats"]["missing"] = data_store["stats"]["total"] - data_store["stats"]["scanned"]
        
        # Determine Next Sample
        next_sample = None
        unscanned = df[~df["Scanned"]]
        if not unscanned.empty:
            first_unscanned = unscanned.iloc[0]
            next_sample = {
                "id": str(first_unscanned["N° Muestra"]),
                "qaqc": str(first_unscanned["QAQC_Type"]) if pd.notna(first_unscanned["QAQC_Type"]) else "Muestra Normal",
                "crm": str(first_unscanned["CRM_Type"]) if pd.notna(first_unscanned["CRM_Type"]) else ""
            }
        
        return {
            "status": "success",
            "total": len(df),
            "next_sample": next_sample
        }
        
    except Exception as e:
        import traceback
        logger.error(f"Configuration error: {traceback.format_exc()}")
        raise HTTPException(status_code=400, detail=f"Error de configuración: {str(e)}")

@app.post("/scan")
async def scan_sample(scan_req: ScanRequest):
    if data_store["df"] is None:
        raise HTTPException(status_code=400, detail="Configuración incompleta")
    
    df = data_store["df"]
    barcode = scan_req.barcode.strip()
    # Use operator from config if available (preferred), else fallback to request
    config_operator = data_store.get("config", {}).get("operator_name")
    user = config_operator if config_operator else scan_req.user.strip()
    
    match = df[df["N° Muestra"] == barcode]
    
    # helper for next sample
    def get_next_sample(dataframe):
        unscanned = dataframe[~dataframe["Scanned"]]
        if not unscanned.empty:
            first = unscanned.iloc[0]
            return {
                "id": str(first["N° Muestra"]),
                "qaqc": str(first["QAQC_Type"]) if pd.notna(first["QAQC_Type"]) else "Muestra Normal",
                "crm": str(first["CRM_Type"]) if pd.notna(first["CRM_Type"]) else ""
            }
        return None

    if match.empty:
        return JSONResponse(content={
            "status": "not_found", 
            "barcode": barcode,
            "next_sample": get_next_sample(df)
        }, status_code=404)
    
    idx = match.index[0]
    
    # Get QAQC Info
    qaqc_val = df.at[idx, "QAQC_Type"]
    qaqc_display = "Muestra Normal"
    if pd.notna(qaqc_val) and str(qaqc_val).strip() != "":
        qaqc_display = str(qaqc_val)
        
    crm_val = df.at[idx, "CRM_Type"]
    crm_display = ""
    if pd.notna(crm_val) and str(crm_val).strip() != "":
        crm_display = str(crm_val)
    
    # Strict Duplicate Check: Return error, DO NOT update
    if df.at[idx, "Scanned"]:
        return JSONResponse(content={
            "status": "duplicate_error", 
            "detail": f"La muestra {barcode} ya fue escaneada previamente.",
            "barcode": barcode, 
            "qaqc_type": qaqc_display,
            "crm_type": crm_display,
            "next_sample": get_next_sample(df)
        })
    
    now_dt = datetime.now()
    now_date = now_dt.strftime("%Y-%m-%d")
    now_time = now_dt.strftime("%H:%M:%S")
    
    df.at[idx, "Scanned"] = True
    df.at[idx, "Scan Date"] = now_date
    df.at[idx, "Scan Time"] = now_time
    df.at[idx, "Scan User"] = user
    
    data_store["stats"]["scanned"] += 1
    data_store["stats"]["missing"] -= 1
    
    row_data = match.iloc[0].to_dict()
    clean_data = {}
    for k, v in row_data.items():
        if pd.isna(v):
            clean_data[k] = None
        else:
            clean_data[k] = v

    # Safe dictionary construction
    response_data = {
        "status": "success", 
        "data": clean_data, 
        "stats": data_store["stats"],
        "qaqc_type": qaqc_display,
        "crm_type": crm_display,
        "next_sample": get_next_sample(df)
    }
    return response_data

@app.get("/get_data")
async def get_data():
    if data_store["df"] is None:
        return {"data": []}
    
    # 1. Replace NaN/None with None (which becomes null in JSON)
    df_clean = data_store["df"].where(pd.notnull(data_store["df"]), None)
    
    # 2. Handle specific types that might break JSON serialization
    # Convert Timestamp/datetime objects to strings
    for col in df_clean.columns:
        if pd.api.types.is_datetime64_any_dtype(df_clean[col]):
            df_clean[col] = df_clean[col].astype(str).replace({"NaT": None, "nan": None})
            
    # Convert potential numpy types to native Python types via to_dict
    records = df_clean.to_dict(orient="records")
    
    # Double check for NaN scalars in the list of dicts (sometimes they persist)
    # A simple way is to iterate and clean, but pandas .where usually handles it.
    # Let's ensure strict compatibility.
    import numpy as np
    def clean_record(record):
        new_record = {}
        for k, v in record.items():
            if v is None:
                new_record[k] = None
            elif isinstance(v, float) and np.isnan(v):
                new_record[k] = None
            else:
                new_record[k] = v
        return new_record

    cleaned_records = [clean_record(r) for r in records]
    
    return {"data": cleaned_records}

@app.post("/reset")
async def reset_session():
    data_store["df"] = None
    data_store["raw_contents"] = None
    data_store["filename"] = None
    data_store["config"] = {}
    data_store["stats"] = {"total": 0, "scanned": 0, "missing": 0}
    return {"status": "success"}

class SetStartIndexRequest(BaseModel):
    sample_id: str

@app.post("/set_start_index")
async def set_start_index(req: SetStartIndexRequest):
    if data_store["df"] is None:
        raise HTTPException(status_code=400, detail="No data loaded")
    
    df = data_store["df"]
    target_id = req.sample_id.strip()
    
    # Verify if ID exists
    match = df[df["N° Muestra"] == target_id]
    if match.empty:
        raise HTTPException(status_code=404, detail="Muestra no encontrada")
    
    # Logic: Mark all SAMPLES BEFORE this one as "Scanned" (skipped) or just Scanned?
    # User said "indicar desde donde iniciara". Usually implies skipping previous ones.
    # Let's mark previous unscanned rows as "Skipped" to clean up the queue?
    # Or simply: The "Next Sample" logic finds the FIRST UNSCANNED. 
    # So if we want to start at X, we must ensure X is the first unscanned.
    # This implies marking everything before X as Scanned (or Skipped).
    
    target_idx = match.index[0]
    
    # Mark all rows before target_idx as Scanned = True (if not already)
    # We'll use a special user "SKIPPED" to denote this if desired, or just "System".
    
    # Get all indices before target
    # Assuming dataframe is ordered by file order? Yes.
    
    # We need to be careful with index if it's not monotonic increasing range, but it should be standard RangeIndex from read_excel
    # Let's rely on position using iloc/index
    
    # Find position of target_idx
    # loc uses labels, iloc uses position. 
    # If we haven't sorted or filtered much (except cleanup), index might be original.
    
    # Let's iterate and mark.
    current_time = datetime.now().strftime("%H:%M:%S")
    current_date = datetime.now().strftime("%Y-%m-%d")
    
    rows_updated = 0
    for idx in df.index:
        if idx == target_idx:
            break # Reached target, stop
            
        if not df.at[idx, "Scanned"]:
            df.at[idx, "Scanned"] = True
            df.at[idx, "Scan User"] = "OMITIDO"
            df.at[idx, "Scan Date"] = current_date
            df.at[idx, "Scan Time"] = current_time
            rows_updated += 1
            
    # Update stats
    data_store["stats"]["scanned"] = int(df["Scanned"].sum())
    data_store["stats"]["missing"] = data_store["stats"]["total"] - data_store["stats"]["scanned"]
    
    # Get next sample (should be target now)
    def get_next():
        unscanned = df[~df["Scanned"]]
        if not unscanned.empty:
            first = unscanned.iloc[0]
            return {
                "id": str(first["N° Muestra"]),
                "qaqc": str(first["QAQC_Type"]) if pd.notna(first["QAQC_Type"]) else "Muestra Normal",
                "crm": str(first["CRM_Type"]) if pd.notna(first["CRM_Type"]) else ""
            }
        return None

    return {
        "status": "success",
        "detail": f"Se omitieron {rows_updated} muestras anteriores.",
        "next_sample": get_next()
    }

@app.get("/export")
async def export_excel():
    if data_store["df"] is None:
        raise HTTPException(status_code=400, detail="No data")
    
    from fastapi import Response
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        data_store["df"].to_excel(writer, index=False)
    output.seek(0)
    
    headers = {
        'Content-Disposition': f'attachment; filename="scanned_{data_store["filename"]}"'
    }
    return Response(content=output.getvalue(), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers=headers)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
