// =============================================
//  CATALOGO DE DESTINOS DE REPARTO
//  Reusa el slide-over de paneles.js para alta y edicion,
//  cambiando la accion, el titulo y los campos segun el caso.
//  El boton de eliminar con "mantener presionado" tambien lo
//  maneja paneles.js (#boton-confirmar-eliminar).
// =============================================

function abrirNuevoDestino() {
    document.getElementById('accion-destino').value = 'nuevo_destino';
    document.getElementById('id-destino-input').value = '';
    document.getElementById('localidad-destino').value = '';
    document.getElementById('valor-destino').value = '';
    document.getElementById('titulo-destino').textContent = 'Nuevo destino';
    abrirSlideOver('slide-over-destino');
}

function abrirEditarDestino(boton) {
    document.getElementById('accion-destino').value = 'editar_destino';
    document.getElementById('id-destino-input').value = boton.dataset.id;
    document.getElementById('localidad-destino').value = boton.dataset.localidad;

    // El valor viene pelado de la base, lo paso por el formato de miles
    ponerValorMiles(document.getElementById('valor-destino'), boton.dataset.valor);

    document.getElementById('titulo-destino').textContent = 'Editar destino';
    abrirSlideOver('slide-over-destino');
}

function abrirEliminarDestino(boton) {
    document.getElementById('id-eliminar-destino').value = boton.dataset.id;
    document.getElementById('texto-eliminar-destino').innerHTML =
        `¿Seguro que quiere eliminar el destino <b>${boton.dataset.localidad}</b>? ` +
        `Dejará de estar disponible para nuevos repartos, pero los viajes ya cargados lo siguen mostrando.`;

    document.getElementById('modal-eliminar-destino').classList.add('abierto');
    document.body.style.overflow = 'hidden';
}

function cerrarModalEliminarDestino() {
    document.getElementById('modal-eliminar-destino').classList.remove('abierto');
    document.body.style.overflow = 'auto';

    // Reseteo el boton de "mantener apretado" por si quedo a medias
    const btn = document.getElementById('boton-confirmar-eliminar');
    if (btn) {
        btn.classList.remove('manteniendo');
        const span = btn.querySelector('span');
        if (span && btn.dataset.textoOriginal) {
            span.innerText = btn.dataset.textoOriginal;
        }
    }
}
