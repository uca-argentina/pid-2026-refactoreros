const inputFilas = document.getElementById("rows");
const inputColumnas = document.getElementById("columns");
const tabla  = document.getElementById("room_layout_table");

let isMouseClicking = false;
let toolMode = "seat"; 
let estado = {};


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
        cb.dataset.type = "none";
        cb.className = "seat_checkbox"
        cb.checked = !!estado[key];
        cb.addEventListener("change", () => { paintSeatWithClick(cb,label,key);});
        
        label.addEventListener("mousedown",  () => {isMouseClicking = true;});
        label.addEventListener("mouseenter", () => {paintSeatWithTool(cb,label,key)});
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
    label.style.setProperty("--checked-color",selectedSeatType.dataset.color);
    deleteExistingIcon(label);
    if (selectedSeatType.dataset.icon && cb.checked){
        updateIcon(label);
    }
}

function updateIcon(label){
    const icon = document.createElement("img");
    icon.setAttribute("src",selectedSeatType.dataset.icon);
    icon.setAttribute("style","max-width: 20px; -webkit-user-drag: none;");
    label.appendChild(icon);
}

function deleteExistingIcon(label){
    const existing_icon = label.querySelector("img");
    if (existing_icon){
        existing_icon.remove();
    }
}

function paintSeatWithClick(cb,label,key) {
    if(toolMode == "seat"){
        cb.checked = true;
        cb.dataset.type = selectedSeatType.dataset.nombre;
        estado[key] = {"checked":cb.checked,"type":selectedSeatType.dataset.nombre};
        updateVisual(cb, label);
    }else if (toolMode == "eraser"){
        cb.checked = false;
        estado[key] = cb.checked;
        updateVisual(cb, label);
    }
}

function paintSeatWithTool(cb,label,key) {
    if (isMouseClicking) {
    if(toolMode == "seat"){
        cb.checked = true;
        cb.dataset.type = selectedSeatType.dataset.nombre;
        estado[key] = {"checked":cb.checked,"type":selectedSeatType.dataset.nombre};
        updateVisual(cb, label);
    }else if (toolMode == "eraser"){
        cb.checked = false;
        estado[key] = cb.checked;
        updateVisual(cb, label);
    }

    }
}


document.querySelectorAll("[data-color]").forEach(toolButton => {
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
}

const seatModeButtons = document.getElementsByClassName("tool-btn")
const eraseModeButton = document.getElementById("tool-eraser-button");
for(let i =0;i<(seatModeButtons.length-1);i++ ){
    seatModeButtons[i].addEventListener("click",() => {changeToolMode("seat");changeSelectedSeatType(seatModeButtons[i]);});
}
let selectedSeatType = seatModeButtons[0];

eraseModeButton.addEventListener("click",() => {changeToolMode("eraser");changeSelectedSeatType(eraseModeButton);});



const form = document.querySelector(".manager-form");
const layoutInput = document.getElementById("id_layout_sala");

form.addEventListener("submit",() => {
    const seats = [];
    document.querySelectorAll("#room_layout_table .seat_checkbox:checked").forEach( (cb) => {
    seats.push({"row":parseInt(cb.dataset.row,10),"column":parseInt(cb.dataset.column,10),"type":cb.dataset.type});
    });
    layoutInput.value = JSON.stringify(seats);
});

inputFilas.addEventListener("input",() => {estado = {};dibujarTabla();});
inputColumnas.addEventListener("input",() => {estado = {};dibujarTabla();});
dibujarTabla();