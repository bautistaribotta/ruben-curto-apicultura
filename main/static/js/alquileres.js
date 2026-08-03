// =============================================
//  ALQUILERES
//
//  Cuatro cosas viven aca:
//    1. Navegador de mes de la cabecera. Cambiar de mes recarga la pagina (los
//       totales de arriba y la tabla se mueven juntos), asi que las flechas son
//       enlaces comunes; el JS solo agrega la grilla para saltar mas lejos.
//    2. Chips de estado y paginacion por AJAX sobre la tabla. La cabecera queda
//       afuera a proposito: mide el mes entero y no se mueve con los filtros.
//    3. Panel de casa (alta y edicion): solo la propiedad.
//    4. Modal de contrato, de donde salen el plazo, el monto y el inquilino.
//
//  El cobro no esta aca: lo hace la casilla de la primera columna, que maneja
//  pago_viaje.js. De eso solo queda escuchar el evento para acomodar la fila.
//
//  El slide-over y el "mantener presionado" del borrado los aporta paneles.js;
//  el formato de miles de los montos, formato_miles.js.
// =============================================

const contenedorTablaCasas = document.getElementById('tabla-alquileres-container');
const contenedorChips = document.getElementById('alq-chips');

// =============================================
//  NAVEGADOR DE MES
// =============================================

const navMes = document.getElementById('alq-nav');
const selectorMes = document.getElementById('alq-selector');
const botonMes = document.getElementById('alq-nav-mes');
const grillaMeses = document.getElementById('alq-selector-grilla');
const etiquetaAnio = document.getElementById('alq-selector-anio');

// "ene", "feb"... Recortados a tres letras porque el locale devuelve "sept" con
// punto incluido y en una grilla de doce el largo disparejo se nota.
const NOMBRES_MES = Array.from({ length: 12 }, (_, i) =>
    new Date(2000, i, 1).toLocaleDateString('es-AR', { month: 'short' }).replace('.', '').slice(0, 3));

// El año que muestra la grilla se mueve solo, sin ir al servidor: recien al
// elegir un mes se navega.
let anioMostrado = Number(navMes.dataset.mesVisto.slice(0, 4));

function pintarGrillaMeses() {
    etiquetaAnio.textContent = anioMostrado;

    const estado = navMes.dataset.estado;
    const sufijo = estado ? `&estado=${estado}` : '';

    grillaMeses.innerHTML = NOMBRES_MES.map((nombre, indice) => {
        const clave = `${anioMostrado}-${String(indice + 1).padStart(2, '0')}`;
        const clases = ['alq-selector__mes'];
        // El mes que se esta mirando y el mes en curso son dos cosas distintas
        // y pueden no coincidir: cada uno tiene su marca.
        if (clave === navMes.dataset.mesVisto) clases.push('es-visto');
        if (clave === navMes.dataset.mesActual) clases.push('es-actual');
        return `<a class="${clases.join(' ')}" href="?mes=${clave}${sufijo}">${nombre}</a>`;
    }).join('');
}

function cerrarSelectorMes() {
    selectorMes.hidden = true;
    botonMes.setAttribute('aria-expanded', 'false');
}

botonMes.addEventListener('click', () => {
    if (selectorMes.hidden) {
        // Siempre abre en el año del mes que se esta viendo, no donde quedo
        anioMostrado = Number(navMes.dataset.mesVisto.slice(0, 4));
        pintarGrillaMeses();
        selectorMes.hidden = false;
        botonMes.setAttribute('aria-expanded', 'true');
    } else {
        cerrarSelectorMes();
    }
});

selectorMes.querySelectorAll('.alq-selector__paso').forEach((paso) => {
    paso.addEventListener('click', () => {
        anioMostrado += Number(paso.dataset.paso);
        pintarGrillaMeses();
    });
});

document.addEventListener('click', (evento) => {
    if (!selectorMes.hidden && !navMes.contains(evento.target)) cerrarSelectorMes();
});

document.addEventListener('keydown', (evento) => {
    if (evento.key === 'Escape' && !selectorMes.hidden) {
        cerrarSelectorMes();
        botonMes.focus();
    }
});

// =============================================
//  CASILLA DE COBRO
//
//  El POST lo hace pago_viaje.js, compartido con reparto y cereal. Aca solo se
//  acomoda lo que en esta pantalla depende del cobro y que vive fuera de la
//  casilla: la pildora de la fila y los totales de la cabecera.
//
//  La fila NO se reordena. El listado ordena por urgencia, asi que al tildar la
//  casa saltaria de grupo y se movería justo debajo del cursor. Se queda donde
//  esta y se reacomoda en la proxima carga, como cualquier checklist.
// =============================================

const CLASE_PILDORA = {
    'Cobrado': 'alq-pildora--cobrada',
    'Pendiente de cobro': 'alq-pildora--pendiente',
    'Sin alquilar': 'alq-pildora--libre',
};

document.addEventListener('pago:cambiado', (evento) => {
    const { casilla, datos } = evento.detail;

    const fila = casilla.closest('tr');

    const pildora = fila && fila.querySelector('.alq-pildora');
    if (pildora && datos.estado) {
        pildora.className = 'alq-pildora ' + (CLASE_PILDORA[datos.estado] || '');
        pildora.innerHTML = '<span class="alq-pildora__punto"></span>' + datos.estado;
    }

    if (!datos.resumen) return;

    const cobrado = document.querySelector('.alq-cifra--cobrado .alq-cifra__valor');
    if (cobrado) cobrado.textContent = '$' + datos.resumen.cobrado;

    // La segunda cifra es la de pendiente: valor, contador de casas y el gris
    // de "no queda nada" tienen que moverse juntos.
    const bloquePendiente = document.querySelectorAll('.alq-cifra')[1];
    if (!bloquePendiente) return;

    bloquePendiente.querySelector('.alq-cifra__valor').textContent = '$' + datos.resumen.pendiente;
    bloquePendiente.classList.toggle('es-cero', !datos.resumen.pendientes);

    const casas = bloquePendiente.querySelector('.alq-cifra__casas');
    if (datos.resumen.pendientes) {
        const texto = `· ${datos.resumen.pendientes} casa${datos.resumen.pendientes === 1 ? '' : 's'}`;
        if (casas) {
            casas.textContent = texto;
        } else {
            bloquePendiente.querySelector('.alq-cifra__rotulo')
                .insertAdjacentHTML('beforeend', ` <span class="alq-cifra__casas">${texto}</span>`);
        }
    } else if (casas) {
        casas.remove();
    }
});

// =============================================
//  FILTROS Y PAGINACION
// =============================================

function estadoActivo() {
    const chip = contenedorChips && contenedorChips.querySelector('.alq-chip.es-activo');
    return chip ? chip.dataset.estado : '';
}

function refrescarTabla(urlString = null) {
    if (!contenedorTablaCasas) return;

    let url;
    if (urlString) {
        // La paginacion manda hrefs relativos ("?page=2"), asi que la base tiene
        // que ser la URL actual completa: con el origin solo caian en la raiz.
        url = new URL(urlString, window.location.href);
    } else {
        url = new URL(window.location.href);
        const estado = estadoActivo();
        if (estado) {
            url.searchParams.set('estado', estado);
        } else {
            url.searchParams.delete('estado');
        }
        url.searchParams.delete('page');
    }

    fetch(url, { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
        .then((respuesta) => respuesta.text())
        .then((html) => {
            contenedorTablaCasas.innerHTML = html;
            window.history.pushState({}, '', url);
            vincularPaginacion();
        })
        .catch(() => abrirModalError('No se pudo actualizar el listado de casas.'));
}

function vincularPaginacion() {
    if (!contenedorTablaCasas) return;
    contenedorTablaCasas.querySelectorAll('.paginacion-botones a').forEach((enlace) => {
        enlace.addEventListener('click', (evento) => {
            evento.preventDefault();
            refrescarTabla(enlace.getAttribute('href'));
        });
    });
}

if (contenedorChips) {
    contenedorChips.addEventListener('click', (evento) => {
        const chip = evento.target.closest('.alq-chip');
        if (!chip) return;

        contenedorChips.querySelectorAll('.alq-chip').forEach((c) => c.classList.remove('es-activo'));
        chip.classList.add('es-activo');
        refrescarTabla();
    });
}

vincularPaginacion();

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
//  Un solo boton para dos casos. El servidor dice cual: si la casa tiene un
//  contrato que cubre hoy, se edita ese (crear un segundo solapado seria
//  invalido igual); si vencio, se crea el que sigue precargado con lo del
//  anterior, que es lo que pasa al renovar.
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

// Deja el formulario cargado con un contrato, o vacio si viene null
function ponerContratoEnFormulario(contrato) {
    inicioContrato.value = contrato ? contrato.inicio : '';
    finContrato.value = contrato ? contrato.fin : '';
    document.getElementById('ctr-comision').value = contrato ? contrato.comision_inmobiliaria : '';
    document.getElementById('ctr-inquilino').value = contrato ? contrato.nombre_inquilino : '';
    ponerValorMiles(document.getElementById('ctr-monto'), contrato ? contrato.monto_mensual : '');
}

function abrirContrato(idCasa) {
    fetch(`/api/casas/${idCasa}/contrato/`)
        .then((respuesta) => {
            if (!respuesta.ok) throw new Error('No encontrada');
            return respuesta.json();
        })
        .then((datos) => {
            document.getElementById('form-contrato').reset();
            document.getElementById('ctr-id-casa').value = datos.casa.id;
            document.getElementById('ctr-casa').textContent = datos.casa.nombre;

            if (datos.vigente) {
                // Hay contrato corriendo: esto es una correccion, no una renovacion
                document.getElementById('ctr-accion').value = 'editar_contrato';
                document.getElementById('ctr-id-contrato').value = datos.vigente.id;
                document.getElementById('ctr-titulo').textContent = 'Contrato vigente';
                document.getElementById('ctr-guardar').textContent = 'Guardar cambios';
                ponerContratoEnFormulario(datos.vigente);
                pintarContratoAnterior(null);
            } else {
                document.getElementById('ctr-accion').value = 'nuevo_contrato';
                document.getElementById('ctr-id-contrato').value = '';
                document.getElementById('ctr-titulo').textContent = 'Nuevo contrato';
                document.getElementById('ctr-guardar').textContent = 'Guardar contrato';
                // Renovar es casi siempre el mismo inquilino con otro plazo y otro
                // monto: precargo lo que se repite y dejo las fechas en blanco,
                // que es justo lo que hay que decidir.
                ponerContratoEnFormulario(datos.anterior);
                inicioContrato.value = '';
                finContrato.value = '';
                pintarContratoAnterior(datos.anterior);
            }

            modalContrato.classList.add('abierto');
            document.body.style.overflow = 'hidden';
            inicioContrato.focus();
        })
        .catch(() => abrirModalError('No se pudo cargar el contrato de la casa.'));
}

document.addEventListener('keydown', (evento) => {
    if (evento.key === 'Escape' && modalContrato.classList.contains('abierto')) {
        cerrarModalContrato();
    }
});

// =============================================
//  ELIMINACION DE UNA CASA
// =============================================

function abrirModalEliminar({ accion, idCasa = '', titulo, texto }) {
    document.getElementById('accion-eliminar').value = accion;
    document.getElementById('id-casa-eliminar').value = idCasa;
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

// =============================================
//  DELEGACION DE EVENTOS
// =============================================

// La tabla se reemplaza por AJAX, asi que los clicks se escuchan en el contenedor
if (contenedorTablaCasas) {
    contenedorTablaCasas.addEventListener('click', (evento) => {
        // Los botones deshabilitados (casa dada de baja) no disparan click, asi
        // que no hace falta filtrarlos aca
        const contrato = evento.target.closest('.alq-boton-icono.contrato');
        const editar = evento.target.closest('.alq-boton-icono.editar');
        const eliminar = evento.target.closest('.alq-boton-icono.eliminar');

        if (contrato) {
            abrirContrato(contrato.dataset.id);
        } else if (editar) {
            abrirEditarCasa(editar.dataset.id);
        } else if (eliminar) {
            abrirModalEliminar({
                accion: 'eliminar_casa',
                idCasa: eliminar.dataset.id,
                titulo: 'Eliminar casa',
                texto: `¿Seguro que querés eliminar <b>${eliminar.dataset.nombre}</b>? `
                     + 'Sale del listado, pero sus pagos quedan guardados.',
            });
        }
    });
}

document.getElementById('boton-nueva-casa').addEventListener('click', abrirNuevaCasa);
