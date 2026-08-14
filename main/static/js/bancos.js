// =============================================
//  BANCOS - catalogo simple
//  Buscador client-side sobre las tarjetas y slide-over de alta/edicion.
//  Reusa abrirSlideOver / cerrarSlideOver / abrirPanelEliminar de paneles.js.
// =============================================

// ---------- BUSQUEDA (filtro por nombre, client-side) ----------

function filtrarBancos() {
    const input = document.getElementById('buscar-banco');
    if (!input) return;

    const termino = input.value.trim().toLowerCase();
    const tarjetas = document.querySelectorAll('#grilla-bancos .tarjeta-banco');
    let visibles = 0;

    tarjetas.forEach((tarjeta) => {
        const coincide = tarjeta.dataset.nombre.includes(termino);
        tarjeta.hidden = !coincide;
        if (coincide) visibles++;
    });

    const sinResultados = document.getElementById('bancos-sin-resultados');
    if (sinResultados) {
        sinResultados.hidden = !(tarjetas.length > 0 && visibles === 0);
    }
}

document.getElementById('buscar-banco')?.addEventListener('input', filtrarBancos);

// ---------- ALTA / EDICION (slide-over) ----------

function abrirNuevoBanco() {
    document.getElementById('accion-banco').value = 'nuevo_banco';
    document.getElementById('id-banco-input').value = '';
    document.getElementById('nombre-banco').value = '';
    document.getElementById('titulo-banco').textContent = 'Nuevo banco';
    document.getElementById('subtitulo-banco').textContent = 'Registra un banco';
    document.getElementById('boton-guardar-banco').textContent = 'Guardar banco';
    abrirSlideOver();
}

function abrirEditarBanco(boton) {
    document.getElementById('accion-banco').value = 'editar_banco';
    document.getElementById('id-banco-input').value = boton.dataset.id;
    document.getElementById('nombre-banco').value = boton.dataset.nombre;
    document.getElementById('titulo-banco').textContent = 'Editar banco';
    document.getElementById('subtitulo-banco').textContent = 'Modifica el nombre del banco';
    document.getElementById('boton-guardar-banco').textContent = 'Actualizar banco';
    abrirSlideOver();
}

// ---------- ELIMINAR (modal de confirmacion) ----------

function abrirEliminarBanco(boton) {
    document.getElementById('id_eliminar').value = boton.dataset.id;
    document.getElementById('texto-confirmacion-eliminar').innerHTML =
        `¿Seguro que quiere eliminar el banco <b>${boton.dataset.nombre}</b>? ` +
        'Dejará de aparecer para las cuentas corrientes, pero se conservan las ya cargadas.';
    if (typeof abrirPanelEliminar === 'function') abrirPanelEliminar();
}

// Autocapitaliza la primera letra del nombre al escribir
const inputNombreBanco = document.getElementById('nombre-banco');
if (inputNombreBanco) {
    inputNombreBanco.addEventListener('input', (evento) => {
        const valor = evento.target.value;
        if (valor.length > 0) {
            evento.target.value = valor.charAt(0).toUpperCase() + valor.slice(1);
        }
    });
}

// Accesibles desde los onclick del HTML
window.abrirNuevoBanco = abrirNuevoBanco;
window.abrirEditarBanco = abrirEditarBanco;
window.abrirEliminarBanco = abrirEliminarBanco;
