/**
 * -----------------------------------------------------------------------------
 * BUSQUEDA Y PAGINACION (AJAX) DE VIAJES DE REPARTO (MERCADO LIBRE)
 * Mismo comportamiento que la tabla de cereales: busca y pagina sin recargar la
 * pagina entera, manteniendo el bloqueo de los botones del footer.
 * -----------------------------------------------------------------------------
 */

const contenedorTablaMeli = document.getElementById('contenedor-tabla-viajes-meli');
const filtroFechasMeli = document.getElementById('filtro-fechas');

/**
 * Vuelca el rango de fechas aplicado (data-* del chip, fuente de verdad) en la
 * URL. Se llama tanto en la busqueda normal como en la paginacion para que el
 * filtro sobreviva a "Anterior"/"Siguiente".
 */
const aplicarFechasMeli = (url) => {
  const dd = filtroFechasMeli ? filtroFechasMeli.dataset.desde : '';
  const hh = filtroFechasMeli ? filtroFechasMeli.dataset.hasta : '';
  if (dd) url.searchParams.set('desde', dd); else url.searchParams.delete('desde');
  if (hh) url.searchParams.set('hasta', hh); else url.searchParams.delete('hasta');
};

/**
 * Busca viajes de reparto aplicando los filtros por entidad (empleado/vehiculo/
 * destino) y la fecha mediante AJAX.
 * @param {string|null} urlString - URL opcional (ej: para paginacion).
 */
const buscarMeli = (urlString = null) => {
  if (!contenedorTablaMeli) return;

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
  if (typeof aplicarFiltroPago === 'function') aplicarFiltroPago(url);
  aplicarFechasMeli(url);

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

      const nuevasTarjetas = fragmento.querySelector('#meli-stats-region');
      const nuevaTabla = fragmento.querySelector('#meli-tabla-region');
      const tarjetas = document.getElementById('meli-stats-region');

      if (nuevasTarjetas && tarjetas) {
        tarjetas.innerHTML = nuevasTarjetas.innerHTML;
      }
      if (nuevaTabla && contenedorTablaMeli) {
        contenedorTablaMeli.innerHTML = nuevaTabla.innerHTML;
      }

      window.history.pushState({}, '', url);
      vincularPaginacionMeli();
    })
    .catch((error) => console.error('Error en la busqueda:', error));
};

/**
 * Hace que los enlaces de paginacion funcionen por AJAX.
 */
const vincularPaginacionMeli = () => {
  if (!contenedorTablaMeli) return;
  const linksPaginacion = contenedorTablaMeli.querySelectorAll('.paginacion-botones a');

  linksPaginacion.forEach((link) => {
    link.addEventListener('click', (e) => {
      e.preventDefault();
      buscarMeli(link.href);
    });
  });
};

// Los chips de filtro por entidad avisan por evento; recargo la tabla al cambiar.
document.addEventListener('filtroentidad:cambio', () => buscarMeli());

// El filtro de fecha avisa por evento; recargo la tabla con el rango aplicado.
document.addEventListener('filtrofechas:cambio', () => buscarMeli());

// El segmentado de estado de cobro avisa por evento; recargo tabla y tarjetas.
document.addEventListener('filtropago:cambio', () => buscarMeli());

vincularPaginacionMeli();
