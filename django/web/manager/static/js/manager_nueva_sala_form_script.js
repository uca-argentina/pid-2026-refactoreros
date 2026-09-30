const inputFilas = document.getElementById("rows");
const inputColumnas = document.getElementById("columns");
const tabla  = document.getElementById("room_layout_table");
let toolMode = "seat"; 

let estado = {};
let isMouseClicking = false;

function limitSize(valor) {
    const n = parseInt(valor, 10);
    return isNaN(n) ? 1 : Math.min(Math.max(n, 1), 100);
}

function dibujarTabla() {
    const filas    = limitSize(inputFilas.value);
    const columnas = limitSize(inputColumnas.value);

    tabla.innerHTML = "";
    for (let f = 0; f < filas; f++) {
    const tr = document.createElement("tr");
    for (let c = 0; c < columnas; c++) {
        const key = `${f}-${c}`;
        const td    = document.createElement("td");
        const cb    = document.createElement("input");
        const label = document.createElement("label");

        label.className = "celda-checkbox";

        cb.type = "checkbox";
        cb.dataset.row = f;
        cb.dataset.column = c;
        cb.className = "seat_checkbox"
        cb.checked = !!estado[key];
        cb.addEventListener("change", () => { estado[key] = cb.checked; updateVisual(cb, label); });
        
        label.addEventListener("mousedown",  () => {isMouseClicking = true;});
        label.addEventListener("mouseenter", () => {paintSeatCb(cb,label,key)});
        label.addEventListener("mouseup",    () => {isMouseClicking = false;});


        label.appendChild(cb);
        td.appendChild(label);
        tr.appendChild(td);
    }
    tabla.appendChild(tr);
    }
}

function updateVisual(cb, label) {
    label.classList.toggle("checked", cb.checked);
}

function paintSeatCb(cb,label,key) {
    if (isMouseClicking) {
    if(toolMode == "seat"){
        cb.checked = true;
        estado[key] = cb.checked;
        updateVisual(cb, label);
    }else if (toolMode == "eraser"){
        cb.checked = false;
        estado[key] = cb.checked;
        updateVisual(cb, label);
    }

    }
}

function changeToolMode(mode) {
    toolMode = mode;
}

const seatModeButton  = document.getElementById("tool-seat-button");
const eraseModeButton = document.getElementById("tool-eraser-button");
seatModeButton.addEventListener("click",() => {changeToolMode("seat")});
eraseModeButton.addEventListener("click",() => {changeToolMode("eraser")});

const form = document.querySelector(".manager-form");
const layoutInput = document.getElementById("id_layout_sala");

form.addEventListener("submit",() => {
    const seats = [];
    document.querySelectorAll("#room_layout_table .seat_checkbox:checked").forEach( (cb) => {
    seats.push({"row":parseInt(cb.dataset.row,10),"column":parseInt(cb.dataset.column,10)});
    });
    layoutInput.value = JSON.stringify(seats);
    console.log(layoutInput.value);
});

inputFilas.addEventListener("input",() => {estado = {};dibujarTabla();});
inputColumnas.addEventListener("input",() => {estado = {};dibujarTabla();});
dibujarTabla();