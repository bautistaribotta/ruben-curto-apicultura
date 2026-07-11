/**
 * -----------------------------------------------------------------------------
 * BUSQUEDA Y PAGINACION (AJAX) DE VIAJES DE REPARTO (MERCADO LIBRE)
 * Mismo comportamiento que la tabla de cereales: busca y pagina sin recargar la
 * pagina entera, manteniendo el bloqueo de los botones del footer.
 * -----------------------------------------------------------------------------
 */

const inputBusquedaMeli = document.getElementById('buscador-viajes-meli');
const contenedorTablaMeli = document.getElementById('contenedor-tabla-viajes-meli');

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

vincularPaginacionMeli();
