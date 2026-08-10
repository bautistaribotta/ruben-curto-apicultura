/**
 * -----------------------------------------------------------------------------
 * COMBUSTIBLE - ESTACIONES DE SERVICIO
 * Busqueda AJAX, paginacion y paneles de alta/edicion/eliminacion.
 * -----------------------------------------------------------------------------
 */

const inputBusqueda = document.getElementById('buscar-estacion');
const contenedorTabla = document.getElementById('tabla-estaciones-container');

/**
 * Busca estaciones por AJAX sin recargar la pagina.
 * @param {string|null} urlString - URL opcional (ej: para paginacion).
 */
const buscar = (urlString = null) => {
  if (!inputBusqueda || !contenedorTabla) return;

  let url;
  if (urlString) {
    url = new URL(urlString, window.location.origin);
  } else {
    url = new URL(window.location.href);
    url.searchParams.set('q', inputBusqueda.value);
    url.searchParams.delete('page');
  }

  fetch(url, { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
    .then((response) => response.text())
    .then((html) => {
      contenedorTabla.innerHTML = html;
      window.history.pushState({}, '', url);
      vincularPaginacion();
    })
    .catch((error) => console.error('Error en la busqueda:', error));
};

/**
 * Hace que los enlaces de paginacion funcionen por AJAX.
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

if (inputBusqueda) inputBusqueda.addEventListener('input', () => buscar());
vincularPaginacion();

/**
 * -----------------------------------------------------------------------------
 * PANELES (NUEVA / EDITAR)
 * -----------------------------------------------------------------------------
 */

const prepararPanelNuevaEstacion = () => {
  document.querySelector('#slide-over-panel h3').innerText = 'Nueva estacion';
  document.querySelector('#slide-over-panel .texto-cabecera p').innerText = 'Registra una estacion de servicio';
  document.querySelector('.boton-primario').innerText = 'Guardar estacion';

  document.getElementById('form-estacion').reset();
  document.getElementById('id_estacion').value = '';

  if (typeof abrirSlideOver === 'function') abrirSlideOver();
};

const prepararPanelEditarEstacion = (id) => {
  fetch(`/api/estaciones/${id}/`)
    .then((response) => response.json())
    .then((estacion) => {
      document.querySelector('#slide-over-panel h3').innerText = 'Editar estacion';
      document.querySelector('#slide-over-panel .texto-cabecera p').innerText = 'Modifica los datos de la estacion';
      document.querySelector('.boton-primario').innerText = 'Actualizar estacion';

      document.getElementById('id_estacion').value = estacion.id;
      document.getElementById('nombre').value = estacion.nombre;

      if (typeof abrirSlideOver === 'function') abrirSlideOver();
    })
    .catch((error) => {
      console.error(error);
      if (typeof abrirModalError === 'function') {
        abrirModalError('Error al cargar los datos de la estacion');
      }
    });
};

/**
 * -----------------------------------------------------------------------------
 * DELEGACION DE EVENTOS (TABLA)
 * -----------------------------------------------------------------------------
 */
document.addEventListener('click', (e) => {
  const botonEditar = e.target.closest('.boton-icono.editar');
  const botonEliminar = e.target.closest('.boton-icono.eliminar');

  // Fila clickeable: navega a la ficha salvo que se toque un boton de accion
  const fila = e.target.closest('.fila-estacion');
  if (fila && !botonEditar && !botonEliminar && fila.dataset.href) {
    window.location.href = fila.dataset.href;
    return;
  }

  if (botonEditar) {
    prepararPanelEditarEstacion(botonEditar.dataset.id);
  }

  if (botonEliminar) {
    const id = botonEliminar.dataset.id;
    const nombre = botonEliminar.dataset.nombre;

    document.getElementById('id_eliminar').value = id;
    document.getElementById('texto-confirmacion-eliminar').innerHTML =
      `¿Confirma que quiere eliminar la estacion <b>${nombre}</b>?`;

    if (typeof abrirPanelEliminar === 'function') abrirPanelEliminar();
  }
});

// Autocapitalizar la primera letra del nombre al escribir
const inputNombreEstacion = document.getElementById('nombre');
if (inputNombreEstacion) {
  inputNombreEstacion.addEventListener('input', (e) => {
    const valor = e.target.value;
    if (valor.length > 0) {
      e.target.value = valor.charAt(0).toUpperCase() + valor.slice(1);
    }
  });
}

// Accesible desde el onclick del HTML
window.prepararPanelNuevaEstacion = prepararPanelNuevaEstacion;
