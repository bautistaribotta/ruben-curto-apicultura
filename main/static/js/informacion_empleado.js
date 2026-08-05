// Perfil de empleado.
//
// El bloque de gastos y viajes (#secciones-empleado) lo devuelve el servidor y se
// reemplaza entero al cambiar el rango de fechas, la pestaña de tipo de viaje o la
// pagina. Por eso todo lo que vive adentro se engancha por delegacion en document:
// asi los listeners sobreviven al reemplazo.

const contenedorSecciones = document.getElementById("secciones-empleado");
const filtroFechasEmpleado = document.getElementById("filtro-fechas");

// ---------- CARGA AJAX DEL BLOQUE DE GASTOS Y VIAJES ----------

function armarUrlSecciones(base = null) {
    const url = base ? new URL(base, window.location.origin) : new URL(window.location.href);

    // A diferencia de las otras vistas, aca los parametros de fecha se mandan
    // siempre, aunque esten vacios: la vista arranca en el año en curso cuando no
    // vienen, asi que un vacio explicito es lo que pide el historial completo.
    const desde = filtroFechasEmpleado ? filtroFechasEmpleado.dataset.desde : "";
    const hasta = filtroFechasEmpleado ? filtroFechasEmpleado.dataset.hasta : "";
    url.searchParams.set("desde", desde || "");
    url.searchParams.set("hasta", hasta || "");

    return url;
}

function cargarSecciones(url) {
    if (!contenedorSecciones) return;

    contenedorSecciones.setAttribute("aria-busy", "true");

    fetch(url, { headers: { "X-Requested-With": "XMLHttpRequest" } })
        .then((respuesta) => respuesta.text())
        .then((html) => {
            contenedorSecciones.innerHTML = html;
            contenedorSecciones.removeAttribute("aria-busy");
            repartirCintaGastos();
            guardarTitularGastos();
            window.history.pushState({}, "", url);
        })
        .catch((error) => {
            contenedorSecciones.removeAttribute("aria-busy");
            console.error("Error al cargar los gastos y viajes:", error);
        });
}

// El filtro de fecha avisa por evento; recargo el bloque con el rango aplicado.
document.addEventListener("filtrofechas:cambio", () => {
    const url = armarUrlSecciones();
    // Al cambiar el periodo la paginacion de viajes deja de tener sentido
    url.searchParams.delete("page_viajes");
    cargarSecciones(url);
});

// ---------- GASTOS ----------

// El ancho de cada segmento es su participacion sobre el total, un dato que solo
// conoce el servidor. Viaja en data-parte y se traduce a flex-grow aca; el color y
// el resto del aspecto siguen viviendo en la hoja de estilos.
function repartirCintaGastos() {
    document.querySelectorAll(".cinta-gastos__seg").forEach((segmento) => {
        segmento.style.flexGrow = segmento.dataset.parte;
    });
}

// Los textos del titular los escribe el servidor con el total del periodo. Los
// guardo apenas se renderiza para poder volver a ellos al elegir "Todas".
let titularGastos = {};

function guardarTitularGastos() {
    const etiqueta = document.getElementById("etiqueta-total-gastos");
    const monto = document.getElementById("monto-total-gastos");
    const nota = document.getElementById("nota-gastos");
    titularGastos = {
        etiqueta: etiqueta ? etiqueta.textContent.trim() : "",
        monto: monto ? monto.textContent.trim() : "",
        nota: nota ? nota.textContent.trim() : ""
    };
}

function filtrarGastos(chip) {
    const categoria = chip.dataset.categoria;
    const todas = categoria === "todas";

    const etiqueta = document.getElementById("etiqueta-total-gastos");
    const monto = document.getElementById("monto-total-gastos");
    const nota = document.getElementById("nota-gastos");

    // Apago lo que no corresponde a la categoria elegida, en la cinta y en la tabla
    document.querySelectorAll(".cinta-gastos__seg").forEach((segmento) => {
        segmento.toggleAttribute("data-atenuado", !todas && segmento.dataset.categoria !== categoria);
    });

    document.querySelectorAll(".fila-gasto").forEach((fila) => {
        fila.toggleAttribute("data-atenuado", !todas && fila.dataset.categoria !== categoria);
    });

    if (todas) {
        if (etiqueta) etiqueta.textContent = titularGastos.etiqueta;
        if (monto) monto.textContent = titularGastos.monto;
        if (nota) nota.textContent = titularGastos.nota;
        return;
    }

    if (etiqueta) etiqueta.textContent = `Rendido en ${chip.dataset.nombre}`;
    if (monto) monto.textContent = chip.dataset.total;
    if (nota) nota.textContent = `${chip.dataset.parte}% del total gastado`;
}

document.addEventListener("click", (evento) => {
    const chip = evento.target.closest(".chip-gasto");
    if (!chip) return;

    document.querySelectorAll(".chip-gasto").forEach((otro) => otro.classList.remove("activa"));
    chip.classList.add("activa");

    filtrarGastos(chip);
});

repartirCintaGastos();
guardarTitularGastos();

// ---------- PAGOS (FILTRO SEMANA / MES + FLECHAS) ----------
// El bloque de pagos (#seccion-pagos) se refresca solo, con su propio periodo,
// sin tocar el resto de la pagina. Los enlaces traen los datos en data-* y aca
// se arma la URL completa preservando el resto de los filtros (desde/hasta/tipo).

const contenedorPagos = document.getElementById("seccion-pagos");

function cargarPagos(gran, ancla, page) {
    if (!contenedorPagos) return;

    // Parto de la URL actual para no pisar los filtros de gastos/viajes
    const url = new URL(window.location.href);
    if (gran) url.searchParams.set("pagos_gran", gran);
    if (ancla) url.searchParams.set("pagos_ancla", ancla);

    // Sin pagina explicita (cambio de periodo o granularidad) vuelvo a la primera
    if (page) {
        url.searchParams.set("pagos_page", page);
    } else {
        url.searchParams.delete("pagos_page");
    }

    // frag=pagos le pide a la vista solo este bloque; no queda en la barra de
    // direcciones para que la URL siga sirviendo para recargar la pagina entera.
    const urlFetch = new URL(url);
    urlFetch.searchParams.set("frag", "pagos");

    contenedorPagos.setAttribute("aria-busy", "true");

    fetch(urlFetch, { headers: { "X-Requested-With": "XMLHttpRequest" } })
        .then((respuesta) => respuesta.text())
        .then((html) => {
            contenedorPagos.innerHTML = html;
            contenedorPagos.removeAttribute("aria-busy");
            window.history.pushState({}, "", url);
        })
        .catch((error) => {
            contenedorPagos.removeAttribute("aria-busy");
            console.error("Error al cargar los pagos:", error);
        });
}

document.addEventListener("click", (evento) => {
    // Cambio de granularidad (Semanal / Mensual)
    const seg = evento.target.closest(".pagos-seg__opt");
    if (seg && !seg.classList.contains("es-activo")) {
        evento.preventDefault();
        cargarPagos(seg.dataset.pagosGran, seg.dataset.pagosAncla);
        return;
    }

    // Flechas de periodo y el atajo "Hoy"
    const paso = evento.target.closest(".pagos-nav__paso, .pagos-nav__hoy");
    if (paso && !paso.classList.contains("es-oculto")) {
        evento.preventDefault();
        cargarPagos(paso.dataset.pagosGran, paso.dataset.pagosAncla);
        return;
    }

    // Paginacion de la tabla de pagos (5 por pagina)
    const pag = evento.target.closest(".pagos-pag");
    if (pag) {
        evento.preventDefault();
        cargarPagos(pag.dataset.pagosGran, pag.dataset.pagosAncla, pag.dataset.pagosPage);
        return;
    }

    // Cada comision abre el detalle del viaje de cereal
    const filaComision = evento.target.closest(".fila-pago--comision");
    if (filaComision && filaComision.dataset.url) {
        window.location.href = filaComision.dataset.url;
    }
});

// ---------- MODAL DE PAGO ----------

function abrirModalPagoEmpleado() {
    const contenedor = document.getElementById("contenedor-modal-pago");
    if (!contenedor) return;

    contenedor.classList.add("abierto");
    document.body.classList.add("con-modal-abierto");

    // El monto es el dato que siempre hay que cargar (la fecha ya viene con la
    // de hoy), asi que el foco arranca ahi
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

// El separador de miles (formato_miles.js) reformatea el campo en un listener de
// input delegado en document. Un listener directo sobre el campo correria en fase
// target, antes del reformateo, y veria "1000" sin puntos: eso no matchea el
// pattern y marcaba el error en falso. Delego este tambien en document y, como
// este archivo se carga despues de formato_miles.js, corre despues de el en la
// fase de burbuja, cuando el campo ya tiene el "1.000" definitivo.
document.addEventListener("input", (evento) => {
    if (evento.target.id === "monto-pago") {
        montoTocado = true;
        revisarMontoPago();
    }
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

// ---------- VIAJES ----------
// Pestañas de tipo, paginacion y filas: todo por delegacion, porque el bloque se
// reemplaza con cada carga AJAX.

document.addEventListener("click", (evento) => {
    // Pestañas de tipo de viaje
    const tab = evento.target.closest(".tab-viaje");
    if (tab && !tab.classList.contains("activa")) {
        const url = armarUrlSecciones();
        url.searchParams.set("tipo", tab.dataset.tipo);
        // Al cambiar de tipo vuelvo a la primera pagina
        url.searchParams.delete("page_viajes");
        cargarSecciones(url);
        return;
    }

    // Paginacion de viajes
    const paginacion = evento.target.closest("#seccion-viajes .paginacion-botones a");
    if (paginacion) {
        evento.preventDefault();
        cargarSecciones(armarUrlSecciones(paginacion.href));
        return;
    }

    // Cada fila abre el detalle del viaje
    const fila = evento.target.closest(".fila-viaje-empleado");
    if (fila && fila.dataset.url) {
        window.location.href = fila.dataset.url;
    }
});
