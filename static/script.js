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
        const config = {
            header_row: parseInt(headerRowInput.value),
            data_start_row: parseInt(dataRowInput.value),
            sample_col: sampleColSelect.value,
            qaqc_col: qaqcColSelect.value || null
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

                // Init Stats
                totalCountEl.textContent = result.total;
                missingCountEl.textContent = result.total;

                showFeedback('Sistema configurado. ¡A escanear!', 'success');
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
            const user = document.getElementById('userInput').value;
            if (!barcode) return;
            barcodeInput.value = '';

            await processScan(barcode, user);
        }
    });

    async function processScan(barcode, user) {
        try {
            const response = await fetch('/scan', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ barcode, user })
            });

            const result = await response.json();

            if (result.status === 'success') {
                showFeedback(`${barcode} OK`, 'success');
                addToList(result.data, 'success', result.qaqc_type);
                updateStats(result.stats);
            } else if (result.status === 'duplicate') {
                showFeedback(`DUPLICADO: ${barcode}`, 'duplicate');
                addToList({ 'N° Muestra': barcode }, 'duplicate', result.qaqc_type);
            } else if (result.status === 'not_found') {
                showFeedback(`NO ENCONTRADO: ${barcode}`, 'error');
            }

        } catch (error) {
            console.error(error);
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
        const li = document.createElement('li');
        li.className = `scan-item ${type}`;

        const mainText = data['N° Muestra'] || data['barcode'] || '???';

        let badgeHtml = '';
        if (qaqcType) {
            const badgeClass = qaqcType === 'Muestra Normal' ? 'normal' : 'control';
            badgeHtml = `<span class="qaqc-badge ${badgeClass}">${qaqcType}</span>`;
        }

        li.innerHTML = `
            <div>
                <strong>${mainText}</strong>
                ${badgeHtml}
            </div>
            <span>${new Date().toLocaleTimeString()}</span>
        `;

        scanList.prepend(li);
        if (scanList.children.length > 20) scanList.removeChild(scanList.lastChild);
    }

    function showFeedback(msg, type) {
        feedbackMsg.textContent = msg;
        feedbackMsg.className = 'feedback-msg';
        if (type === 'success') feedbackMsg.classList.add('scan-success');
        if (type === 'error') feedbackMsg.classList.add('scan-error');
        if (type === 'duplicate') feedbackMsg.classList.add('scan-duplicate');
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
            && e.target.tagName !== 'SELECT') {
            barcodeInput.focus();
        }
    });

});
