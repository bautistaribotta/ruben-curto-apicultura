// Perfil de empleado: filtro de gastos por categoria y de viajes por tipo.
// Los datos todavia estan cargados a mano en la plantilla, asi que el filtrado
// es del lado del cliente sobre las filas ya renderizadas.

// ---------- GASTOS (filtro por categoria) ----------

// Copia del detalle que hoy vive en la plantilla. Cuando los montos salgan de la
// base, esto se reemplaza por lo que mande la vista.
const DETALLE_GASTOS = {
    combustible: { nombre: "Combustible", total: "$1.402.100", parte: "48,1%" },
    comida: { nombre: "Comida", total: "$402.300", parte: "13,8%" },
    peaje: { nombre: "Peaje", total: "$380.500", parte: "13,1%" },
    hotel: { nombre: "Hotel", total: "$232.000", parte: "8,0%" },
    playa: { nombre: "Playa", total: "$212.000", parte: "7,3%" },
    viaticos: { nombre: "Viáticos personales", total: "$179.000", parte: "6,1%" },
    extras: { nombre: "Extras", total: "$105.500", parte: "3,6%" }
};

const TOTAL_GASTOS = "$2.913.400";

function filtrarGastos(categoria) {
    const segmentos = document.querySelectorAll(".cinta-gastos__seg");
    const filas = document.querySelectorAll(".fila-gasto");
    const etiqueta = document.getElementById("etiqueta-total-gastos");
    const monto = document.getElementById("monto-total-gastos");
    const nota = document.getElementById("nota-gastos");

    const todas = categoria === "todas";

    // Apago lo que no corresponde a la categoria elegida, en la cinta y en la tabla
    segmentos.forEach((segmento) => {
        segmento.toggleAttribute("data-atenuado", !todas && segmento.dataset.categoria !== categoria);
    });

    filas.forEach((fila) => {
        fila.toggleAttribute("data-atenuado", !todas && fila.dataset.categoria !== categoria);
    });

    if (todas) {
        etiqueta.textContent = "Total rendido en 47 viajes";
        monto.textContent = TOTAL_GASTOS;
        nota.textContent = "Combustible se lleva casi la mitad de lo rendido";
        return;
    }

    const detalle = DETALLE_GASTOS[categoria];
    etiqueta.textContent = `Rendido en ${detalle.nombre}`;
    monto.textContent = detalle.total;
    nota.textContent = `${detalle.parte} del total gastado`;
}

document.getElementById("chips-gasto")?.addEventListener("click", (evento) => {
    const chip = evento.target.closest(".chip-gasto");
    if (!chip) return;

    document.querySelectorAll(".chip-gasto").forEach((otro) => otro.classList.remove("activa"));
    chip.classList.add("activa");

    filtrarGastos(chip.dataset.categoria);
});

// ---------- MODAL DE PAGO ----------

function abrirModalPagoEmpleado() {
    const contenedor = document.getElementById("contenedor-modal-pago");
    if (!contenedor) return;

    contenedor.classList.add("abierto");
    document.body.classList.add("con-modal-abierto");

    // El monto es lo unico que hay que decidir, asi que arranca con el foco puesto
    document.getElementById("monto-pago").focus();
}

function cerrarModalPagoEmpleado() {
    const contenedor = document.getElementById("contenedor-modal-pago");
    if (!contenedor) return;

    contenedor.classList.remove("abierto");
    document.body.classList.remove("con-modal-abierto");

    document.getElementById("form-pago-empleado").reset();
    actualizarContadorObservacion();

    // El proximo modal arranca limpio, sin el error del intento anterior
    montoTocado = false;
    document.querySelector(".campo-monto")?.classList.remove("con-error");
}

function actualizarContadorObservacion() {
    const observacion = document.getElementById("observaciones-pago");
    const contador = document.getElementById("contador-observacion");
    if (observacion && contador) {
        contador.textContent = observacion.value.length;
    }
}

// Marca el monto en rojo, pero recien despues de que el campo se haya tocado:
// un modal que se abre ya con el error puesto no ayuda a nadie.
let montoTocado = false;

function revisarMontoPago() {
    const monto = document.getElementById("monto-pago");
    const campo = document.querySelector(".campo-monto");
    if (!monto || !campo) return;

    campo.classList.toggle("con-error", montoTocado && !monto.checkValidity());
}

document.getElementById("boton-anadir-pago")?.addEventListener("click", abrirModalPagoEmpleado);
document.getElementById("observaciones-pago")?.addEventListener("input", actualizarContadorObservacion);

document.getElementById("monto-pago")?.addEventListener("input", () => {
    montoTocado = true;
    revisarMontoPago();
});

document.getElementById("monto-pago")?.addEventListener("blur", () => {
    montoTocado = true;
    revisarMontoPago();
});

// Escape cierra el modal, como el resto de los paneles de la app
document.addEventListener("keydown", (evento) => {
    if (evento.key === "Escape" && document.getElementById("contenedor-modal-pago")?.classList.contains("abierto")) {
        cerrarModalPagoEmpleado();
    }
});

// ---------- PANELES DE EDICION Y ELIMINACION ----------
// Las dos funciones viven en empleados.js, que esta pagina carga antes que a
// este archivo: el perfil abre los mismos paneles que el listado.

document.getElementById("boton-editar-empleado")?.addEventListener("click", (evento) => {
    prepararPanelEditarEmpleado(evento.currentTarget.dataset.id);
});

document.getElementById("boton-eliminar-empleado")?.addEventListener("click", (evento) => {
    const boton = evento.currentTarget;
    prepararPanelEliminarEmpleado(boton.dataset.id, boton.dataset.nombre);
});

// ---------- VIAJES (filtro por tipo) ----------

function filtrarViajes(tipo) {
    const filas = document.querySelectorAll(".fila-viaje-empleado");
    const pie = document.getElementById("pie-tabla-viajes");
    let visibles = 0;

    filas.forEach((fila) => {
        const coincide = tipo === "todos" || fila.dataset.tipo === tipo;
        fila.hidden = !coincide;
        if (coincide) visibles++;
    });

    // Aviso de tabla vacia: solo si hay viajes cargados y ninguno es de ese tipo
    const filaVacia = document.getElementById("fila-sin-viajes");
    if (filaVacia) {
        filaVacia.hidden = visibles > 0;
    }

    if (pie) {
        const total = document.querySelector(`.tab-viaje[data-tipo="${tipo}"] .tab-viaje__cuenta`);
        pie.textContent = visibles > 0
            ? `Mostrando los últimos ${visibles} viajes de ${total.textContent}`
            : "Sin viajes para mostrar";
    }
}

document.getElementById("tabs-viajes")?.addEventListener("click", (evento) => {
    const tab = evento.target.closest(".tab-viaje");
    if (!tab) return;

    document.querySelectorAll(".tab-viaje").forEach((otro) => otro.classList.remove("activa"));
    tab.classList.add("activa");

    filtrarViajes(tab.dataset.tipo);
});
