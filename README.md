# Sistema de Control de Muestras con Código de Barras

Una aplicación web moderna para la verificación y control de muestras mediante escaneo de códigos de barras, diseñada para integrarse con flujos de trabajo basados en Excel.

## Características

* **Carga de Excel Configurable**: Permite definir fila de encabezados, inicio de datos y columnas clave (Muestra, QAQC).
* **Interfaz Moderna**: Diseño oscuro con efectos "glassmorphism" y feedback visual/auditivo.
* **Validación en Tiempo Real**: Detecta duplicados, muestras no encontradas y muestra el tipo de control (QAQC).
* **Exportación**: Permite descargar el Excel actualizado con el estado de escaneo, usuario y fecha.
* **Local**: Funciona en tu propia máquina, manteniendo tus datos seguros.

## Requisitos

* Python 3.8 o superior
* Navegador web moderno (Chrome, Edge, Firefox)

## Instalación

1. **Clonar el repositorio:**

    ```bash
    git clone https://github.com/VJIMMY2022/Codigo_barras_2026.git
    cd Codigo_barras_2026
    ```

2. **Instalar dependencias:**

    ```bash
    pip install -r requirements.txt
    ```

## Ejecución

1. **Iniciar la aplicación:**
    Ejecuta el archivo `run_app.bat` (en Windows) o usa el comando:

    ```bash
    uvicorn app:app --reload
    ```

2. **Abrir en el navegador:**
    La aplicación se abrirá automáticamente en: `http://127.0.0.1:8000`

## Uso

1. **Subir Archivo**: Arrastra tu archivo `.xls` o `.xlsx`.
2. **Configurar**: Indica en qué fila están los encabezados y selecciona las columnas de "N° Muestra" y "QAQC".
3. **Escanear**: Usa tu lector de código de barras o escribe el código.
4. **Exportar**: Al finalizar, descarga el reporte actualizado.

## Despliegue en Render (Gratis)

Para publicar tu aplicación en internet:

1. Sube tu código a GitHub (si no lo has hecho).
2. Créate una cuenta en [Render.com](https://render.com).
3. Haz clic en **"New + "** y selecciona **"Web Service"**.
4. Conecta tu cuenta de GitHub y selecciona este repositorio (`Codigo_barras_2026`).
5. Render detectará automáticamente el archivo `render.yaml` o la configuración.
6. Haz clic en **"Create Web Service"**.
7. ¡Listo! En unos minutos te dará una URL (ej: `https://codigo-barras.onrender.com`) para compartir.

> **Nota**: En la versión gratuita, la aplicación puede tardar unos segundos en "despertar" si nadie la ha usado en un tiempo. Además, los datos cargados se borrarán si la aplicación se reinicia (ya que no usa base de datos permanente).
