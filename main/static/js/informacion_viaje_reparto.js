// Logica de la vista "Informacion del viaje de reparto".
// La eliminacion reutiliza abrirPanelEliminar()/cerrarPanelEliminar() de
// paneles.js (mismo markup #contenedor-panel-eliminar / #boton-confirmar-eliminar)
// y la apertura/cierre del slide-over usa abrirSlideOver()/cerrarSlideOver().
// Aca va el modal de "Registrar gasto"; el destino se elige del catalogo y su
// tarifa la completa destino_reparto.js.

function abrirModalGasto() {
    document.getElementById('contenedor-modal-gasto').classList.add('abierto');
    document.body.style.overflow = 'hidden';
}

function cerrarModalGasto() {
    document.getElementById('contenedor-modal-gasto').classList.remove('abierto');
    document.body.style.overflow = 'auto';
    const formGasto = document.getElementById('formulario-gasto');
    if (formGasto) {
        formGasto.reset();
    }
}
