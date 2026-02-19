document.addEventListener('DOMContentLoaded', () => {
    // Elements
    const fileInput = document.getElementById('fileInput');
    const uploadSection = document.getElementById('uploadSection');

    // Config Section Elements
    const configSection = document.getElementById('configSection');
    const headerRowInput = document.getElementById('headerRowInput');
    const dataRowInput = document.getElementById('dataRowInput');
    const loadColumnsBtn = document.getElementById('loadColumnsBtn');
    const columnSelectors = document.getElementById('columnSelectors');
    const sampleColSelect = document.getElementById('sampleColSelect');
    const qaqcColSelect = document.getElementById('qaqcColSelect');
    const confirmConfigBtn = document.getElementById('confirmConfigBtn');

    // Scan Section Elements
    const scanSection = document.getElementById('scanSection');
    const recentScans = document.getElementById('recentScans');
    const barcodeInput = document.getElementById('barcodeInput');
    const feedbackMsg = document.getElementById('scanFeedback');
    const scanList = document.getElementById('scanList');
    const footerActions = document.getElementById('footerActions');
    const exportBtn = document.getElementById('exportBtn');

    // Stats Elements
    const scanCountEl = document.getElementById('scannedCount');
    const missingCountEl = document.getElementById('missingCount');
    const totalCountEl = document.getElementById('totalCount');
    const filenameDisplay = document.getElementById('filenameDisplay');

    // 1. File Upload
    fileInput.addEventListener('change', async (e) => {
        const file = e.target.files[0];
        if (!file) return;

        const formData = new FormData();
        formData.append('file', file);

        showFeedback('Subiendo archivo...', 'neutral');

        try {
            const response = await fetch('/upload', {
                method: 'POST',
                body: formData
            });

            const result = await response.json();

            if (response.ok) {
                // Show Config Section
                uploadSection.classList.add('hidden');
                configSection.classList.remove('hidden');
                filenameDisplay.textContent = result.filename;

                // Trigger auto-load of columns with default values if possible
                // loadColumnsBtn.click(); // Optional: Auto-click
                showFeedback('', 'neutral');
            } else {
                alert('Error: ' + result.detail);
                showFeedback('Error de carga', 'error');
            }
        } catch (error) {
            console.error(error);
            alert('Error de conexión');
        }
    });

    // 2. Load Columns based on Header Row
    loadColumnsBtn.addEventListener('click', async () => {
        const headerRow = parseInt(headerRowInput.value);
        if (isNaN(headerRow)) {
            alert("Ingrese un número de fila válido");
            return;
        }

        try {
            const response = await fetch('/analyze_headers', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ header_row: headerRow })
            });

            const result = await response.json();

            if (response.ok) {
                // Populate Selects
                populateSelect(sampleColSelect, result.columns, ['muestras', 'muestra', 'sample', 'id', 'código', 'codigo']);
                populateSelect(qaqcColSelect, result.columns, ['qaqc', 'control', 'std', 'tipo']);

                // Show Selectors
                columnSelectors.classList.remove('hidden');
            } else {
                alert('Error al leer columnas: ' + result.detail);
            }
        } catch (error) {
            console.error(error);
            alert('Error al analizar archivo');
        }
    });

    // 3. Confirm Configuration
    confirmConfigBtn.addEventListener('click', async () => {
        const shipmentVal = document.getElementById('shipmentInput').value;
        const operatorVal = document.getElementById('operatorInput').value;

        if (!shipmentVal.trim()) {
            alert("Ingrese un Número de Envío");
            return;
        }
        if (!operatorVal.trim()) {
            alert("Ingrese el Nombre del Operador");
            return;
        }

        const config = {
            header_row: parseInt(headerRowInput.value),
            data_start_row: parseInt(dataRowInput.value),
            sample_col: sampleColSelect.value,
            qaqc_col: qaqcColSelect.value || null,
            shipment_number: shipmentVal,
            operator_name: operatorVal
        };

        if (!config.sample_col) {
            alert("Debe seleccionar la columna de Muestras");
            return;
        }

        try {
            const response = await fetch('/configure', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(config)
            });

            const result = await response.json();

            if (response.ok) {
                // Transition to Scan
                configSection.classList.add('hidden');
                scanSection.classList.remove('hidden');
                recentScans.classList.remove('hidden');
                footerActions.classList.remove('hidden');

                // Update Badge
                document.getElementById('headerOperatorDisplay').textContent = operatorVal;

                // Init Stats
                totalCountEl.textContent = result.total;
                missingCountEl.textContent = result.total;

                // Init Next Sample
                updateNextSample(result.next_sample);

                showFeedback('Configurado. Envío: ' + shipmentVal, 'success');
                barcodeInput.focus();
            } else {
                alert('Error: ' + result.detail);
            }
        } catch (error) {
            console.error(error);
            alert('Error de configuración');
        }
    });

    // Scanner Handler
    barcodeInput.addEventListener('keydown', async (e) => {
        if (e.key === 'Enter') {
            const barcode = barcodeInput.value;
            // User is now in config, but we send it just in case logic depends on it, 
            // though backend prefers config value now.
            if (!barcode) return;
            barcodeInput.value = '';

            await processScan(barcode);
        }
    });

    async function processScan(barcode) {
        try {
            const response = await fetch('/scan', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ barcode, user: "ConfiguredUser" })
            });

            const result = await response.json();

            if (result.status === 'success') {
                showFeedback(`${barcode} OK`, 'success');
                addToList(result.data, 'success', result.qaqc_type);
                updateStats(result.stats);
                updateNextSample(result.next_sample);
            } else if (result.status === 'duplicate_error') {
                // STRICT DUPLICATE HANDLING: Alert Only
                showFeedback(`¡DUPLICADO! ${barcode} YA ESCANEADO`, 'duplicate'); // CSS animation handles visual alert
                alert(`ALERTA: La muestra ${barcode} YA FUE ESCANEADA.\nNO SE REGISTRARÁ NUEVAMENTE.`);
                updateNextSample(result.next_sample);
            } else if (result.status === 'not_found') {
                showFeedback(`NO ENCONTRADO: ${barcode}`, 'error');
                updateNextSample(result.next_sample);
            }

        } catch (error) {
            console.error(error);
        }
    }

    function updateNextSample(nextSample) {
        const idEl = document.getElementById('nextSampleId');
        const typeEl = document.getElementById('nextSampleType');

        if (nextSample) {
            idEl.textContent = nextSample.id;
            typeEl.textContent = nextSample.qaqc;

            // Visual cue for type
            if (nextSample.qaqc !== 'Muestra Normal') {
                typeEl.style.color = 'var(--accent-color)';
                typeEl.style.fontWeight = 'bold';
            } else {
                typeEl.style.color = 'var(--text-secondary)';
                typeEl.style.fontWeight = 'normal';
            }
        } else {
            idEl.textContent = "---";
            typeEl.textContent = "Completado";
            showFeedback("¡Todo Escaneado!", "success");
        }
    }

    function populateSelect(selectEl, columns, keywords) {
        selectEl.innerHTML = '';
        if (selectEl.id === 'qaqcColSelect') {
            selectEl.innerHTML = '<option value="">-- Ninguna --</option>';
        }

        columns.forEach(col => {
            const option = document.createElement('option');
            option.value = col;
            option.textContent = col;

            // Auto-select logic
            const lowerCol = col.toLowerCase();
            if (keywords.some(k => lowerCol.includes(k))) {
                if (!selectEl.value) option.selected = true; // Select first match only if not set
            }
            selectEl.appendChild(option);
        });
    }

    function addToList(data, type, qaqcType) {
        // If strict duplicate error, we don't add to list? 
        // User said "manda un mensaje de alerta... pero no lo registres".
        // Code above doesn't call addToList for duplicate_error.

        const li = document.createElement('li');
        li.className = `scan-item ${type}`;

        const mainText = data['N° Muestra'] || data['barcode'] || '???';
        const shipment = data['N° Envío'] || '-';
        const date = data['Scan Date'] || '';
        const time = data['Scan Time'] || new Date().toLocaleTimeString();

        let badgeHtml = '';
        if (qaqcType) {
            const badgeClass = qaqcType === 'Muestra Normal' ? 'normal' : 'control';
            badgeHtml = `<span class="qaqc-badge ${badgeClass}">${qaqcType}</span>`;
        }

        // Detailed layout for list item
        li.innerHTML = `
            <div style="display: flex; flex-direction: column;">
                <div style="display: flex; gap: 10px; align-items: center;">
                     <strong>${mainText}</strong>
                     ${badgeHtml}
                </div>
                <span class="text-secondary" style="font-size: 0.8rem;">Ref: ${shipment}</span>
            </div>
            <div style="text-align: right;">
                 <div style="font-weight: bold;">${time}</div>
                 <div class="text-secondary" style="font-size: 0.8rem;">${date}</div>
            </div>
        `;

        scanList.prepend(li);
        if (scanList.children.length > 20) scanList.removeChild(scanList.lastChild);
    }

    function showFeedback(msg, type) {
        feedbackMsg.textContent = msg;
        feedbackMsg.className = 'feedback-msg';
        if (type === 'success') feedbackMsg.classList.add('scan-success');
        if (type === 'error') feedbackMsg.classList.add('scan-error');
        if (type === 'duplicate') {
            feedbackMsg.classList.add('scan-duplicate');
            // Add shake animation
            feedbackMsg.style.animation = 'none';
            feedbackMsg.offsetHeight; /* trigger reflow */
            feedbackMsg.style.animation = 'shake 0.5s';
        }
    }

    function updateStats(stats) {
        if (!stats) return;
        scanCountEl.textContent = stats.scanned;
        missingCountEl.textContent = stats.missing;
    }

    // Export
    exportBtn.addEventListener('click', () => { window.location.href = '/export'; });

    // Focus Keep
    document.addEventListener('click', (e) => {
        if (!scanSection.classList.contains('hidden')
            && e.target.tagName !== 'INPUT'
            && e.target.tagName !== 'BUTTON'
            && e.target.tagName !== 'SELECT'
            && !document.getElementById('dataModal').contains(e.target)) { // Don't steal focus if in modal
            barcodeInput.focus();
        }
    });

    // --- New Features ---

    // 1. View Data
    const viewDataBtn = document.getElementById('viewDataBtn');
    const dataModal = document.getElementById('dataModal');
    const closeModalBtn = document.getElementById('closeModalBtn');
    const tableHeader = document.getElementById('tableHeader');
    const tableBody = document.getElementById('tableBody');

    viewDataBtn.addEventListener('click', async () => {
        showFeedback('Cargando datos...', 'neutral');
        try {
            const response = await fetch('/get_data');
            const result = await response.json();

            renderTable(result.data);
            dataModal.classList.remove('hidden');
            showFeedback('', 'neutral');
        } catch (error) {
            console.error(error);
            alert('Error al cargar datos');
        }
    });

    closeModalBtn.addEventListener('click', () => {
        dataModal.classList.add('hidden');
        barcodeInput.focus();
    });

    // Close modal on click outside
    dataModal.addEventListener('click', (e) => {
        if (e.target === dataModal) {
            dataModal.classList.add('hidden');
            barcodeInput.focus();
        }
    });

    function renderTable(data) {
        if (!data || data.length === 0) {
            tableBody.innerHTML = '<tr><td colspan="5">No hay datos</td></tr>';
            return;
        }

        // Specific columns user requested
        const targetCols = [
            { key: 'N° Envío', label: 'Envío' },
            { key: 'N° Muestra', label: 'Muestra' },
            { key: 'QAQC_Type', label: 'Tipo' },
            { key: 'Scan Date', label: 'Fecha' },
            { key: 'Scan Time', label: 'Hora' },
            { key: 'Scanned', label: 'Estado' } // Keep status
        ];

        tableHeader.innerHTML = targetCols.map(c => `<th>${c.label}</th>`).join('');

        // Rows
        tableBody.innerHTML = data.map(row => {
            const isScanned = row['Scanned'] === true || row['Scanned'] === 'True';
            const rowClass = isScanned ? 'scanned-row' : '';

            const cells = targetCols.map(col => {
                let val = row[col.key];
                if (val === null || val === undefined) val = '';

                if (col.key === 'Scanned') {
                    val = isScanned ? '✅' : 'Pendiente';
                }

                return `<td>${val}</td>`;
            }).join('');

            return `<tr class="${rowClass}">${cells}</tr>`;
        }).join('');
    }

    // 2. New Scan / Reset
    const newScanBtn = document.getElementById('newScanBtn');

    newScanBtn.addEventListener('click', async () => {
        if (!confirm('¿Estás seguro? Se BORRARÁN todos los datos cargados y el progreso actual.')) {
            return;
        }

        try {
            await fetch('/reset', { method: 'POST' });
            location.reload(); // Reload page to reset UI state completely
        } catch (error) {
            console.error(error);
            alert('Error al reiniciar');
        }
    });

});
