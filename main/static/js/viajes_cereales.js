/**
 * -----------------------------------------------------------------------------
 * BÚSQUEDA Y PAGINACIÓN (AJAX)
 * Mismo comportamiento que la tabla de viajes: busca y pagina sin recargar
 * la página entera, y mantiene el bloqueo de los botones del footer.
 * -----------------------------------------------------------------------------
 */

const contenedorTabla = document.getElementById('tabla-viajes-cereales-container');
const filtroFechasCereal = document.getElementById('filtro-fechas');

/**
 * Vuelca el rango de fechas aplicado (data-* del chip) en la URL, tanto en la
 * busqueda como en la paginacion, para que el filtro sobreviva al paginar.
 */
const aplicarFechasCereal = (url) => {
  const dd = filtroFechasCereal ? filtroFechasCereal.dataset.desde : '';
  const hh = filtroFechasCereal ? filtroFechasCereal.dataset.hasta : '';
  if (dd) url.searchParams.set('desde', dd); else url.searchParams.delete('desde');
  if (hh) url.searchParams.set('hasta', hh); else url.searchParams.delete('hasta');
};

/**
 * Busca viajes de cereales aplicando los filtros por entidad (empleado/vehiculo/
 * destino) y la fecha mediante AJAX.
 * @param {string|null} urlString - URL opcional (ej: para paginación).
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

  // Los filtros por entidad y por fecha viven en sus chips (fuera de la region que
  // reemplaza el AJAX); los vuelco en la URL tanto al buscar como al paginar.
  if (typeof aplicarFiltrosEntidad === 'function') aplicarFiltrosEntidad(url);
  if (typeof aplicarFiltroFactura === 'function') aplicarFiltroFactura(url);
  if (typeof aplicarFiltroPago === 'function') aplicarFiltroPago(url);
  aplicarFechasCereal(url);

  fetch(url, {
    headers: {
      'X-Requested-With': 'XMLHttpRequest',
    },
  })
    .then((response) => response.text())
    .then((html) => {
      // La respuesta trae dos regiones (tarjetas de resumen y tabla). Las parseo
      // y reemplazo cada una por su id, para que las tarjetas reflejen el filtro
      // aplicado sin recargar la pagina.
      const fragmento = document.createElement('div');
      fragmento.innerHTML = html;

      const nuevasTarjetas = fragmento.querySelector('#vjc-stats-region');
      const nuevaTabla = fragmento.querySelector('#vjc-tabla-region');
      const tarjetas = document.getElementById('vjc-stats-region');

      if (nuevasTarjetas && tarjetas) {
        tarjetas.innerHTML = nuevasTarjetas.innerHTML;
      }
      if (nuevaTabla && contenedorTabla) {
        contenedorTabla.innerHTML = nuevaTabla.innerHTML;
      }

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

// La pildora de busqueda por factura avisa por evento; recargo la tabla al aplicar.
document.addEventListener('filtrofactura:cambio', () => buscar());

// El filtro de fecha avisa por evento; recargo la tabla con el rango aplicado.
document.addEventListener('filtrofechas:cambio', () => buscar());

// El segmentado de estado de cobro avisa por evento; recargo tabla y tarjetas.
document.addEventListener('filtropago:cambio', () => buscar());

vincularPaginacion();
