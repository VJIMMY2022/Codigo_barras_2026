from fastapi import FastAPI, UploadFile, File, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import JSONResponse
import pandas as pd
import io
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

# In-memory storage
data_store = {
    "df": None,
    "raw_contents": None, # Store raw bytes to re-parse with different settings
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

@app.get("/")
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    if not file.filename.endswith(('.xls', '.xlsx')):
        raise HTTPException(status_code=400, detail="Formato inválido. Use .xls o .xlsx")
    
    try:
        contents = await file.read()
        data_store["raw_contents"] = contents
        data_store["filename"] = file.filename
        
        # Determine engine
        engine = "openpyxl" if file.filename.endswith(".xlsx") else None
        
        # Initial peek to guess header (defaulting to user preference 18 if possible, or auto)
        # We will just return success and let frontend trigger the analyze step with defaults
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
    if data_store["raw_contents"] is None:
        raise HTTPException(status_code=400, detail="No file loaded")
    
    try:
        contents = data_store["raw_contents"]
        engine = "openpyxl" if data_store["filename"].endswith(".xlsx") else None
        
        # Pandas uses 0-based index. User gives 1-based row number.
        # If User says Row 18, that is index 17.
        header_idx = req.header_row - 1
        
        if header_idx < 0: header_idx = 0
        
        df = pd.read_excel(io.BytesIO(contents), header=header_idx, engine=engine, nrows=5) # Read only a few rows to get columns
        
        # Normalize columns
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
    if data_store["raw_contents"] is None:
        raise HTTPException(status_code=400, detail="No file loaded")
    
    try:
        contents = data_store["raw_contents"]
        engine = "openpyxl" if data_store["filename"].endswith(".xlsx") else None
        
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
            
        df.rename(columns=rename_map, inplace=True)
        
        # 4. Cleanup
        df["N° Muestra"] = df["N° Muestra"].astype(str).str.strip()
        # Remove NaNs or generic placeholders
        df = df[df["N° Muestra"] != "nan"]
        df = df[df["N° Muestra"] != "None"]
        df = df[df["N° Muestra"] != ""]
        
        # Add control columns
        if "Scanned" not in df.columns:
            df["Scanned"] = False
        if "Scan Timestamp" not in df.columns:
            df["Scan Timestamp"] = ""
        if "Scan User" not in df.columns:
            df["Scan User"] = ""
        if "QAQC_Type" not in df.columns:
            df["QAQC_Type"] = None 
            
        data_store["df"] = df
        data_store["config"] = req.dict()
        
        # Update stats
        data_store["stats"]["total"] = len(df)
        data_store["stats"]["scanned"] = int(df["Scanned"].sum())
        data_store["stats"]["missing"] = data_store["stats"]["total"] - data_store["stats"]["scanned"]
        
        return {
            "status": "success",
            "total": len(df)
        }
        
    except Exception as e:
        logger.error(f"Configuration error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/scan")
async def scan_sample(scan_req: ScanRequest):
    if data_store["df"] is None:
        raise HTTPException(status_code=400, detail="Configuración incompleta")
    
    df = data_store["df"]
    barcode = scan_req.barcode.strip()
    user = scan_req.user.strip()
    
    match = df[df["N° Muestra"] == barcode]
    
    if match.empty:
        return JSONResponse(content={"status": "not_found", "barcode": barcode}, status_code=404)
    
    idx = match.index[0]
    
    # Get QAQC Info
    qaqc_val = df.at[idx, "QAQC_Type"]
    qaqc_display = "Muestra Normal"
    if pd.notna(qaqc_val) and str(qaqc_val).strip() != "":
        qaqc_display = str(qaqc_val)
    
    if df.at[idx, "Scanned"]:
        return JSONResponse(content={
            "status": "duplicate", 
            "barcode": barcode, 
            "timestamp": df.at[idx, "Scan Timestamp"],
            "scanned_by": df.at[idx, "Scan User"],
            "qaqc_type": qaqc_display
        })
    
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    df.at[idx, "Scanned"] = True
    df.at[idx, "Scan Timestamp"] = now
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

    return {
        "status": "success", 
        "data": clean_data, 
        "stats": data_store["stats"],
        "qaqc_type": qaqc_display
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
