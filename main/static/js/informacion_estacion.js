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
      const inputMonto = document.getElementById('monto');
      const inputLitros = document.getElementById('litros');
      if (typeof ponerValorMiles === 'function') {
        ponerValorMiles(inputMonto, carga.monto);
        ponerValorMiles(inputLitros, carga.litros);
      } else {
        inputMonto.value = carga.monto;
        inputLitros.value = carga.litros || '';
      }
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
});

/**
 * -----------------------------------------------------------------------------
 * CLIC EN UNA FILA DE CARGA
 * Si la carga nacio en un viaje (tiene data-viaje-url) la fila lleva a ese viaje.
 * Si es una carga manual, abre un modal centrado con la fecha y los litros. Los
 * datos viajan en los data- de la fila.
 * -----------------------------------------------------------------------------
 */
const activarFila = (fila) => {
  const urlViaje = fila.dataset.viajeUrl;
  if (urlViaje) {
    window.location.href = urlViaje;
    return;
  }
  abrirModalCarga(fila);
};

const abrirModalCarga = (fila) => {
  const litros = fila.dataset.litros?.trim();
  const dd = document.getElementById('modal-carga-litros');

  document.getElementById('modal-carga-fecha').innerText = fila.dataset.fecha || '—';
  if (litros) {
    dd.innerText = litros;
    dd.classList.remove('modal-carga__vacio');
  } else {
    dd.innerText = 'Sin litros cargados';
    dd.classList.add('modal-carga__vacio');
  }

  document.getElementById('contenedor-modal-carga').classList.add('abierto');
  document.body.style.overflow = 'hidden';
};

const cerrarModalCarga = () => {
  document.getElementById('contenedor-modal-carga').classList.remove('abierto');
  document.body.style.overflow = 'auto';
};

// Clic en la fila: la activa, salvo que el clic haya sido sobre un control propio
// (casilla de pago, botones de editar/eliminar). Asi la fila no roba esos clics.
document.addEventListener('click', (e) => {
  const fila = e.target.closest('.carga-fila');
  if (fila && !e.target.closest('input, button, a, label')) {
    activarFila(fila);
  }
});

// Teclado: Enter o barra espaciadora sobre la fila enfocada la activan; Escape
// cierra el modal.
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    cerrarModalCarga();
    return;
  }
  const fila = e.target.closest?.('.carga-fila');
  if (fila && (e.key === 'Enter' || e.key === ' ')) {
    e.preventDefault();
    activarFila(fila);
  }
});

// El check de pago alterna el estado de la carga. Uso 'change' para que tambien
// funcione con teclado (barra espaciadora), no solo con click.
document.addEventListener('change', (e) => {
  const check = e.target.closest('.toggle-pago');
  if (check) {
    document.getElementById('id_toggle').value = check.dataset.id;
    document.getElementById('form-toggle-pago').submit();
  }
});

// El filtro de fechas es agnostico: dispara 'filtrofechas:cambio' y aca lo
// traducimos a una recarga server-side, conservando el estado de pago elegido y
// volviendo a la primera pagina. El estado ya viaja en la URL actual.
document.addEventListener('filtrofechas:cambio', () => {
  const cont = document.getElementById('filtro-fechas');
  if (!cont) return;
  const params = new URLSearchParams(window.location.search);
  if (cont.dataset.desde) params.set('desde', cont.dataset.desde);
  else params.delete('desde');
  if (cont.dataset.hasta) params.set('hasta', cont.dataset.hasta);
  else params.delete('hasta');
  params.delete('page');
  window.location.search = params.toString();
});

// Accesibles desde los onclick del HTML
window.prepararPanelNuevaCarga = prepararPanelNuevaCarga;
window.prepararEditarEstacion = prepararEditarEstacion;
window.prepararEliminarEstacion = prepararEliminarEstacion;
window.cerrarModalCarga = cerrarModalCarga;
