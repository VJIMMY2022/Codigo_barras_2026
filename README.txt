# CONTROL DE MUESTRAS - SCANNER

## Instrucciones de Uso

1. **Iniciar la Aplicación**:
   - Haz doble clic en el archivo `run_app.bat`.
   - Se abrirá una ventana negra (consola) instalando lo necesario.
   - Automáticamente se abrirá tu navegador en la aplicación.

2. **Cargar Muestras**:
   - En la pantalla de inicio, arrastra tu archivo Excel.
   - La aplicación leerá la columna "N° Muestra" automáticamente.

3. **Escanear**:
   - Conecta tu lector de código de barras.
   - Asegúrate de que el cursor esté en la caja de texto central.
   - Escanea las muestras.
   - Verás en verde las correctas, en amarillo las duplicadas y en rojo las que no están en el Excel.

4. **Exportar**:
   - Al finalizar, haz clic en "Exportar Excel Actualizado" al final de la página.
   - Se descargará un archivo con las columnas "Scanned", "Scan Timestamp" y "Scan User" llenas.

## Solución de Problemas
- Si el navegador no abre, ve a: http://127.0.0.1:8000
- Si dice "Puerto ocupado", cierra otras ventanas de consola negra y vuelve a intentar.
