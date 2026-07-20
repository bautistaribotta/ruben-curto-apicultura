/**
 * -----------------------------------------------------------------------------
 * BÚSQUEDA Y PAGINACIÓN (AJAX)
 * Mismo comportamiento que la tabla de viajes: busca y pagina sin recargar
 * la página entera, y mantiene el bloqueo de los botones del footer.
 * -----------------------------------------------------------------------------
 */

const inputBusqueda = document.getElementById('buscar-viaje-cereal');
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
 * Busca viajes de cereales aplicando el texto ingresado mediante AJAX.
 * @param {string|null} urlString - URL opcional (ej: para paginación).
 */
const buscar = (urlString = null) => {
  if (!inputBusqueda || !contenedorTabla) return;

  const q = inputBusqueda.value;
  let url;

  if (urlString) {
    url = new URL(urlString, window.location.origin);
  } else {
    url = new URL(window.location.href);
    url.searchParams.set('q', q);
    url.searchParams.delete('page');
  }

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

if (inputBusqueda) inputBusqueda.addEventListener('input', () => buscar());

// El filtro de fecha avisa por evento; recargo la tabla con el rango aplicado.
document.addEventListener('filtrofechas:cambio', () => buscar());

vincularPaginacion();
