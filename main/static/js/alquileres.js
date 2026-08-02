// =============================================
//  ALQUILERES
//
//  Cuatro cosas viven aca:
//    1. Navegador de mes de la cabecera. Cambiar de mes recarga la pagina (los
//       totales de arriba y la tabla se mueven juntos), asi que las flechas son
//       enlaces comunes; el JS solo agrega la grilla para saltar mas lejos.
//    2. Chips de estado y paginacion por AJAX sobre la tabla. La cabecera queda
//       afuera a proposito: mide el mes entero y no se mueve con los filtros.
//    3. Panel de casa (alta y edicion).
//    4. Panel de cobro, que ademas lista los ultimos pagos para poder
//       corregirlos mientras la casa no tenga perfil propio.
//
//  El slide-over y el "mantener presionado" del borrado los aporta paneles.js;
//  el formato de miles de los montos, formato_miles.js.
// =============================================

const contenedorTablaCasas = document.getElementById('tabla-alquileres-container');
const contenedorChips = document.getElementById('alq-chips');

const formateadorPesos = new Intl.NumberFormat('es-AR', {
    style: 'currency',
    currency: 'ARS',
    maximumFractionDigits: 0,
});

// "60000.00" (como lo manda el servidor) -> "$ 60.000". El vacio es un dato que
// no esta cargado, no un cero.
function comoPesos(valor) {
    if (valor === '' || valor === null || valor === undefined) return '—';
    const numero = Number(valor);
    return Number.isNaN(numero) ? '—' : formateadorPesos.format(numero);
}

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

    // Un mes cobrado no admite un segundo pago, asi que el boton de cobro
    // acompaña a la casilla en vez de abrir un panel que va a ser rechazado.
    const cobrar = fila && fila.querySelector('.alq-boton-icono.cobrar');
    if (cobrar) {
        cobrar.disabled = datos.pagado;
        cobrar.dataset.estado = datos.estado || '';
        cobrar.title = datos.pagado
            ? 'El alquiler de este mes ya está cobrado'
            : 'Registrar pago';
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
            document.getElementById('comision-casa').value = casa.comision_inmobiliaria;
            document.getElementById('alquilada-casa').checked = casa.alquilada;
            document.getElementById('fecha-alta-casa').value = casa.fecha_alta;

            // El precio llega pelado del servidor ("120000.00"): lo paso por el
            // formato de miles para que se vea igual que en la tabla
            ponerValorMiles(document.getElementById('precio-casa'), casa.precio);

            document.getElementById('icono-casa').textContent = 'edit_note';
            document.getElementById('titulo-casa').textContent = 'Editar casa';
            document.getElementById('subtitulo-casa').textContent = casa.nombre || 'Sin nombre';
            document.getElementById('boton-guardar-casa').textContent = 'Guardar cambios';
            abrirSlideOver('slide-over-casa');
        })
        .catch(() => abrirModalError('No se pudieron cargar los datos de la casa.'));
}

// =============================================
//  PANEL DE COBRO
// =============================================

// Clase de color por estado, para que el panel hable el mismo idioma que la
// pildora de la tabla
const CLASE_POR_ESTADO = {
    'Cobrado': 'alq-estado-casa__valor--cobrado',
    'Pendiente de cobro': 'alq-estado-casa__valor--pendiente',
    'Sin alquilar': 'alq-estado-casa__valor--libre',
};

function pintarEstadoCasa(datos) {
    document.getElementById('cobro-alquiler').textContent = comoPesos(datos.precio);

    const estado = document.getElementById('cobro-estado');
    // Si el mes esta cobrado, el dato util es cuanto entro, no la palabra sola
    estado.textContent = datos.estado === 'Cobrado'
        ? `Cobrado · ${comoPesos(datos.cobrado)}`
        : datos.estado;
    estado.className = 'alq-estado-casa__valor ' + (CLASE_POR_ESTADO[datos.estado] || '');

    // Cargar un segundo pago del mismo mes lo rechaza la base: lo aviso antes
    document.getElementById('alq-aviso-cobrado').hidden = datos.estado !== 'Cobrado';
}

function marcarAtajoPeriodo(valor) {
    document.querySelectorAll('.alq-atajo').forEach((atajo) => {
        atajo.classList.toggle('es-activo', atajo.dataset.periodo === valor);
    });
}

function pintarHistorial(pagos) {
    const contenedor = document.getElementById('alq-historial');

    if (!pagos.length) {
        contenedor.innerHTML = '<p class="alq-historial__vacio">Todavía no hay pagos cargados para esta casa.</p>';
        return;
    }

    contenedor.innerHTML = pagos.map((pago) => `
        <div class="alq-pago">
          <div class="alq-pago__datos">
            <span class="alq-pago__periodo">Mes ${pago.periodo_label}</span>
            <span class="alq-pago__fecha">Cobrado el ${pago.fecha.split('-').reverse().join('/')}</span>
          </div>
          <span class="alq-pago__monto">${comoPesos(pago.monto)}</span>
          <button type="button" class="alq-boton-icono editar" title="Editar pago"
                  data-pago="${pago.id}" data-monto="${pago.monto}"
                  data-fecha="${pago.fecha}" data-periodo="${pago.periodo}">
            <span class="material-symbols-outlined">edit</span>
          </button>
          <button type="button" class="alq-boton-icono eliminar" title="Eliminar pago"
                  data-pago="${pago.id}" data-etiqueta="${pago.periodo_label}">
            <span class="material-symbols-outlined">delete</span>
          </button>
        </div>
    `).join('');
}

function cargarHistorial(idCasa) {
    document.getElementById('alq-historial').innerHTML =
        '<p class="alq-historial__vacio">Cargando pagos…</p>';

    fetch(`/api/casas/${idCasa}/pagos/`)
        .then((respuesta) => respuesta.json())
        .then((datos) => pintarHistorial(datos.pagos))
        .catch(() => {
            document.getElementById('alq-historial').innerHTML =
                '<p class="alq-historial__vacio">No se pudieron cargar los pagos.</p>';
        });
}

// 'origen' es el boton de cobro de la fila, con los data-* del estado de la
// casa en el mes que se esta mirando.
function abrirCobro(origen) {
    const formulario = document.getElementById('form-cobro');
    formulario.reset();

    document.getElementById('accion-cobro').value = 'nuevo_pago';
    document.getElementById('id-casa-cobro').value = origen.dataset.id;
    document.getElementById('id-pago-cobro').value = '';
    document.getElementById('titulo-cobro').textContent = 'Cobrar alquiler';
    document.getElementById('subtitulo-cobro').textContent = origen.dataset.nombre;
    document.getElementById('boton-guardar-cobro').textContent = 'Registrar pago';

    pintarEstadoCasa(origen.dataset);

    // El alquiler se cobra completo, asi que el monto arranca en el precio de la
    // casa: en el caso normal alcanza con abrir y guardar. Sin precio cargado
    // queda vacio para que el usuario escriba.
    const inputMonto = document.getElementById('monto-cobro');
    const precio = origen.dataset.precio;
    if (precio && Number(precio) > 0) {
        ponerValorMiles(inputMonto, precio);
    } else {
        inputMonto.value = '';
    }

    const periodo = document.getElementById('periodo-cobro');
    periodo.value = periodo.defaultValue;
    marcarAtajoPeriodo(periodo.value);

    cargarHistorial(origen.dataset.id);
    abrirSlideOver('slide-over-cobro');
}

function prepararEditarPago(boton) {
    document.getElementById('accion-cobro').value = 'editar_pago';
    document.getElementById('id-pago-cobro').value = boton.dataset.pago;
    document.getElementById('titulo-cobro').textContent = 'Editar pago';
    document.getElementById('boton-guardar-cobro').textContent = 'Guardar cambios';
    // Editar es justamente lo que propone el aviso: una vez aca ya no aporta
    document.getElementById('alq-aviso-cobrado').hidden = true;

    ponerValorMiles(document.getElementById('monto-cobro'), boton.dataset.monto);
    document.getElementById('fecha-cobro').value = boton.dataset.fecha;
    document.getElementById('periodo-cobro').value = boton.dataset.periodo;
    marcarAtajoPeriodo(boton.dataset.periodo);

    document.getElementById('monto-cobro').focus();
}

// Atajos del mes que cubre el pago
document.querySelectorAll('.alq-atajo').forEach((atajo) => {
    atajo.addEventListener('click', () => {
        document.getElementById('periodo-cobro').value = atajo.dataset.periodo;
        marcarAtajoPeriodo(atajo.dataset.periodo);
    });
});

document.getElementById('periodo-cobro').addEventListener('change', (evento) => {
    marcarAtajoPeriodo(evento.target.value);
});

// =============================================
//  ELIMINACION (casas y pagos comparten el modal)
// =============================================

function abrirModalEliminar({ accion, idCasa = '', idPago = '', titulo, texto }) {
    document.getElementById('accion-eliminar').value = accion;
    document.getElementById('id-casa-eliminar').value = idCasa;
    document.getElementById('id-pago-eliminar').value = idPago;
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
        // Los botones deshabilitados (mes ya cobrado) no disparan click, asi que
        // no hace falta filtrarlos aca
        const cobrar = evento.target.closest('.alq-boton-icono.cobrar');
        const editar = evento.target.closest('.alq-boton-icono.editar');
        const eliminar = evento.target.closest('.alq-boton-icono.eliminar');

        if (cobrar) {
            abrirCobro(cobrar);
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

// Historial del panel de cobro (se pinta desde JS)
document.getElementById('alq-historial').addEventListener('click', (evento) => {
    const editar = evento.target.closest('.alq-boton-icono.editar');
    const eliminar = evento.target.closest('.alq-boton-icono.eliminar');

    if (editar) {
        prepararEditarPago(editar);
    } else if (eliminar) {
        abrirModalEliminar({
            accion: 'eliminar_pago',
            idPago: eliminar.dataset.pago,
            titulo: 'Eliminar pago',
            texto: `¿Seguro que querés eliminar el pago del mes <b>${eliminar.dataset.etiqueta}</b>? `
                 + 'El mes vuelve a figurar como no cobrado.',
        });
    }
});

document.getElementById('boton-nueva-casa').addEventListener('click', abrirNuevaCasa);
