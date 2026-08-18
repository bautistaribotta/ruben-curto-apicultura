// =============================================
//  CHEQUES - EMPRESAS / SOCIEDADES
//  Pildora selectora de empresa (filtro server-side) y slide-over de alta/edicion
//  de la empresa (compartida con IVA). Reusa abrirSlideOver / cerrarSlideOver de
//  paneles.js y el selector modal de selector_entidad.js. La baja de empresa se
//  hace desde IVA, asi que aca no esta.
// =============================================

// ---------- PILDORA DE EMPRESA (filtro server-side) ----------
// Reemplaza al buscador: al elegir una empresa recargo con ?empresa=ID preservando
// el periodo (mes/anio) que ya viaja en la URL; la "×" saca ese parametro.

(function () {
    const contenedor = document.getElementById('che-empresa');
    const trigger = document.getElementById('che-empresa-trigger');
    const modal = document.getElementById('selector-empresa-cheque');
    if (!contenedor || !trigger || !modal) return;

    function irAEmpresa(id) {
        const params = new URLSearchParams(window.location.search);
        if (id) {
            params.set('empresa', id);
        } else {
            params.delete('empresa');
        }
        const qs = params.toString();
        window.location.href = qs ? `?${qs}` : window.location.pathname;
    }

    trigger.addEventListener('click', (evento) => {
        // La "×" limpia el filtro sin abrir el modal
        if (evento.target.closest('.che-empresa__clear')) {
            evento.stopPropagation();
            irAEmpresa('');
            return;
        }
        if (typeof abrirSelectorEntidad === 'function') {
            abrirSelectorEntidad('selector-empresa-cheque');
        }
    });

    const limpiar = document.getElementById('che-empresa-clear');
    if (limpiar) {
        limpiar.addEventListener('keydown', (evento) => {
            if (evento.key === 'Enter' || evento.key === ' ') {
                evento.preventDefault();
                evento.stopPropagation();
                irAEmpresa('');
            }
        });
    }

    // El modal avisa la eleccion; recargo con la empresa elegida.
    modal.addEventListener('selector-entidad:elegir', (evento) => {
        irAEmpresa(evento.detail.id);
    });
})();

// ---------- NAVEGACION A LA FICHA (click en la tarjeta) ----------
// La tarjeta entera lleva a la ficha de cheques de la empresa, salvo que el click
// caiga sobre el boton de editar.

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
// La empresa es la misma entidad que en IVA: la baja logica la oculta de ambas
// secciones, asi que lo aviso en el texto para que no sorprenda.

function abrirEliminarEmpresa(boton) {
    document.getElementById('id_eliminar').value = boton.dataset.id;
    document.getElementById('texto-confirmacion-eliminar').innerHTML =
        `¿Seguro que quiere eliminar la empresa <b>${boton.dataset.nombre}</b>? ` +
        'Dejará de aparecer tanto en Cheques como en IVA, pero se conservan sus ' +
        'cheques y operaciones.';
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
