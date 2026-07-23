/**
 * -----------------------------------------------------------------------------
 * BUSQUEDA Y PAGINACION DE EMPLEADOS (AJAX)
 * -----------------------------------------------------------------------------
 * Replica el patron de clientes.js: busqueda en tiempo real con debounce
 * y paginacion sin recarga de pagina.
 */

const inputBusquedaEmpleado = document.getElementById('buscar-empleado');
const contenedorTablaEmpleados = document.getElementById('tabla-empleados-container');

/**
 * Realiza la busqueda de empleados mediante AJAX.
 * Si recibe una URL (paginacion), la usa directamente.
 * Si no, construye la URL con el valor del input de busqueda.
 */
const buscarEmpleado = (urlString = null) => {
  if (!inputBusquedaEmpleado || !contenedorTablaEmpleados) return;

  const q = inputBusquedaEmpleado.value;
  let url;

  if (urlString) {
    url = new URL(urlString, window.location.origin);
  } else {
    url = new URL(window.location.href);
    url.searchParams.set('q', q);
    url.searchParams.delete('page');
  }

  fetch(url, {
    headers: {
      'X-Requested-With': 'XMLHttpRequest',
    },
  })
    .then((response) => response.text())
    .then((html) => {
      contenedorTablaEmpleados.innerHTML = html;
      window.history.pushState({}, '', url);
      vincularPaginacionEmpleados();
    })
    .catch((error) => console.error('Error en la busqueda:', error));
};

/**
 * Vincula los clicks de paginacion para que usen AJAX
 * en lugar de recargar la pagina entera.
 */
const vincularPaginacionEmpleados = () => {
  if (!contenedorTablaEmpleados) return;
  const linksPaginacion = contenedorTablaEmpleados.querySelectorAll('.paginacion-botones a');

  linksPaginacion.forEach((link) => {
    link.addEventListener('click', (e) => {
      e.preventDefault();
      buscarEmpleado(link.getAttribute('href'));
    });
  });
};

// Debounce de 300ms para no disparar una peticion por cada tecla
let timerBusquedaEmpleado;
if (inputBusquedaEmpleado) {
  inputBusquedaEmpleado.addEventListener('input', () => {
    clearTimeout(timerBusquedaEmpleado);
    timerBusquedaEmpleado = setTimeout(() => buscarEmpleado(), 300);
  });
}

// Vinculo la paginacion al cargar la pagina
vincularPaginacionEmpleados();
