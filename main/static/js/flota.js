// =============================================
//  GESTIÓN DE VEHÍCULOS (FLOTA)
//  Reusa los slide-overs (paneles.js) para alta y edición,
//  cambiando la accion/titulo/campos segun el caso.
//  Los empleados se gestionan desde la vista de empleados.
// =============================================

// ---------- VEHÍCULO ----------

function abrirNuevoVehiculo() {
    document.getElementById('accion-vehiculo').value = 'nuevo_vehiculo';
    document.getElementById('id-vehiculo-input').value = '';
    document.getElementById('nombre-vehiculo').value = '';
    document.getElementById('patente-vehiculo').value = '';
    document.getElementById('titulo-vehiculo').textContent = 'Nuevo Vehículo';
    abrirSlideOver('slide-over-vehiculo');
}

function abrirEditarVehiculo(boton) {
    document.getElementById('accion-vehiculo').value = 'editar_vehiculo';
    document.getElementById('id-vehiculo-input').value = boton.dataset.id;
    document.getElementById('nombre-vehiculo').value = boton.dataset.nombre;
    document.getElementById('patente-vehiculo').value = boton.dataset.patente;
    document.getElementById('titulo-vehiculo').textContent = 'Editar Vehículo';
    abrirSlideOver('slide-over-vehiculo');
}

// ---------- ELIMINAR (modal de confirmación) ----------

function abrirEliminarFlota(boton) {
    const id = boton.dataset.id;
    const nombre = boton.dataset.nombre;

    document.getElementById('accion-eliminar-flota').value = 'eliminar_vehiculo';
    document.getElementById('id-eliminar-vehiculo').value = id;

    document.getElementById('texto-eliminar-flota').innerHTML =
        `¿Seguro que quiere eliminar el vehículo <b>${nombre}</b>? Dejará de estar disponible para nuevos viajes.`;

    document.getElementById('modal-eliminar-flota').classList.add('abierto');
    document.body.style.overflow = 'hidden';
}

function cerrarModalEliminarFlota() {
    document.getElementById('modal-eliminar-flota').classList.remove('abierto');
    document.body.style.overflow = 'auto';

    // Reseteo el estado del boton de "mantener apretado" por si quedo a medias
    const btn = document.getElementById('boton-confirmar-eliminar');
    if (btn) {
        btn.classList.remove('manteniendo');
        const span = btn.querySelector('span');
        if (span && btn.dataset.textoOriginal) {
            span.innerText = btn.dataset.textoOriginal;
        }
    }
}
