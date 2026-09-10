/**
 * -----------------------------------------------------------------------------
 * MARCOS - RECEPCION, PROCESAMIENTO Y ENTREGA
 * Filtros y paginacion por AJAX, y paneles de alta / edicion / eliminacion.
 *
 * El estado aplicado de cada filtro vive fuera de la tabla que reemplaza el AJAX:
 *   - cliente -> data-* del chip .filtro-entidad (lo vuelca aplicarFiltrosEntidad).
 *   - estado  -> data-estado de la pildora #filtro-estado-marcos.
 *   - fecha   -> data-desde/data-hasta de #filtro-fechas.
 * Por eso los tres sobreviven a los refrescos y a "Anterior"/"Siguiente".
 * -----------------------------------------------------------------------------
 */

const contenedorTabla = document.getElementById('tabla-marcos-container');
const filtroFechas = document.getElementById('filtro-fechas');
const filtroEstado = document.getElementById('filtro-estado-marcos');

/** Vuelca el rango de fechas aplicado (data-* del chip) en la URL. */
const aplicarFechas = (url) => {
  const desde = filtroFechas ? filtroFechas.dataset.desde : '';
  const hasta = filtroFechas ? filtroFechas.dataset.hasta : '';
  if (desde) url.searchParams.set('desde', desde); else url.searchParams.delete('desde');
  if (hasta) url.searchParams.set('hasta', hasta); else url.searchParams.delete('hasta');
};

/** Vuelca el estado elegido en la pildora. Vacio = todos los estados. */
const aplicarEstado = (url) => {
  const estado = filtroEstado ? filtroEstado.dataset.estado : '';
  if (estado) url.searchParams.set('estado', estado); else url.searchParams.delete('estado');
};

/**
 * Refresca la tabla con los filtros aplicados, sin recargar la pagina.
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

  if (typeof aplicarFiltrosEntidad === 'function') aplicarFiltrosEntidad(url);
  aplicarEstado(url);
  aplicarFechas(url);

  fetch(url, { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
    .then((respuesta) => respuesta.text())
    .then((html) => {
      contenedorTabla.innerHTML = html;
      window.history.pushState({}, '', url);
      vincularPaginacion();
    })
    .catch((error) => console.error('Error al filtrar los marcos:', error));
};

/** Hace que los enlaces de paginacion funcionen por AJAX. */
const vincularPaginacion = () => {
  if (!contenedorTabla) return;
  contenedorTabla.querySelectorAll('.paginacion-botones a').forEach((enlace) => {
    enlace.addEventListener('click', (e) => {
      e.preventDefault();
      buscar(enlace.href);
    });
  });
};

// Los tres filtros avisan por evento; cada uno recarga la tabla.
document.addEventListener('filtroentidad:cambio', () => buscar());
document.addEventListener('filtroestado:cambio', () => buscar());
document.addEventListener('filtrofechas:cambio', () => buscar());

vincularPaginacion();

/**
 * -----------------------------------------------------------------------------
 * PANELES (NUEVA / EDITAR)
 * -----------------------------------------------------------------------------
 */

const panel = document.getElementById('slide-over-panel');
const formulario = document.getElementById('form-marco');

/** Textos de la cabecera y del boton segun se este dando de alta o editando. */
const rotularPanel = (titulo, bajada, boton) => {
  if (!panel) return;
  panel.querySelector('.texto-cabecera h3').innerText = titulo;
  panel.querySelector('.texto-cabecera p').innerText = bajada;
  panel.querySelector('.boton-primario').innerText = boton;
};

const prepararPanelNuevoMarco = () => {
  rotularPanel('Nueva operación', 'Registrá los marcos que entran al galpón', 'Guardar operación');

  if (formulario) formulario.reset();
  document.getElementById('id_marco').value = '';
  document.getElementById('id_cliente_marco').value = '';

  // El reset devuelve el value del HTML, que ya trae la fecha de hoy.
  if (typeof abrirSlideOver === 'function') abrirSlideOver();
};

const prepararPanelEditarMarco = (id) => {
  fetch(`/api/marcos/${id}/`)
    .then((respuesta) => respuesta.json())
    .then((marco) => {
      rotularPanel('Editar operación', 'Modificá los datos de esta tanda de marcos', 'Actualizar operación');

      document.getElementById('id_marco').value = marco.id;
      document.getElementById('cliente-marco').value = marco.cliente;
      document.getElementById('id_cliente_marco').value = marco.id_cliente;
      document.getElementById('cantidad-marco').value = marco.cantidad;
      document.getElementById('estado-marco').value = marco.estado;
      document.getElementById('fecha-recepcion-marco').value = marco.fecha_recepcion;
      document.getElementById('fecha-entrega-marco').value = marco.fecha_entrega;

      if (typeof abrirSlideOver === 'function') abrirSlideOver();
    })
    .catch((error) => {
      console.error(error);
      if (typeof abrirModalError === 'function') {
        abrirModalError('No se pudieron cargar los datos de la operación de marcos.');
      }
    });
};

/**
 * -----------------------------------------------------------------------------
 * DELEGACION DE EVENTOS (TABLA)
 * La tabla se reemplaza entera en cada refresco AJAX, asi que los botones de cada
 * fila se escuchan desde document y no uno por uno.
 * -----------------------------------------------------------------------------
 */
document.addEventListener('click', (e) => {
  const botonEditar = e.target.closest('.boton-icono.editar');
  if (botonEditar) {
    prepararPanelEditarMarco(botonEditar.dataset.id);
    return;
  }

  const botonEliminar = e.target.closest('.boton-icono.eliminar');
  if (botonEliminar) {
    const { id, cliente, cantidad } = botonEliminar.dataset;

    document.getElementById('id_eliminar').value = id;
    document.getElementById('texto-confirmacion-eliminar').innerHTML =
      `¿Querés eliminar los <b>${cantidad}</b> marcos de <b>${cliente}</b>?`;

    if (typeof abrirPanelEliminar === 'function') abrirPanelEliminar();
  }
});

// Accesible desde el onclick del HTML
window.prepararPanelNuevoMarco = prepararPanelNuevoMarco;
