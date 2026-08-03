// =============================================
//  PANELES DE ALQUILERES
//
//  Los tres paneles que el listado y el perfil de una casa comparten: el
//  slide-over de la casa, el modal de contrato y el de eliminacion. El marcado
//  vive en paneles_alquileres.html y los estilos en alquileres.css.
//
//  Cada pantalla llama a las funciones de abrir que necesita:
//    - listado: nueva casa, editar casa, contrato nuevo, eliminar casa
//    - perfil:  todo lo anterior mas corregir y eliminar un contrato
//
//  El slide-over y el "mantener presionado" del borrado los aporta paneles.js;
//  el formato de miles de los montos, formato_miles.js.
// =============================================

// =============================================
//  PANEL DE CASA (ALTA Y EDICION)
// =============================================

function abrirNuevaCasa() {
    document.getElementById('form-casa').reset();
    document.getElementById('accion-casa').value = 'nueva_casa';
    document.getElementById('id-casa-input').value = '';
    document.getElementById('icono-casa').textContent = 'add_home';
    document.getElementById('titulo-casa').textContent = 'Nueva casa';
    document.getElementById('subtitulo-casa').textContent = 'Cargá lo que tengas a mano, después se completa';
    document.getElementById('boton-guardar-casa').textContent = 'Guardar casa';
    abrirSlideOver('slide-over-casa');
}

function abrirEditarCasa(id) {
    fetch(`/api/casas/${id}/`)
        .then((respuesta) => {
            if (!respuesta.ok) throw new Error('No encontrada');
            return respuesta.json();
        })
        .then((casa) => {
            document.getElementById('form-casa').reset();
            document.getElementById('accion-casa').value = 'editar_casa';
            document.getElementById('id-casa-input').value = casa.id;
            document.getElementById('nombre-casa').value = casa.nombre;
            document.getElementById('localidad-casa').value = casa.localidad;
            document.getElementById('direccion-casa').value = casa.direccion;

            document.getElementById('icono-casa').textContent = 'edit_note';
            document.getElementById('titulo-casa').textContent = 'Editar casa';
            document.getElementById('subtitulo-casa').textContent = casa.nombre || 'Sin nombre';
            document.getElementById('boton-guardar-casa').textContent = 'Guardar cambios';
            abrirSlideOver('slide-over-casa');
        })
        .catch(() => abrirModalError('No se pudieron cargar los datos de la casa.'));
}

// =============================================
//  MODAL DE CONTRATO
//
//  Dos modos sobre el mismo formulario. Uno carga el contrato que sigue y el
//  otro corrige uno ya guardado; lo unico que cambia es la accion del POST, el
//  titulo y de donde salen los valores.
// =============================================

const modalContrato = document.getElementById('modal-contrato');
const inicioContrato = document.getElementById('ctr-inicio');
const finContrato = document.getElementById('ctr-fin');

const formateadorFecha = new Intl.DateTimeFormat('es-AR', { dateStyle: 'short' });

// "2026-01-15" -> "15/1/26". Parseo a mano y no con new Date(texto): eso lo lee
// como UTC y en Argentina devuelve el dia anterior.
function comoFecha(iso) {
    const [anio, mes, dia] = iso.split('-').map(Number);
    return formateadorFecha.format(new Date(anio, mes - 1, dia));
}

function cerrarModalContrato() {
    modalContrato.classList.remove('abierto');
    document.body.style.overflow = 'auto';
}

function pintarContratoAnterior(anterior) {
    const bloque = document.getElementById('ctr-anterior');
    if (!anterior) {
        bloque.hidden = true;
        return;
    }
    document.getElementById('ctr-anterior-detalle').textContent =
        `${comoFecha(anterior.inicio)} – ${comoFecha(anterior.fin)} · $${Number(anterior.monto_mensual).toLocaleString('es-AR', { maximumFractionDigits: 0 })}`;
    bloque.hidden = false;
}

// La comision es un porcentaje entero. El type="number" ya rebota los decimales
// al mandar el formulario, pero recien despues de escribirlos: corto las teclas
// que arman un decimal para que ni se puedan tipear.
document.getElementById('ctr-comision').addEventListener('keydown', (evento) => {
    if ([',', '.', 'e', 'E', '+', '-'].includes(evento.key)) {
        evento.preventDefault();
    }
});

// Deja el formulario cargado con un contrato, o vacio si viene null
function ponerContratoEnFormulario(contrato) {
    inicioContrato.value = contrato ? contrato.inicio : '';
    finContrato.value = contrato ? contrato.fin : '';
    document.getElementById('ctr-comision').value = contrato ? contrato.comision_inmobiliaria : '';
    document.getElementById('ctr-inquilino').value = contrato ? contrato.nombre_inquilino : '';
    ponerValorMiles(document.getElementById('ctr-monto'), contrato ? contrato.monto_mensual : '');
}

function mostrarModalContrato() {
    modalContrato.classList.add('abierto');
    document.body.style.overflow = 'hidden';
    inicioContrato.focus();
}

// Contrato nuevo. Si vencio uno, el modal precarga sus numeros, que es lo que
// pasa al renovar: mismo inquilino, plazo nuevo, monto que casi siempre se
// retoca. Las fechas quedan en blanco a proposito: son lo que hay que decidir.
function abrirContratoNuevo(idCasa) {
    fetch(`/api/casas/${idCasa}/contrato/`)
        .then((respuesta) => {
            if (!respuesta.ok) throw new Error('No encontrada');
            return respuesta.json();
        })
        .then((datos) => {
            // El boton llega bloqueado cuando hay contrato vigente, pero la tabla
            // se refresca por AJAX y podria estar vieja: el servidor manda igual el
            // vigente y aca se corta antes de abrir un formulario que va a rebotar.
            if (datos.vigente) {
                abrirModalError('La casa ya tiene un contrato vigente. Vas a poder cargar '
                              + 'el próximo cuando ese se venza.');
                return;
            }

            document.getElementById('form-contrato').reset();
            document.getElementById('ctr-accion').value = 'nuevo_contrato';
            document.getElementById('ctr-id-casa').value = datos.casa.id;
            document.getElementById('ctr-id-contrato').value = '';
            document.getElementById('ctr-titulo').textContent = 'Nuevo contrato';
            document.getElementById('ctr-casa').textContent = datos.casa.nombre;
            document.getElementById('ctr-guardar').textContent = 'Guardar contrato';

            ponerContratoEnFormulario(datos.anterior);
            inicioContrato.value = '';
            finContrato.value = '';
            pintarContratoAnterior(datos.anterior);

            mostrarModalContrato();
        })
        .catch(() => abrirModalError('No se pudo cargar el contrato de la casa.'));
}

// Correccion de un contrato ya guardado. Los valores llegan en el dataset del
// boton y no por fetch: el perfil ya los tiene renderizados en pantalla.
function abrirContratoEdicion(datos) {
    document.getElementById('form-contrato').reset();
    document.getElementById('ctr-accion').value = 'editar_contrato';
    document.getElementById('ctr-id-casa').value = '';
    document.getElementById('ctr-id-contrato').value = datos.id;
    document.getElementById('ctr-titulo').textContent = 'Editar contrato';
    document.getElementById('ctr-casa').textContent = datos.casa;
    document.getElementById('ctr-guardar').textContent = 'Guardar cambios';

    ponerContratoEnFormulario(datos);
    pintarContratoAnterior(null);

    mostrarModalContrato();
}

document.addEventListener('keydown', (evento) => {
    if (evento.key === 'Escape' && modalContrato.classList.contains('abierto')) {
        cerrarModalContrato();
    }
});

// =============================================
//  MODAL DE ELIMINACION
// =============================================

function abrirModalEliminar({ accion, idCasa = '', idContrato = '', idGasto = '', titulo, texto }) {
    document.getElementById('accion-eliminar').value = accion;
    document.getElementById('id-casa-eliminar').value = idCasa;
    document.getElementById('id-contrato-eliminar').value = idContrato;
    document.getElementById('id-gasto-eliminar').value = idGasto;
    document.getElementById('titulo-eliminar-alquiler').textContent = titulo;
    document.getElementById('texto-eliminar-alquiler').innerHTML = texto;

    document.getElementById('modal-eliminar-alquiler').classList.add('abierto');
    document.body.style.overflow = 'hidden';
}

function cerrarModalEliminarAlquiler() {
    document.getElementById('modal-eliminar-alquiler').classList.remove('abierto');
    document.body.style.overflow = 'auto';

    // Reseteo el boton de "mantener apretado" por si quedo a medias
    const boton = document.getElementById('boton-confirmar-eliminar');
    if (boton) {
        boton.classList.remove('manteniendo');
        const etiqueta = boton.querySelector('span');
        if (etiqueta && boton.dataset.textoOriginal) {
            etiqueta.innerText = boton.dataset.textoOriginal;
        }
    }
}

// Texto unico para las dos pantallas: borrar un contrato nunca toca la plata,
// porque los pagos cuelgan de la casa. Lo que se pierde es el plazo y el monto,
// y con eso los meses que cubria pasan a figurar sin alquilar.
function abrirEliminarContrato(idContrato, plazo) {
    abrirModalEliminar({
        accion: 'eliminar_contrato',
        idContrato: idContrato,
        titulo: 'Eliminar contrato',
        texto: `¿Seguro que querés eliminar el contrato <b>${plazo}</b>? `
             + 'Los meses que cubría pasan a figurar sin alquilar. Los pagos que '
             + 'tengan cargados no se borran.',
    });
}

function abrirEliminarCasa(idCasa, nombre) {
    abrirModalEliminar({
        accion: 'eliminar_casa',
        idCasa: idCasa,
        titulo: 'Eliminar casa',
        texto: `¿Seguro que querés eliminar <b>${nombre}</b>? `
             + 'Sale del listado, pero sus pagos quedan guardados.',
    });
}
