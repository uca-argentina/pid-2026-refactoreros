const inputFilas = document.getElementById("rows");
const inputColumnas = document.getElementById("columns");
const tabla  = document.getElementById("room_layout_table");
const layoutInput = document.getElementById("id_layout_sala");
const undoButton = document.getElementById("undo-layout");
const redoButton = document.getElementById("redo-layout");
const selectAllButton = document.getElementById("select-all-seats");
const clearAllButton = document.getElementById("clear-all-seats");
const exportBackupButton = document.getElementById("export-layout-backup");
const importBackupButton = document.getElementById("import-layout-backup");
const importBackupInput = document.getElementById("layout-backup-file");
const roomNameInput = document.getElementById("id_nombre");
const dimensionStepperButtons = document.querySelectorAll(".dimension-step-button");

let isMouseClicking = false;
let toolMode = "seat"; 
let estado = {};
let history = [];
let historyIndex = -1;
let isRestoringHistory = false;
let hasPendingHistoryEntry = false;
let dimensionRepeatTimeout;
let dimensionRepeatInterval;
let hasPendingDimensionHistoryEntry = false;
let currentDimensions = {rows: 0, columns: 0};
let suppressColumnLabelRefresh = false;
let hasPendingColumnLabelRefresh = false;
let columnLabelRefreshFrame = null;


function limitSize(valor) {
    const n = parseInt(valor, 10);
    return isNaN(n) ? 1 : Math.min(Math.max(n, 1), 100);
}

function normalizeDimensionInput(input) {
    const normalizedValue = limitSize(input.value);
    input.value = normalizedValue;
    return normalizedValue;
}

function getDimensionInput(target) {
    return target === "rows" ? inputFilas : inputColumnas;
}

function getDefaultSeatTypeName() {
    return seatModeButtons[0]?.dataset.nombre || selectedSeatType?.dataset?.nombre || "Estándar";
}

function resizeLayoutState(nextRows, nextColumns, fillNewSeats = true) {
    const previousRows = currentDimensions.rows;
    const previousColumns = currentDimensions.columns;
    const defaultSeatType = getDefaultSeatTypeName();
    const nextEstado = {};

    for (const [key, seat] of Object.entries(estado)) {
        const [row, column] = key.split("-").map((value) => parseInt(value, 10));
        if (row < nextRows && column < nextColumns && seat?.checked) {
            nextEstado[key] = seat;
        }
    }

    if (fillNewSeats && defaultSeatType) {
        for (let row = 0; row < nextRows; row++) {
            for (let column = 0; column < nextColumns; column++) {
                const isNewRow = row >= previousRows;
                const isNewColumn = column >= previousColumns;
                const key = `${row}-${column}`;
                if ((isNewRow || isNewColumn) && !nextEstado[key]) {
                    nextEstado[key] = {checked: true, type: defaultSeatType};
                }
            }
        }
    }

    estado = nextEstado;
    currentDimensions = {rows: nextRows, columns: nextColumns};
}

function fillMissingSeats(rows, columns) {
    const defaultSeatType = getDefaultSeatTypeName();
    if (!defaultSeatType) {
        return;
    }
    for (let row = 0; row < rows; row++) {
        for (let column = 0; column < columns; column++) {
            const key = `${row}-${column}`;
            if (!estado[key]) {
                estado[key] = {checked: true, type: defaultSeatType};
            }
        }
    }
}

function applyDimensionChange(shouldRecordHistory = true) {
    const rows = normalizeDimensionInput(inputFilas);
    const columns = normalizeDimensionInput(inputColumnas);
    resizeLayoutState(rows, columns);
    dibujarTabla();
    if (shouldRecordHistory) {
        recordHistory();
    }
}

function stepDimension(target, direction) {
    const input = getDimensionInput(target);
    const min = parseInt(input.min, 10) || 1;
    const max = parseInt(input.max, 10) || 100;
    const currentValue = normalizeDimensionInput(input);
    const nextValue = Math.min(Math.max(currentValue + direction, min), max);

    if (nextValue === currentValue) {
        return false;
    }

    input.value = nextValue;
    applyDimensionChange(false);
    return true;
}

function stopDimensionRepeat() {
    clearTimeout(dimensionRepeatTimeout);
    clearInterval(dimensionRepeatInterval);
    dimensionRepeatTimeout = null;
    dimensionRepeatInterval = null;

    if (hasPendingDimensionHistoryEntry) {
        recordHistory();
        hasPendingDimensionHistoryEntry = false;
    }
}

function cloneEstado() {
    return JSON.parse(JSON.stringify(estado));
}

function getSnapshot() {
    return {
        rows: limitSize(inputFilas.value),
        columns: limitSize(inputColumnas.value),
        estado: cloneEstado(),
    };
}

function updateHistoryButtons() {
    undoButton.disabled = historyIndex <= 0;
    redoButton.disabled = historyIndex >= history.length - 1;
}

function recordHistory() {
    if (isRestoringHistory) {
        return;
    }
    const snapshot = getSnapshot();
    const serializedSnapshot = JSON.stringify(snapshot);
    if (history[historyIndex] && JSON.stringify(history[historyIndex]) === serializedSnapshot) {
        updateHistoryButtons();
        return;
    }
    history = history.slice(0, historyIndex + 1);
    history.push(snapshot);
    historyIndex = history.length - 1;
    updateHistoryButtons();
}

function restoreHistory(nextIndex) {
    if (nextIndex < 0 || nextIndex >= history.length) {
        return;
    }
    isRestoringHistory = true;
    const snapshot = history[nextIndex];
    inputFilas.value = snapshot.rows;
    inputColumnas.value = snapshot.columns;
    estado = JSON.parse(JSON.stringify(snapshot.estado));
    currentDimensions = {rows: snapshot.rows, columns: snapshot.columns};
    historyIndex = nextIndex;
    dibujarTabla();
    isRestoringHistory = false;
    updateHistoryButtons();
}

function getColumnLabel(index) {
    let label = "";
    let value = index + 1;
    while (value > 0) {
        const remainder = (value - 1) % 26;
        label = String.fromCharCode(65 + remainder) + label;
        value = Math.floor((value - 1) / 26);
    }
    return label;
}

function hasSeatAt(row, column) {
    return Boolean(estado[`${row}-${column}`]?.checked);
}

function getVisibleColumnLabels(columns) {
    const rows = normalizeDimensionInput(inputFilas);
    const labels = {};
    let nextLabelIndex = 0;
    for (let column = 0; column < columns; column++) {
        const hasSeats = Array.from({length: rows}).some((_item, row) => (
            hasSeatAt(row, column)
        ));
        if (hasSeats) {
            labels[column] = getColumnLabel(nextLabelIndex);
            nextLabelIndex += 1;
        } else {
            labels[column] = "";
        }
    }
    return labels;
}

function setColumnPreview(column, isActive) {
    tabla.querySelectorAll(`.seat_checkbox[data-column="${column}"]`).forEach((cb) => {
        cb.closest(".celda-checkbox")?.classList.toggle("is-column-preview", isActive);
    });
    tabla.querySelector(`.column-label-header[data-column="${column}"]`)?.classList.toggle("is-column-preview", isActive);
}

function refreshVisibleColumnLabels() {
    const rows = normalizeDimensionInput(inputFilas);
    const columns = normalizeDimensionInput(inputColumnas);
    const visibleColumnLabels = getVisibleColumnLabels(columns);

    for (let column = 0; column < columns; column++) {
        const columnLabel = visibleColumnLabels[column];
        const columnHeader = tabla.querySelector(`.column-label-header[data-column="${column}"]`);
        if (columnHeader) {
            columnHeader.textContent = columnLabel;
            columnHeader.classList.toggle("is-aisle", !columnLabel);
            columnHeader.title = columnLabel ? `Columna ${columnLabel}` : "Pasillo vertical";
        }

        const columnButton = tabla.querySelector(`.column-select-button[data-column="${column}"]`);
        if (columnButton) {
            columnButton.title = columnLabel ? `Aplicar herramienta a toda la columna ${columnLabel}` : "Aplicar herramienta a esta columna pasillo";
            columnButton.setAttribute("aria-label", columnButton.title);
        }

        for (let row = 0; row < rows; row++) {
            const cb = tabla.querySelector(`.seat_checkbox[data-row="${row}"][data-column="${column}"]`);
            const label = cb?.closest(".celda-checkbox");
            if (!label) {
                continue;
            }
            label.title = columnLabel ? `Fila ${row + 1}, columna ${columnLabel}` : `Fila ${row + 1}, pasillo vertical`;
            label.setAttribute("aria-label", label.title);
        }
    }
}

function requestColumnLabelRefresh() {
    if (suppressColumnLabelRefresh) {
        hasPendingColumnLabelRefresh = true;
        return;
    }
    if (columnLabelRefreshFrame) {
        return;
    }
    columnLabelRefreshFrame = window.requestAnimationFrame(() => {
        columnLabelRefreshFrame = null;
        refreshVisibleColumnLabels();
    });
}

function flushColumnLabelRefresh() {
    suppressColumnLabelRefresh = false;
    if (!hasPendingColumnLabelRefresh) {
        return;
    }
    hasPendingColumnLabelRefresh = false;
    if (columnLabelRefreshFrame) {
        window.cancelAnimationFrame(columnLabelRefreshFrame);
        columnLabelRefreshFrame = null;
    }
    refreshVisibleColumnLabels();
}

function dibujarTabla() {
    const filas    = normalizeDimensionInput(inputFilas);
    const columnas = normalizeDimensionInput(inputColumnas);
    const visibleColumnLabels = getVisibleColumnLabels(columnas);

    tabla.innerHTML = "";
    const headerRow = document.createElement("tr");
    headerRow.className = "column-header-row";

    const rowToolHeader = document.createElement("th");
    rowToolHeader.className = "row-control-header";
    rowToolHeader.scope = "col";
    rowToolHeader.setAttribute("aria-label", "Seleccionar fila");
    headerRow.appendChild(rowToolHeader);

    const rowLabelHeader = document.createElement("th");
    rowLabelHeader.className = "row-label-header";
    rowLabelHeader.scope = "col";
    rowLabelHeader.setAttribute("aria-label", "Fila");
    headerRow.appendChild(rowLabelHeader);

    for (let c = 0; c < columnas; c++) {
        const columnHeader = document.createElement("th");
        const columnLabel = visibleColumnLabels[c];
        columnHeader.className = "column-label-header";
        columnHeader.scope = "col";
        columnHeader.dataset.column = c;
        columnHeader.textContent = columnLabel;
        columnHeader.classList.toggle("is-aisle", !columnLabel);
        columnHeader.title = columnLabel ? `Columna ${columnLabel}` : "Pasillo vertical";
        headerRow.appendChild(columnHeader);
    }
    tabla.appendChild(headerRow);

    for (let f = 0; f < filas; f++) {
    const tr = document.createElement("tr");
    const rowControlCell = document.createElement("td");
    const rowButton = document.createElement("button");
    const rowLabelCell = document.createElement("th");

    rowControlCell.className = "row-control-cell";
    rowButton.type = "button";
    rowButton.className = "row-select-button";
    rowButton.dataset.row = f;
    rowButton.title = "Aplicar herramienta a toda la fila";
    rowButton.setAttribute("aria-label", `Aplicar herramienta a toda la fila ${f + 1}`);
    rowButton.innerHTML = '<i data-lucide="grip-horizontal" aria-hidden="true"></i>';
    rowButton.addEventListener("mouseenter", () => {tr.classList.add("is-row-preview");});
    rowButton.addEventListener("mouseleave", () => {tr.classList.remove("is-row-preview");});
    rowButton.addEventListener("focus", () => {tr.classList.add("is-row-preview");});
    rowButton.addEventListener("blur", () => {tr.classList.remove("is-row-preview");});
    rowButton.addEventListener("click", () => {applyToolToRow(f);});
    rowControlCell.appendChild(rowButton);
    tr.appendChild(rowControlCell);

    rowLabelCell.className = "row-label-cell";
    rowLabelCell.scope = "row";
    rowLabelCell.textContent = f + 1;
    tr.appendChild(rowLabelCell);

    for (let c = 0; c < columnas; c++) {
        const key = `${f}-${c}`;
        const columnLabel = visibleColumnLabels[c];
        const td    = document.createElement("td");
        const cb    = document.createElement("input");
        const label = document.createElement("label");

        label.className = "celda-checkbox";
        label.title = columnLabel ? `Fila ${f + 1}, columna ${columnLabel}` : `Fila ${f + 1}, pasillo vertical`;
        label.setAttribute("aria-label", label.title);

        cb.type = "checkbox";
        cb.dataset.row = f;
        cb.dataset.column = c;
        cb.dataset.type = estado[key]?.type || "none";
        cb.className = "seat_checkbox"
        cb.checked = hasSeatAt(f, c);
        
        label.addEventListener("pointerdown",  (event) => {
            event.preventDefault();
            isMouseClicking = true;
            paintSeatWithTool(cb,label,key);
        });
        label.addEventListener("mouseenter", () => {paintSeatWithTool(cb,label,key)});


        label.appendChild(cb);
        td.appendChild(label);
        updateVisual(cb, label);
        tr.appendChild(td);
    }
    tabla.appendChild(tr);
    }

    const columnControlRow = document.createElement("tr");
    columnControlRow.className = "column-control-row";

    const columnControlSpacer = document.createElement("td");
    columnControlSpacer.className = "column-control-spacer";
    columnControlSpacer.colSpan = 2;
    columnControlRow.appendChild(columnControlSpacer);

    for (let c = 0; c < columnas; c++) {
        const columnControlCell = document.createElement("td");
        const columnButton = document.createElement("button");
        const columnLabel = visibleColumnLabels[c];

        columnControlCell.className = "column-control-cell";
        columnButton.type = "button";
        columnButton.className = "column-select-button";
        columnButton.dataset.column = c;
        columnButton.title = columnLabel ? `Aplicar herramienta a toda la columna ${columnLabel}` : "Aplicar herramienta a esta columna pasillo";
        columnButton.setAttribute("aria-label", columnButton.title);
        columnButton.innerHTML = '<i data-lucide="grip-vertical" aria-hidden="true"></i>';
        columnButton.addEventListener("mouseenter", () => {setColumnPreview(c, true);});
        columnButton.addEventListener("mouseleave", () => {setColumnPreview(c, false);});
        columnButton.addEventListener("focus", () => {setColumnPreview(c, true);});
        columnButton.addEventListener("blur", () => {setColumnPreview(c, false);});
        columnButton.addEventListener("click", () => {applyToolToColumn(c);});
        columnControlCell.appendChild(columnButton);
        columnControlRow.appendChild(columnControlCell);
    }
    tabla.appendChild(columnControlRow);

    if (window.lucide) {
        lucide.createIcons();
    }
}

function updateVisual(cb, label) {
    label.classList.toggle("checked", cb.checked);
    deleteExistingIcon(label);

    if (!cb.checked) {
        label.style.removeProperty("--checked-color");
        return;
    }

    const seatTypeButton = getToolButtonByType(cb.dataset.type);
    label.style.setProperty("--checked-color", seatTypeButton?.dataset.color || "#4f46e5");
    if (seatTypeButton?.dataset.icon){
        updateIcon(label, seatTypeButton.dataset.icon);
    }
}

function updateIcon(label, iconUrl){
    const icon = document.createElement("img");
    icon.setAttribute("src",iconUrl);
    icon.setAttribute("style","max-width: 20px; -webkit-user-drag: none;");
    label.appendChild(icon);
}

function deleteExistingIcon(label){
    const existing_icon = label.querySelector("img");
    if (existing_icon){
        existing_icon.remove();
    }
}

function paintSeatWithTool(cb,label,key) {
    if (isMouseClicking) {
        applyToolToSeat(cb, label, key);
    }
}

function applyToolToSeat(cb,label,key) {
    if(toolMode == "seat"){
        const previousType = cb.dataset.type;
        const wasChecked = cb.checked;
        cb.checked = true;
        cb.dataset.type = selectedSeatType.dataset.nombre;
        estado[key] = {"checked":cb.checked,"type":selectedSeatType.dataset.nombre};
        updateVisual(cb, label);
        hasPendingHistoryEntry = hasPendingHistoryEntry || !wasChecked || previousType !== cb.dataset.type;
        if (!wasChecked || previousType !== cb.dataset.type) {
            requestColumnLabelRefresh();
        }
    }else if (toolMode == "eraser"){
        const wasChecked = cb.checked;
        cb.checked = false;
        cb.dataset.type = "none";
        delete estado[key];
        updateVisual(cb, label);
        hasPendingHistoryEntry = hasPendingHistoryEntry || wasChecked;
        requestColumnLabelRefresh();
    }
}

function applyToolToRow(row, shouldRecordHistory = true) {
    hasPendingHistoryEntry = false;
    suppressColumnLabelRefresh = true;
    const columns = normalizeDimensionInput(inputColumnas);
    for (let column = 0; column < columns; column++) {
        const key = `${row}-${column}`;
        const cb = tabla.querySelector(`.seat_checkbox[data-row="${row}"][data-column="${column}"]`);
        if (!cb) {
            continue;
        }
        const label = cb.closest(".celda-checkbox");
        applyToolToSeat(cb, label, key);
    }
    flushColumnLabelRefresh();
    if (shouldRecordHistory && hasPendingHistoryEntry) {
        recordHistory();
        hasPendingHistoryEntry = false;
    }
}

function applyToolToColumn(column, shouldRecordHistory = true) {
    hasPendingHistoryEntry = false;
    suppressColumnLabelRefresh = true;
    const rows = normalizeDimensionInput(inputFilas);
    for (let row = 0; row < rows; row++) {
        const key = `${row}-${column}`;
        const cb = tabla.querySelector(`.seat_checkbox[data-row="${row}"][data-column="${column}"]`);
        if (!cb) {
            continue;
        }
        const label = cb.closest(".celda-checkbox");
        applyToolToSeat(cb, label, key);
    }
    flushColumnLabelRefresh();
    if (shouldRecordHistory && hasPendingHistoryEntry) {
        recordHistory();
        hasPendingHistoryEntry = false;
    }
}

function getToolButtonByType(type) {
    return Array.from(seatModeButtons).find((toolButton) => toolButton.dataset.nombre === type);
}

function resolveSeatTypeName(seat) {
    const rawType = seat.type;
    const matchingButton = Array.from(seatModeButtons).find((button) => (
        button.dataset.nombre === rawType ||
        button.dataset.typeId === String(rawType) ||
        button.dataset.typeId === String(seat.type_id)
    ));
    return matchingButton?.dataset.nombre || null;
}


document.querySelectorAll(".tool-btn.seat[data-color]").forEach(toolButton => {
    toolButton.style.background = toolButton.dataset.color;
});

function changeToolMode(newMode) {
    toolMode = newMode;
    if(newMode == "eraser"){
        selectedSeatType = "";
    }
}

function changeSelectedSeatType(newSeatType){
    selectedSeatType = newSeatType;
    document.documentElement.style.setProperty('--seat-hover-color',newSeatType.dataset.color );
    Array.from(toolButtons).forEach((toolButton) => {
        const isActive = toolButton === newSeatType;
        toolButton.classList.toggle("is-active", isActive);
        toolButton.setAttribute("aria-pressed", isActive ? "true" : "false");
    });
}

const toolButtons = document.getElementsByClassName("tool-btn")
const seatModeButtons = document.getElementsByClassName("tool-btn seat")
const eraseModeButton = document.getElementById("tool-eraser-button");
for(let i =0;i<seatModeButtons.length;i++ ){
    seatModeButtons[i].addEventListener("click",() => {changeToolMode("seat");changeSelectedSeatType(seatModeButtons[i]);});
}
let selectedSeatType = seatModeButtons[0] || eraseModeButton;
if (!seatModeButtons.length) {
    changeToolMode("eraser");
}
changeSelectedSeatType(selectedSeatType);

eraseModeButton.addEventListener("click",() => {changeToolMode("eraser");changeSelectedSeatType(eraseModeButton);});

document.addEventListener("pointerup", () => {
    isMouseClicking = false;
    if (hasPendingHistoryEntry) {
        recordHistory();
        hasPendingHistoryEntry = false;
    }
});
document.addEventListener("pointercancel", () => {
    isMouseClicking = false;
    hasPendingHistoryEntry = false;
});

dimensionStepperButtons.forEach((button) => {
    const target = button.dataset.dimensionTarget;
    const direction = parseInt(button.dataset.dimensionStep, 10);

    button.addEventListener("pointerenter", () => {
        button.classList.add("is-hovered");
    });
    button.addEventListener("pointerleave", () => {
        button.classList.remove("is-hovered");
    });
    button.addEventListener("pointerdown", (event) => {
        event.preventDefault();
        stopDimensionRepeat();
        button.setPointerCapture?.(event.pointerId);

        hasPendingDimensionHistoryEntry = stepDimension(target, direction);
        dimensionRepeatTimeout = setTimeout(() => {
            dimensionRepeatInterval = setInterval(() => {
                hasPendingDimensionHistoryEntry = stepDimension(target, direction) || hasPendingDimensionHistoryEntry;
            }, 85);
        }, 320);
    });

    button.addEventListener("pointerup", stopDimensionRepeat);
    button.addEventListener("pointercancel", () => {
        button.classList.remove("is-hovered");
        stopDimensionRepeat();
    });
    button.addEventListener("lostpointercapture", () => {
        button.classList.remove("is-hovered");
        stopDimensionRepeat();
    });
    button.addEventListener("blur", () => {
        button.classList.remove("is-hovered");
    });
    button.addEventListener("click", (event) => {
        if (event.detail !== 0) {
            return;
        }
        if (stepDimension(target, direction)) {
            recordHistory();
        }
    });
});

document.addEventListener("visibilitychange", () => {
    if (document.hidden) {
        stopDimensionRepeat();
    }
});



const form = document.querySelector(".manager-form");

form.addEventListener("submit",(event) => {
    normalizeDimensionInput(inputFilas);
    normalizeDimensionInput(inputColumnas);

    layoutInput.value = JSON.stringify({
        rows: normalizeDimensionInput(inputFilas),
        columns: normalizeDimensionInput(inputColumnas),
        seats: getSeatsFromEstado(),
    });
});

[inputFilas, inputColumnas].forEach((input) => {
    input.addEventListener("input", () => {
        applyDimensionChange();
    });
    input.addEventListener("blur", () => {
        applyDimensionChange();
    });
});

function fillAllSeats() {
    if (!seatModeButtons.length) {
        return;
    }
    if (toolMode !== "seat") {
        changeToolMode("seat");
        changeSelectedSeatType(seatModeButtons[0]);
    }

    const rows = normalizeDimensionInput(inputFilas);
    hasPendingHistoryEntry = false;
    for (let row = 0; row < rows; row++) {
        applyToolToRow(row, false);
    }
    if (hasPendingHistoryEntry) {
        recordHistory();
        hasPendingHistoryEntry = false;
    }
}

function clearAllSeats() {
    estado = {};
    dibujarTabla();
    recordHistory();
}

function getSeatsFromEstado() {
    return Object.entries(estado)
        .filter(([_key, seat]) => seat?.checked)
        .map(([key, seat]) => {
            const [row, column] = key.split("-").map((value) => parseInt(value, 10));
            return {row, column, type: seat.type};
        })
        .sort((a, b) => a.row - b.row || a.column - b.column);
}

function normalizeFilePart(value) {
    return value
        .trim()
        .normalize("NFD")
        .replace(/[\u0300-\u036f]/g, "")
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, "-")
        .replace(/^-+|-+$/g, "")
        .slice(0, 80);
}

function getBackupTimestamp() {
    const now = new Date();
    const pad = (value) => String(value).padStart(2, "0");
    return [
        now.getFullYear(),
        pad(now.getMonth() + 1),
        pad(now.getDate()),
        "-",
        pad(now.getHours()),
        pad(now.getMinutes()),
        pad(now.getSeconds()),
    ].join("");
}

function getBackupFilename() {
    const roomName = normalizeFilePart(roomNameInput?.value || "");
    const roomPart = roomName ? `-${roomName}` : "";
    return `backup-sala${roomPart}-${getBackupTimestamp()}.json`;
}

function exportBackup() {
    const backup = {
        version: 1,
        rows: normalizeDimensionInput(inputFilas),
        columns: normalizeDimensionInput(inputColumnas),
        seats: getSeatsFromEstado(),
    };
    const blob = new Blob([JSON.stringify(backup, null, 2)], {type: "application/json"});
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = getBackupFilename();
    link.click();
    URL.revokeObjectURL(url);
}

function applyBackupData(backupData) {
    const seats = Array.isArray(backupData) ? backupData : backupData.seats;
    if (!Array.isArray(seats)) {
        window.alert("El backup no tiene un formato válido.");
        return;
    }

    const nextEstado = {};
    let maxRow = 0;
    let maxColumn = 0;
    for (const seat of seats) {
        const row = parseInt(seat.row, 10);
        const column = parseInt(seat.column, 10);
        const type = resolveSeatTypeName(seat);
        if (Number.isNaN(row) || Number.isNaN(column) || row < 0 || column < 0 || !type) {
            continue;
        }
        nextEstado[`${row}-${column}`] = {checked: true, type};
        maxRow = Math.max(maxRow, row + 1);
        maxColumn = Math.max(maxColumn, column + 1);
    }

    const rows = limitSize(backupData.rows || maxRow || inputFilas.value);
    const columns = limitSize(backupData.columns || maxColumn || inputColumnas.value);
    inputFilas.value = rows;
    inputColumnas.value = columns;
    estado = nextEstado;
    currentDimensions = {rows, columns};
    dibujarTabla();
    recordHistory();
}

function importBackup(file) {
    const reader = new FileReader();
    reader.addEventListener("load", () => {
        try {
            applyBackupData(JSON.parse(reader.result));
        } catch (_error) {
            window.alert("No se pudo leer el backup.");
        }
    });
    reader.readAsText(file);
}

function loadLayoutFromHiddenInput() {
    if (!layoutInput.value) {
        return false;
    }
    try {
        applyBackupData(JSON.parse(layoutInput.value));
        return true;
    } catch (_error) {
        estado = {};
        return false;
    }
}

function setupDoubleConfirm(button, defaultLabel, confirmLabel, action) {
    let confirmationTimer;
    button.addEventListener("click", () => {
        if (button.dataset.confirming === "true") {
            clearTimeout(confirmationTimer);
            button.dataset.confirming = "false";
            button.querySelector("span").textContent = defaultLabel;
            action();
            return;
        }

        button.dataset.confirming = "true";
        button.querySelector("span").textContent = confirmLabel;
        confirmationTimer = setTimeout(() => {
            button.dataset.confirming = "false";
            button.querySelector("span").textContent = defaultLabel;
        }, 3000);
    });
}

setupDoubleConfirm(selectAllButton, "Seleccionar todo", "Confirmar selección", fillAllSeats);
setupDoubleConfirm(clearAllButton, "Borrar todo", "Confirmar borrado", clearAllSeats);

undoButton.addEventListener("click", () => {restoreHistory(historyIndex - 1);});
redoButton.addEventListener("click", () => {restoreHistory(historyIndex + 1);});
exportBackupButton.addEventListener("click", exportBackup);
importBackupButton.addEventListener("click", () => {importBackupInput.click();});
importBackupInput.addEventListener("change", () => {
    const [file] = importBackupInput.files;
    if (file) {
        importBackup(file);
    }
    importBackupInput.value = "";
});
if (!loadLayoutFromHiddenInput()) {
    const rows = normalizeDimensionInput(inputFilas);
    const columns = normalizeDimensionInput(inputColumnas);
    fillMissingSeats(rows, columns);
    currentDimensions = {rows, columns};
}
dibujarTabla();
recordHistory();
