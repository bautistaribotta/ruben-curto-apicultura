/**
 * -----------------------------------------------------------------------------
 * INFORMACION ESTACION DE SERVICIO
 * Alta/edicion/eliminacion de cargas de combustible y toggle de pagado.
 * Reutiliza abrirSlideOver / cerrarSlideOver / abrirPanelEliminar de paneles.js.
 * -----------------------------------------------------------------------------
 */

const hoyISO = () => new Date().toISOString().split('T')[0];

/**
 * Abre el panel para cargar una nueva carga de combustible.
 */
const prepararPanelNuevaCarga = () => {
  document.querySelector('#slide-over-panel h3').innerText = 'Nueva carga';
  document.querySelector('#slide-over-panel .texto-cabecera p').innerText = 'Registra una carga de combustible';
  document.querySelector('.boton-primario').innerText = 'Guardar carga';

  const form = document.getElementById('form-carga');
  form.reset();
  document.getElementById('accion-carga').value = 'nueva_carga';
  document.getElementById('id_registro').value = '';
  document.getElementById('fecha').value = hoyISO();

  if (typeof abrirSlideOver === 'function') abrirSlideOver();
};

/**
 * Abre el panel de edicion precargado con los datos de una carga.
 * @param {string} id - id de la carga.
 */
const prepararPanelEditarCarga = (id) => {
  fetch(`/api/cargas/${id}/`)
    .then((response) => response.json())
    .then((carga) => {
      document.querySelector('#slide-over-panel h3').innerText = 'Editar carga';
      document.querySelector('#slide-over-panel .texto-cabecera p').innerText = 'Modifica los datos de la carga';
      document.querySelector('.boton-primario').innerText = 'Actualizar carga';

      document.getElementById('accion-carga').value = 'editar_carga';
      document.getElementById('id_registro').value = carga.id;
      document.getElementById('empleado').value = carga.empleado;
      document.getElementById('vehiculo').value = carga.vehiculo;
      document.getElementById('fecha').value = carga.fecha;
      document.getElementById('monto').value = carga.monto;
      document.getElementById('observaciones').value = carga.observaciones || '';
      document.getElementById('pagada').checked = carga.pagada;

      if (typeof abrirSlideOver === 'function') abrirSlideOver();
    })
    .catch((error) => {
      console.error(error);
      if (typeof abrirModalError === 'function') {
        abrirModalError('Error al cargar los datos de la carga');
      }
    });
};

/**
 * -----------------------------------------------------------------------------
 * ACCIONES SOBRE LA ESTACION (editar nombre / eliminar)
 * -----------------------------------------------------------------------------
 */
const prepararEditarEstacion = () => {
  const boton = document.querySelector('.boton-accion.boton-editar');
  document.getElementById('nombre-estacion').value = boton.dataset.nombre || '';
  if (typeof abrirSlideOver === 'function') abrirSlideOver('contenedor-slide-over-estacion');
};

const prepararEliminarEstacion = () => {
  // El mismo modal sirve para cargas y estacion: solo cambia la accion y el texto.
  // La estacion sale del id de la URL, asi que no hace falta id_registro.
  document.getElementById('accion-eliminar').value = 'eliminar_estacion';
  document.getElementById('id_registro_eliminar').value = '';
  document.getElementById('texto-confirmacion-eliminar').innerHTML =
    'Se dara de baja la estacion y no aparecera mas en el listado. ¿Confirma?';
  if (typeof abrirPanelEliminar === 'function') abrirPanelEliminar();
};

/**
 * -----------------------------------------------------------------------------
 * DELEGACION DE EVENTOS (TABLA)
 * -----------------------------------------------------------------------------
 */
document.addEventListener('click', (e) => {
  const botonEditar = e.target.closest('.boton-icono.editar');
  const botonEliminar = e.target.closest('.boton-icono.eliminar');
  const botonToggle = e.target.closest('.toggle-pago');

  if (botonEditar) {
    prepararPanelEditarCarga(botonEditar.dataset.id);
  }

  if (botonEliminar) {
    document.getElementById('accion-eliminar').value = 'eliminar_carga';
    document.getElementById('id_registro_eliminar').value = botonEliminar.dataset.id;
    document.getElementById('texto-confirmacion-eliminar').innerHTML =
      `¿Confirma que quiere eliminar <b>${botonEliminar.dataset.descripcion}</b>?`;
    if (typeof abrirPanelEliminar === 'function') abrirPanelEliminar();
  }

  if (botonToggle) {
    document.getElementById('id_toggle').value = botonToggle.dataset.id;
    document.getElementById('form-toggle-pago').submit();
  }
});

// Accesibles desde los onclick del HTML
window.prepararPanelNuevaCarga = prepararPanelNuevaCarga;
window.prepararEditarEstacion = prepararEditarEstacion;
window.prepararEliminarEstacion = prepararEliminarEstacion;
