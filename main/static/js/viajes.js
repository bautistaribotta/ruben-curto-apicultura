/**
 * -----------------------------------------------------------------------------
 * BÚSQUEDA, FILTRADO POR ESTADO Y PAGINACIÓN (AJAX)
 * -----------------------------------------------------------------------------
 */

const filtroEstado = document.getElementById('filtro-estado');
const contenedorTabla = document.getElementById('tabla-viajes-container');
const filtroFechasViaje = document.getElementById('filtro-fechas');

/**
 * Vuelca el rango de fechas aplicado (data-* del chip) en la URL, tanto en la
 * busqueda como en la paginacion, para que el filtro sobreviva al paginar.
 */
const aplicarFechasViaje = (url) => {
  const dd = filtroFechasViaje ? filtroFechasViaje.dataset.desde : '';
  const hh = filtroFechasViaje ? filtroFechasViaje.dataset.hasta : '';
  if (dd) url.searchParams.set('desde', dd); else url.searchParams.delete('desde');
  if (hh) url.searchParams.set('hasta', hh); else url.searchParams.delete('hasta');
};

/**
 * Busca viajes aplicando los filtros por entidad (empleado/vehiculo/destino), el
 * estado y la fecha mediante AJAX, sin recargar la página entera.
 * @param {string|null} urlString - URL opcional (ej: para paginación).
 */
const buscar = (urlString = null) => {
  if (!filtroEstado || !contenedorTabla) return;

  const estado = filtroEstado.value;
  let url;

  if (urlString) {
    url = new URL(urlString, window.location.origin);
  } else {
    url = new URL(window.location.href);
    if (estado) {
      url.searchParams.set('estado', estado);
    } else {
      url.searchParams.delete('estado');
    }
    url.searchParams.delete('page');
  }

  // Los filtros por entidad y por fecha viven en sus chips (fuera de la tabla que
  // reemplaza el AJAX); los vuelco en la URL tanto al buscar como al paginar.
  if (typeof aplicarFiltrosEntidad === 'function') aplicarFiltrosEntidad(url);
  aplicarFechasViaje(url);

  fetch(url, {
    headers: {
      'X-Requested-With': 'XMLHttpRequest',
    },
  })
    .then((response) => response.text())
    .then((html) => {
      contenedorTabla.innerHTML = html;
      window.history.pushState({}, '', url);
      vincularPaginacion();
    })
    .catch((error) => console.error('Error en la búsqueda:', error));
};

/**
 * Hace que los enlaces de paginación funcionen por AJAX.
 */
const vincularPaginacion = () => {
  if (!contenedorTabla) return;
  const linksPaginacion = contenedorTabla.querySelectorAll('.paginacion-botones a');

  linksPaginacion.forEach((link) => {
    link.addEventListener('click', (e) => {
      e.preventDefault();
      buscar(link.href);
    });
  });
};

// Los chips de filtro por entidad avisan por evento; recargo la tabla al cambiar.
document.addEventListener('filtroentidad:cambio', () => buscar());

// El filtro de fecha avisa por evento; recargo la tabla con el rango aplicado.
document.addEventListener('filtrofechas:cambio', () => buscar());

// La pildora de estado (filtro_estado_viaje.js) avisa por evento tras escribir el
// nuevo valor en #filtro-estado; recargo la tabla con ese estado.
document.addEventListener('filtroestado:cambio', () => buscar());

vincularPaginacion();
