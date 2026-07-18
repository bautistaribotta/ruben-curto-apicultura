/**
 * -----------------------------------------------------------------------------
 * BUSQUEDA Y PAGINACION (AJAX) DE VIAJES DE REPARTO (MERCADO LIBRE)
 * Mismo comportamiento que la tabla de cereales: busca y pagina sin recargar la
 * pagina entera, manteniendo el bloqueo de los botones del footer.
 * -----------------------------------------------------------------------------
 */

const inputBusquedaMeli = document.getElementById('buscador-viajes-meli');
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
 * Busca viajes de reparto aplicando el texto mediante AJAX.
 * @param {string|null} urlString - URL opcional (ej: para paginacion).
 */
const buscarMeli = (urlString = null) => {
  if (!inputBusquedaMeli || !contenedorTablaMeli) return;

  let url;

  if (urlString) {
    url = new URL(urlString, window.location.origin);
  } else {
    url = new URL(window.location.href);
    url.searchParams.set('q', inputBusquedaMeli.value);
    url.searchParams.delete('page');
  }

  aplicarFechasMeli(url);

  fetch(url, {
    headers: {
      'X-Requested-With': 'XMLHttpRequest',
    },
  })
    .then((response) => response.text())
    .then((html) => {
      contenedorTablaMeli.innerHTML = html;
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

if (inputBusquedaMeli) inputBusquedaMeli.addEventListener('input', () => buscarMeli());

// El filtro de fecha avisa por evento; recargo la tabla con el rango aplicado.
document.addEventListener('filtrofechas:cambio', () => buscarMeli());

vincularPaginacionMeli();
