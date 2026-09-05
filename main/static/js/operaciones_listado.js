/**
 * -----------------------------------------------------------------------------
 * LISTADO DE OPERACIONES: FILTRADO Y PAGINACION (AJAX)
 * Solo lectura. Refresca la tabla sin recargar la pagina al cambiar el filtro de
 * producto (chip -> modal) o el de fecha (chip + popover), y al paginar.
 *
 * El estado aplicado de cada filtro vive fuera de la tabla que reemplaza el AJAX:
 *   - producto -> data-* del chip .filtro-entidad (lo vuelca aplicarFiltrosEntidad).
 *   - fecha    -> data-desde/data-hasta de #filtro-fechas.
 * Por eso ambos sobreviven a los refrescos y a "Anterior"/"Siguiente".
 * -----------------------------------------------------------------------------
 */

const contenedorTabla = document.getElementById('tabla-operaciones-container');
const filtroFechas = document.getElementById('filtro-fechas');

/**
 * Vuelca el rango de fechas aplicado (data-* del chip) en la URL, tanto al buscar
 * como al paginar, para que el filtro sobreviva.
 */
const aplicarFechas = (url) => {
  const dd = filtroFechas ? filtroFechas.dataset.desde : '';
  const hh = filtroFechas ? filtroFechas.dataset.hasta : '';
  if (dd) url.searchParams.set('desde', dd); else url.searchParams.delete('desde');
  if (hh) url.searchParams.set('hasta', hh); else url.searchParams.delete('hasta');
};

/**
 * Busca operaciones aplicando el filtro por producto y por fecha mediante AJAX.
 * @param {string|null} urlString - URL opcional (por ejemplo, para la paginacion).
 */
const buscar = (urlString = null) => {
  if (!contenedorTabla) return;

  let url;
  if (urlString) {
    url = new URL(urlString, window.location.origin);
  } else {
    url = new URL(window.location.href);
    url.searchParams.delete('page');
  }

  // Los chips viven fuera de la region que reemplaza el AJAX: vuelco su estado en
  // la URL tanto al buscar como al paginar.
  if (typeof aplicarFiltrosEntidad === 'function') aplicarFiltrosEntidad(url);
  aplicarFechas(url);

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
 * Hace que los enlaces de paginacion funcionen por AJAX en vez de recargar la pagina.
 */
const vincularPaginacion = () => {
  if (!contenedorTabla) return;
  contenedorTabla.querySelectorAll('.paginacion-botones a').forEach((link) => {
    link.addEventListener('click', (e) => {
      e.preventDefault();
      buscar(link.href);
    });
  });
};

// Los filtros avisan por evento (mismo patron que Viajes); recargo la tabla.
document.addEventListener('filtroentidad:cambio', () => buscar());
document.addEventListener('filtrofechas:cambio', () => buscar());

vincularPaginacion();
