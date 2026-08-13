// =============================================
//  IVA - EMPRESAS / SOCIEDADES
//  Buscador client-side sobre las tarjetas y slide-over de alta/edicion
//  (reusa abrirSlideOver / cerrarSlideOver / abrirPanelEliminar de paneles.js).
// =============================================

// ---------- BUSQUEDA (filtro por nombre, client-side) ----------

function filtrarEmpresas() {
    const input = document.getElementById('buscar-empresa');
    if (!input) return;

    const termino = input.value.trim().toLowerCase();
    const tarjetas = document.querySelectorAll('#grilla-iva .tarjeta-empresa');
    let visibles = 0;

    tarjetas.forEach((tarjeta) => {
        const coincide = tarjeta.dataset.nombre.includes(termino);
        tarjeta.hidden = !coincide;
        if (coincide) visibles++;
    });

    // Aviso de "sin resultados": solo cuando hay tarjetas y ninguna coincide
    const sinResultados = document.getElementById('iva-sin-resultados');
    if (sinResultados) {
        sinResultados.hidden = !(tarjetas.length > 0 && visibles === 0);
    }
}

document.getElementById('buscar-empresa')?.addEventListener('input', filtrarEmpresas);

// ---------- NAVEGACION A LA FICHA (click en la tarjeta) ----------
// La tarjeta entera lleva a la ficha de la empresa, salvo que el click caiga
// sobre los botones de editar/eliminar.

function irAFichaEmpresa(tarjeta) {
    const destino = tarjeta.dataset.href;
    if (destino) window.location.href = destino;
}

document.getElementById('grilla-iva')?.addEventListener('click', (evento) => {
    const tarjeta = evento.target.closest('.tarjeta-empresa');
    if (!tarjeta || evento.target.closest('.tarjeta-empresa__acciones')) return;
    irAFichaEmpresa(tarjeta);
});

document.getElementById('grilla-iva')?.addEventListener('keydown', (evento) => {
    if (evento.key !== 'Enter') return;
    const tarjeta = evento.target.closest('.tarjeta-empresa');
    if (!tarjeta || evento.target !== tarjeta) return;
    irAFichaEmpresa(tarjeta);
});

// ---------- ALTA / EDICION (slide-over) ----------

function abrirNuevaEmpresa() {
    document.getElementById('accion-empresa').value = 'nueva_empresa';
    document.getElementById('id-empresa-input').value = '';
    document.getElementById('nombre-empresa').value = '';
    document.getElementById('titulo-empresa').textContent = 'Nueva empresa / sociedad';
    document.getElementById('subtitulo-empresa').textContent = 'Registra una empresa o sociedad';
    document.getElementById('boton-guardar-empresa').textContent = 'Guardar empresa';
    abrirSlideOver();
}

function abrirEditarEmpresa(boton) {
    document.getElementById('accion-empresa').value = 'editar_empresa';
    document.getElementById('id-empresa-input').value = boton.dataset.id;
    document.getElementById('nombre-empresa').value = boton.dataset.nombre;
    document.getElementById('titulo-empresa').textContent = 'Editar empresa / sociedad';
    document.getElementById('subtitulo-empresa').textContent = 'Modifica los datos de la empresa o sociedad';
    document.getElementById('boton-guardar-empresa').textContent = 'Actualizar empresa';
    abrirSlideOver();
}

// ---------- ELIMINAR (modal de confirmacion) ----------

function abrirEliminarEmpresa(boton) {
    document.getElementById('id_eliminar').value = boton.dataset.id;
    document.getElementById('texto-confirmacion-eliminar').innerHTML =
        `¿Seguro que quiere eliminar la empresa <b>${boton.dataset.nombre}</b>? ` +
        'Dejará de aparecer en el listado, pero se conservan sus operaciones.';
    if (typeof abrirPanelEliminar === 'function') abrirPanelEliminar();
}

// Autocapitaliza la primera letra del nombre al escribir
const inputNombreEmpresa = document.getElementById('nombre-empresa');
if (inputNombreEmpresa) {
    inputNombreEmpresa.addEventListener('input', (evento) => {
        const valor = evento.target.value;
        if (valor.length > 0) {
            evento.target.value = valor.charAt(0).toUpperCase() + valor.slice(1);
        }
    });
}

// Accesibles desde los onclick del HTML
window.abrirNuevaEmpresa = abrirNuevaEmpresa;
window.abrirEditarEmpresa = abrirEditarEmpresa;
window.abrirEliminarEmpresa = abrirEliminarEmpresa;
