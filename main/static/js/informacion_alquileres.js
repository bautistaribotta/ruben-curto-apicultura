// =============================================
//  PERFIL DE UNA CASA
//
//  Los paneles (casa, contrato y eliminacion) son los del listado y los maneja
//  paneles_alquileres.js. Aca solo quedan los botones de esta pagina y el modal
//  de gasto, que todavia es puro front.
// =============================================

// =============================================
//  ACCIONES DE LA CASA Y DE LOS CONTRATOS
//
//  Los botones de contrato aparecen en dos lugares (la tarjeta del vigente y
//  cada fila del historial) con el mismo marcado, asi que van por delegacion en
//  document en vez de un listener por boton.
// =============================================

document.addEventListener('click', (evento) => {
    const editarContrato = evento.target.closest('.boton-contrato-editar');
    if (editarContrato) {
        // El perfil ya tiene el contrato renderizado, asi que los valores viajan
        // en el dataset del boton y no hace falta ir a buscarlos al servidor
        abrirContratoEdicion({
            id: editarContrato.dataset.contrato,
            casa: editarContrato.dataset.casa,
            inicio: editarContrato.dataset.inicio,
            fin: editarContrato.dataset.fin,
            monto_mensual: editarContrato.dataset.monto,
            comision_inmobiliaria: editarContrato.dataset.comision,
            nombre_inquilino: editarContrato.dataset.inquilino,
        });
        return;
    }

    const eliminarContrato = evento.target.closest('.boton-contrato-eliminar');
    if (eliminarContrato) {
        abrirEliminarContrato(eliminarContrato.dataset.contrato, eliminarContrato.dataset.plazo);
    }
});

const botonEditarCasa = document.getElementById('boton-editar-casa');
if (botonEditarCasa) {
    botonEditarCasa.addEventListener('click', () => abrirEditarCasa(botonEditarCasa.dataset.id));
}

const botonEliminarCasa = document.getElementById('boton-eliminar-casa');
if (botonEliminarCasa) {
    botonEliminarCasa.addEventListener('click', () =>
        abrirEliminarCasa(botonEliminarCasa.dataset.id, botonEliminarCasa.dataset.nombre));
}

// Solo esta cuando la casa no tiene contrato vigente: con uno corriendo no hay
// ninguno nuevo que cargar y el que se cargara se solaparia
const botonNuevoContrato = document.getElementById('boton-nuevo-contrato');
if (botonNuevoContrato) {
    botonNuevoContrato.addEventListener('click', () => abrirContratoNuevo(botonNuevoContrato.dataset.id));
}

// =============================================
//  MODAL DE GASTO
//
//  Dos modos sobre el mismo formulario, igual que el de contrato: uno carga un
//  gasto nuevo y el otro corrige uno guardado. Lo unico que cambia es la accion
//  del POST, el titulo y de donde salen los valores.
// =============================================

const modalGasto = document.getElementById('modal-gasto');
const categoriaGasto = document.getElementById('gasto-categoria');

function cerrarModalGasto() {
    modalGasto.classList.remove('abierto');
    document.body.style.overflow = 'auto';
}

function mostrarModalGasto() {
    modalGasto.classList.add('abierto');
    document.body.style.overflow = 'hidden';
    categoriaGasto.focus();
}

function abrirGastoNuevo() {
    document.getElementById('form-gasto').reset();
    document.getElementById('gasto-accion').value = 'nuevo_gasto';
    document.getElementById('gasto-id').value = '';
    document.getElementById('gasto-titulo').textContent = 'Nuevo gasto';
    document.getElementById('gasto-guardar').textContent = 'Guardar gasto';
    mostrarModalGasto();
}

// Los valores llegan en el dataset del boton y no por fetch: la fila que se
// esta editando ya esta renderizada en pantalla con esos mismos datos.
function abrirGastoEdicion(datos) {
    document.getElementById('form-gasto').reset();
    document.getElementById('gasto-accion').value = 'editar_gasto';
    document.getElementById('gasto-id').value = datos.gasto;
    document.getElementById('gasto-titulo').textContent = 'Editar gasto';
    document.getElementById('gasto-guardar').textContent = 'Guardar cambios';

    categoriaGasto.value = datos.categoria;
    document.getElementById('gasto-fecha').value = datos.fecha;
    document.getElementById('gasto-detalle').value = datos.detalle;
    ponerValorMiles(document.getElementById('gasto-monto'), datos.monto);

    mostrarModalGasto();
}

document.getElementById('boton-nuevo-gasto').addEventListener('click', abrirGastoNuevo);

// Las filas de gastos comparten marcado, asi que van por delegacion
document.addEventListener('click', (evento) => {
    const editar = evento.target.closest('.boton-gasto-editar');
    if (editar) {
        abrirGastoEdicion(editar.dataset);
        return;
    }

    const eliminar = evento.target.closest('.boton-gasto-eliminar');
    if (eliminar) {
        abrirModalEliminar({
            accion: 'eliminar_gasto',
            idGasto: eliminar.dataset.gasto,
            titulo: 'Eliminar gasto',
            texto: `¿Seguro que querés eliminar el gasto de <b>${eliminar.dataset.resumen}</b>? `
                 + 'No se puede deshacer.',
        });
    }
});

document.addEventListener('keydown', (evento) => {
    if (evento.key === 'Escape' && modalGasto.classList.contains('abierto')) {
        cerrarModalGasto();
    }
});

// =============================================
//  FILTRO DE FECHAS DE LOS GASTOS
//
//  filtro_fechas.js administra el popover y avisa con 'filtrofechas:cambio'; de
//  aca para abajo es cosa de esta pantalla.
//
//  Recarga la pagina en vez de refrescar la tabla por AJAX: el perfil no tiene
//  fragmento aparte que pedir, y con el rango en la URL el filtro sobrevive al
//  POST de cualquier accion, anda el boton de atras y el enlace se puede
//  compartir ya filtrado.
// =============================================

document.addEventListener('filtrofechas:cambio', () => {
    const filtro = document.getElementById('filtro-fechas');
    if (!filtro) return;

    const url = new URL(window.location.href);
    for (const [clave, valor] of [['desde', filtro.dataset.desde], ['hasta', filtro.dataset.hasta]]) {
        if (valor) {
            url.searchParams.set(clave, valor);
        } else {
            url.searchParams.delete(clave);
        }
    }
    window.location.href = url;
});
