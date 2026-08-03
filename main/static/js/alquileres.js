// =============================================
//  ALQUILERES
//
//  Lo propio del listado:
//    1. Navegador de mes de la cabecera. Cambiar de mes recarga la pagina (los
//       totales de arriba y la tabla se mueven juntos), asi que las flechas son
//       enlaces comunes; el JS solo agrega la grilla para saltar mas lejos.
//    2. Chips de estado y paginacion por AJAX sobre la tabla. La cabecera queda
//       afuera a proposito: mide el mes entero y no se mueve con los filtros.
//    3. Los clicks de la tabla, que abren los paneles o el perfil de la casa.
//
//  Los paneles (casa, contrato y eliminacion) no estan aca: los comparte con el
//  perfil de una casa y viven en paneles_alquileres.js.
//
//  El cobro tampoco: lo hace la casilla de la primera columna, que maneja
//  pago_viaje.js. De eso solo queda escuchar el evento para acomodar la fila.
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
//  DELEGACION DE EVENTOS
//
//  La fila entera lleva al perfil de la casa, pero la primera celda y la de
//  acciones no: ahi el click ya significa otra cosa. Por eso el enlace no
//  envuelve la fila (un <a> no puede contener la casilla ni los botones) sino
//  que el salto se resuelve aca, descartando primero esos dos casos.
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
            abrirContratoNuevo(contrato.dataset.id);
            return;
        }
        if (editar) {
            abrirEditarCasa(editar.dataset.id);
            return;
        }
        if (eliminar) {
            abrirEliminarCasa(eliminar.dataset.id, eliminar.dataset.nombre);
            return;
        }

        // Cualquier otro punto de la fila abre el perfil. La casilla de cobro y
        // los botones ya salieron arriba; la celda de la casilla se descarta
        // entera para que el click al costado del tilde no navegue.
        if (evento.target.closest('.pago-celda, .alq-col-acciones')) return;

        const fila = evento.target.closest('tr[data-perfil]');
        if (fila) window.location.href = fila.dataset.perfil;
    });
}

document.getElementById('boton-nueva-casa').addEventListener('click', abrirNuevaCasa);
