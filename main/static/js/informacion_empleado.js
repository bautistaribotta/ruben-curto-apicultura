// Perfil de empleado.

// ---------- CUENTA CORRIENTE (MES A MES + FLECHAS) ----------
// El bloque de cuenta corriente (#seccion-pagos) se refresca solo, con su propio
// mes, sin tocar el resto de la pagina. Las flechas traen el mes en data-* y aca
// se arma la URL completa preservando el resto de los filtros (desde/hasta/tipo).

const contenedorPagos = document.getElementById("seccion-pagos");

function cargarPagos(ancla) {
    if (!contenedorPagos) return;

    // Parto de la URL actual para no pisar los filtros de viajes
    const url = new URL(window.location.href);
    if (ancla) url.searchParams.set("pagos_ancla", ancla);

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
    // Flechas de mes (anterior / siguiente) y atajo al mes actual: los tres
    // llevan el mes destino en data-pagos-ancla y refrescan el mismo bloque.
    const paso = evento.target.closest(".pagos-nav__paso, .pagos-hoy");
    if (paso) {
        evento.preventDefault();
        cargarPagos(paso.dataset.pagosAncla);
        return;
    }

    // Editar un pago: abre el mismo modal del alta pero con los datos cargados
    const btnEditarPago = evento.target.closest(".pago-editar");
    if (btnEditarPago) {
        abrirModalPagoEdicion(btnEditarPago.dataset);
        return;
    }

    // Eliminar un pago: usa el panel de confirmacion (el mismo del empleado)
    const btnEliminarPago = evento.target.closest(".pago-eliminar");
    if (btnEliminarPago) {
        prepararEliminarPago(btnEliminarPago.dataset.id);
        return;
    }

    // Cada comision abre el detalle del viaje de cereal
    const filaComision = evento.target.closest(".fila-pago--comision");
    if (filaComision && filaComision.dataset.url) {
        window.location.href = filaComision.dataset.url;
    }
});

// ---------- MODAL DE PAGO (ALTA Y EDICION) ----------
// Un solo modal para las dos cosas: el boton "Añadir pago" lo abre vacio y el
// lapiz de cada fila lo abre con los datos. El campo oculto pago-id es lo que
// distingue el alta (vacio) de la edicion en el servidor.

function mostrarModalPago() {
    const contenedor = document.getElementById("contenedor-modal-pago");
    if (!contenedor) return;

    contenedor.classList.add("abierto");
    document.body.classList.add("con-modal-abierto");

    // El proximo modal arranca sin el error del intento anterior
    montoTocado = false;
    document.querySelector(".campo-monto")?.classList.remove("con-error");

    // El monto es el dato que siempre hay que cargar, asi que el foco arranca ahi
    document.getElementById("monto-pago").focus();
}

function abrirModalPagoEmpleado() {
    const form = document.getElementById("form-pago-empleado");
    if (!form) return;

    form.reset();
    document.getElementById("pago-id").value = "";
    document.getElementById("titulo-modal-pago").textContent = "Añadir pago";
    document.getElementById("boton-guardar-pago").textContent = "Registrar pago";
    actualizarContadorObservacion();
    mostrarModalPago();
}

function abrirModalPagoEdicion(datos) {
    const form = document.getElementById("form-pago-empleado");
    if (!form) return;

    form.reset();
    document.getElementById("pago-id").value = datos.id;
    document.getElementById("titulo-modal-pago").textContent = "Editar pago";
    document.getElementById("boton-guardar-pago").textContent = "Guardar cambios";

    // ponerValorMiles (formato_miles.js) escribe el monto del servidor ya con el
    // formato es-AR que espera el pattern del input
    ponerValorMiles(document.getElementById("monto-pago"), datos.monto);
    document.getElementById("fecha-pago").value = datos.fecha;
    document.getElementById("observaciones-pago").value = datos.observaciones || "";
    actualizarContadorObservacion();
    mostrarModalPago();
}

// Reusa el panel de confirmacion del empleado, pero cambiando la accion del POST
// para que la vista borre el pago y no al empleado.
function prepararEliminarPago(id) {
    document.getElementById("id_eliminar").value = id;
    document.getElementById("accion-eliminar").value = "eliminar_pago";
    document.getElementById("texto-confirmacion-eliminar").innerText =
        "¿Está seguro que quiere eliminar este pago?";
    if (typeof abrirPanelEliminar === "function") abrirPanelEliminar();
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

// ---------- MODAL DE SUELDO ----------
// Un unico campo (el sueldo mensual). El boton "Fijar sueldo" lo abre con el
// sueldo actual ya cargado; el submit es normal y formato_miles.js limpia el
// separador de miles antes de que salga el POST.

function mostrarModalSueldo() {
    const contenedor = document.getElementById("contenedor-modal-sueldo");
    if (!contenedor) return;

    contenedor.classList.add("abierto");
    document.body.classList.add("con-modal-abierto");

    sueldoTocado = false;
    document.querySelector(".campo-sueldo")?.classList.remove("con-error");

    document.getElementById("monto-sueldo").focus();
}

function abrirModalSueldo(sueldoActual) {
    const form = document.getElementById("form-sueldo-empleado");
    if (!form) return;

    form.reset();
    // ponerValorMiles escribe el sueldo del servidor ("35000.00") con el formato
    // es-AR que espera el pattern. Un sueldo en 0 queda como "0", editable.
    ponerValorMiles(document.getElementById("monto-sueldo"), sueldoActual || "0");
    mostrarModalSueldo();
}

function cerrarModalSueldo() {
    const contenedor = document.getElementById("contenedor-modal-sueldo");
    if (!contenedor) return;

    contenedor.classList.remove("abierto");
    document.body.classList.remove("con-modal-abierto");

    document.getElementById("form-sueldo-empleado").reset();

    sueldoTocado = false;
    document.querySelector(".campo-sueldo")?.classList.remove("con-error");
}

// Mismo criterio que el monto del pago: marca en rojo recien despues de tocar.
let sueldoTocado = false;

function revisarSueldo() {
    const monto = document.getElementById("monto-sueldo");
    const campo = document.querySelector(".campo-sueldo");
    if (!monto || !campo) return;

    campo.classList.toggle("con-error", sueldoTocado && !monto.checkValidity());
}

document.getElementById("boton-fijar-sueldo")?.addEventListener("click", (evento) => {
    abrirModalSueldo(evento.currentTarget.dataset.sueldo);
});

document.addEventListener("input", (evento) => {
    if (evento.target.id === "monto-sueldo") {
        sueldoTocado = true;
        revisarSueldo();
    }
});

document.getElementById("monto-sueldo")?.addEventListener("blur", () => {
    sueldoTocado = true;
    revisarSueldo();
});

document.addEventListener("keydown", (evento) => {
    if (evento.key === "Escape" && document.getElementById("contenedor-modal-sueldo")?.classList.contains("abierto")) {
        cerrarModalSueldo();
    }
});

// ---------- MODAL DE CARNET (ALTA Y EDICION) ----------
// Un unico campo: la fecha de vencimiento del carnet. El boton de la tarjeta lo
// abre con la fecha actual ya cargada (vacio si todavia no hay ninguna). El
// titulo y el boton cambian segun sea un alta o una edicion.

function mostrarModalCarnet() {
    const contenedor = document.getElementById("contenedor-modal-carnet");
    if (!contenedor) return;

    contenedor.classList.add("abierto");
    document.body.classList.add("con-modal-abierto");

    document.getElementById("vencimiento-carnet").focus();
}

function abrirModalCarnet(vencimientoActual) {
    const form = document.getElementById("form-carnet-empleado");
    if (!form) return;

    form.reset();

    // Con fecha ya cargada es una edicion; sin fecha, un alta. El data-* viene
    // en formato "YYYY-MM-DD", que es justo lo que espera el input date.
    const esEdicion = Boolean(vencimientoActual);
    document.getElementById("vencimiento-carnet").value = vencimientoActual || "";
    document.getElementById("titulo-modal-carnet").textContent =
        esEdicion ? "Editar vencimiento" : "Agregar vencimiento";
    document.getElementById("boton-guardar-carnet").textContent =
        esEdicion ? "Guardar cambios" : "Guardar vencimiento";

    mostrarModalCarnet();
}

function cerrarModalCarnet() {
    const contenedor = document.getElementById("contenedor-modal-carnet");
    if (!contenedor) return;

    contenedor.classList.remove("abierto");
    document.body.classList.remove("con-modal-abierto");

    document.getElementById("form-carnet-empleado").reset();
}

document.getElementById("boton-carnet")?.addEventListener("click", (evento) => {
    abrirModalCarnet(evento.currentTarget.dataset.vencimiento);
});

document.addEventListener("keydown", (evento) => {
    if (evento.key === "Escape" && document.getElementById("contenedor-modal-carnet")?.classList.contains("abierto")) {
        cerrarModalCarnet();
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
