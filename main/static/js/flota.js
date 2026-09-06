// =============================================
//  GESTIÓN DE VEHÍCULOS (FLOTA)
//  Reusa los slide-overs (paneles.js) para alta y edición,
//  cambiando la accion/titulo/campos segun el caso.
//  Los empleados se gestionan desde la vista de empleados.
// =============================================

// ---------- BUSQUEDA (filtro por nombre, client-side) ----------

function filtrarVehiculos() {
    const input = document.getElementById('buscar-vehiculo');
    if (!input) return;

    const termino = input.value.trim().toLowerCase();
    const filas = document.querySelectorAll('#cuerpo-flota .fila-vehiculo');

    let visibles = 0;
    filas.forEach((fila) => {
        const coincide = fila.dataset.nombre.includes(termino);
        fila.hidden = !coincide;
        if (coincide) visibles++;
    });

    // Muestro el aviso de "sin resultados" solo cuando hay filas pero ninguna
    // coincide con la busqueda (no cuando la tabla esta vacia de entrada).
    const sinResultados = document.getElementById('flota-sin-resultados');
    if (sinResultados) sinResultados.hidden = !(filas.length && visibles === 0);

    // Reflejo en el footer cuantas filas quedan a la vista tras el filtro.
    const contador = document.getElementById('flota-visibles');
    if (contador) contador.textContent = visibles;
}

document.getElementById('buscar-vehiculo')?.addEventListener('input', filtrarVehiculos);

// ---------- NAVEGACION AL PERFIL (click en la fila) ----------
// La fila entera lleva al perfil del vehiculo, pero la ultima columna tiene los
// botones de editar/eliminar: ahi el click hace lo suyo y no navega.

function irAlPerfilVehiculo(fila) {
    const destino = fila.dataset.href;
    if (destino) window.location.href = destino;
}

document.getElementById('cuerpo-flota')?.addEventListener('click', (evento) => {
    const fila = evento.target.closest('.fila-vehiculo');
    if (!fila || evento.target.closest('.flota-acciones')) return;
    irAlPerfilVehiculo(fila);
});

document.getElementById('cuerpo-flota')?.addEventListener('keydown', (evento) => {
    if (evento.key !== 'Enter') return;
    const fila = evento.target.closest('.fila-vehiculo');
    if (!fila || evento.target !== fila) return;
    irAlPerfilVehiculo(fila);
});

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

// ---------- VENCIMIENTOS DE CARNET (modal de solo lectura) ----------

function abrirModalCarnets() {
    document.getElementById('modal-carnets').classList.add('abierto');
    document.body.style.overflow = 'hidden';
}

function cerrarModalCarnets() {
    document.getElementById('modal-carnets').classList.remove('abierto');
    document.body.style.overflow = 'auto';
}

document.addEventListener('keydown', (evento) => {
    if (evento.key !== 'Escape') return;
    const modal = document.getElementById('modal-carnets');
    if (modal?.classList.contains('abierto')) cerrarModalCarnets();
});

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
