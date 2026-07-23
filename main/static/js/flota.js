// =============================================
//  GESTIÓN DE EMPLEADOS Y VEHÍCULOS (FLOTA)
//  Reusa los slide-overs (paneles.js) para alta y edición,
//  cambiando la accion/titulo/campos segun el caso.
// =============================================

// ---------- EMPLEADO ----------

function abrirNuevoEmpleado() {
    document.getElementById('accion-empleado').value = 'nuevo_empleado';
    document.getElementById('id-empleado-input').value = '';
    document.getElementById('nombre-empleado').value = '';
    document.getElementById('apellido-empleado').value = '';
    document.getElementById('titulo-empleado').textContent = 'Nuevo Empleado';
    abrirSlideOver('slide-over-empleado');
}

function abrirEditarEmpleado(boton) {
    document.getElementById('accion-empleado').value = 'editar_empleado';
    document.getElementById('id-empleado-input').value = boton.dataset.id;
    document.getElementById('nombre-empleado').value = boton.dataset.nombre;
    document.getElementById('apellido-empleado').value = boton.dataset.apellido;
    document.getElementById('titulo-empleado').textContent = 'Editar Empleado';
    abrirSlideOver('slide-over-empleado');
}

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

function abrirEliminarFlota(tipo, boton) {
    const id = boton.dataset.id;
    const nombre = boton.dataset.nombre;

    const inputEmpleado = document.getElementById('id-eliminar-empleado');
    const inputVehiculo = document.getElementById('id-eliminar-vehiculo');

    // Dejo habilitado solo el campo del tipo correspondiente (los disabled no se envian)
    if (tipo === 'empleado') {
        document.getElementById('accion-eliminar-flota').value = 'eliminar_empleado';
        inputEmpleado.disabled = false;
        inputEmpleado.value = id;
        inputVehiculo.disabled = true;
        inputVehiculo.value = '';
    } else {
        document.getElementById('accion-eliminar-flota').value = 'eliminar_vehiculo';
        inputVehiculo.disabled = false;
        inputVehiculo.value = id;
        inputEmpleado.disabled = true;
        inputEmpleado.value = '';
    }

    const etiqueta = tipo === 'empleado' ? 'al empleado' : 'el vehículo';
    document.getElementById('texto-eliminar-flota').innerHTML =
        `¿Seguro que quiere eliminar ${etiqueta} <b>${nombre}</b>? Dejará de estar disponible para nuevos viajes.`;

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
