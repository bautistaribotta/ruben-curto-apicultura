/**
 * -----------------------------------------------------------------------------
 * INFORMACION EMPRESA / SOCIEDAD (IVA)
 * Alta/edicion/eliminacion de operaciones y edicion/baja de la empresa.
 * Reutiliza abrirSlideOver / cerrarSlideOver / abrirPanelEliminar de paneles.js
 * y leerMiles / ponerValorMiles de formato_miles.js.
 * -----------------------------------------------------------------------------
 */

const hoyISO = () => new Date().toISOString().split('T')[0];

/**
 * IVA calculado en vivo (monto neto x alicuota), para controlar antes de guardar.
 */
const calcularPreviewIva = () => {
  const inputMonto = document.getElementById('monto_neto');
  const selectAlicuota = document.getElementById('alicuota');
  const salida = document.getElementById('preview-iva-valor');
  if (!inputMonto || !selectAlicuota || !salida) return;

  const neto = parseFloat(typeof leerMiles === 'function' ? leerMiles(inputMonto) : inputMonto.value) || 0;
  const alicuota = parseFloat(selectAlicuota.value) || 0;
  const iva = neto * alicuota / 100;

  salida.textContent = '$' + iva.toLocaleString('es-AR', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
};

/**
 * Abre el panel para cargar una nueva operacion.
 */
const prepararNuevaOperacion = () => {
  document.querySelector('#slide-over-panel h3').innerText = 'Nueva operación';
  document.querySelector('#slide-over-panel .texto-cabecera p').innerText = 'Registra una venta o una compra';
  document.getElementById('boton-guardar-operacion').innerText = 'Guardar operación';

  const form = document.getElementById('form-operacion');
  form.reset();
  document.getElementById('accion-operacion').value = 'nueva_operacion';
  document.getElementById('id_registro').value = '';
  document.getElementById('fecha').value = hoyISO();
  // Venta es el default del alta
  const radioVenta = document.querySelector('input[name="tipo"][value="venta"]');
  if (radioVenta) radioVenta.checked = true;
  calcularPreviewIva();

  if (typeof abrirSlideOver === 'function') abrirSlideOver();
};

/**
 * Abre el panel de edicion precargado con los datos de una operacion.
 * @param {string} id - id de la operacion.
 */
const prepararEditarOperacion = (id) => {
  fetch(`/api/operaciones_iva/${id}/`)
    .then((response) => response.json())
    .then((operacion) => {
      document.querySelector('#slide-over-panel h3').innerText = 'Editar operación';
      document.querySelector('#slide-over-panel .texto-cabecera p').innerText = 'Modifica los datos de la operación';
      document.getElementById('boton-guardar-operacion').innerText = 'Actualizar operación';

      document.getElementById('accion-operacion').value = 'editar_operacion';
      document.getElementById('id_registro').value = operacion.id;

      const radioTipo = document.querySelector(`input[name="tipo"][value="${operacion.tipo}"]`);
      if (radioTipo) radioTipo.checked = true;

      document.getElementById('fecha').value = operacion.fecha;
      document.getElementById('alicuota').value = operacion.alicuota;
      document.getElementById('detalle').value = operacion.detalle || '';

      const inputMonto = document.getElementById('monto_neto');
      if (typeof ponerValorMiles === 'function') {
        ponerValorMiles(inputMonto, operacion.monto_neto);
      } else {
        inputMonto.value = operacion.monto_neto;
      }
      calcularPreviewIva();

      if (typeof abrirSlideOver === 'function') abrirSlideOver();
    })
    .catch((error) => {
      console.error(error);
      if (typeof abrirModalError === 'function') {
        abrirModalError('Error al cargar los datos de la operación');
      }
    });
};

/**
 * -----------------------------------------------------------------------------
 * ACCIONES SOBRE LA EMPRESA (editar nombre / eliminar)
 * -----------------------------------------------------------------------------
 */
const prepararEditarEmpresa = () => {
  const boton = document.querySelector('.boton-accion.boton-editar');
  document.getElementById('nombre-empresa').value = boton.dataset.nombre || '';
  if (typeof abrirSlideOver === 'function') abrirSlideOver('contenedor-slide-over-empresa');
};

const prepararEliminarEmpresa = () => {
  // El mismo modal sirve para operaciones y empresa: solo cambia la accion y el
  // texto. La empresa sale del id de la URL, asi que no hace falta id_registro.
  document.getElementById('accion-eliminar').value = 'eliminar_empresa';
  document.getElementById('id_registro_eliminar').value = '';
  document.getElementById('texto-confirmacion-eliminar').innerHTML =
    'Se dará de baja la empresa y no aparecerá más en el listado. ¿Confirma?';
  if (typeof abrirPanelEliminar === 'function') abrirPanelEliminar();
};

/**
 * -----------------------------------------------------------------------------
 * DELEGACION DE EVENTOS (TABLA) + PREVIEW EN VIVO
 * -----------------------------------------------------------------------------
 */
document.addEventListener('click', (e) => {
  const botonEditar = e.target.closest('.boton-icono.editar');
  const botonEliminar = e.target.closest('.boton-icono.eliminar');

  if (botonEditar) {
    prepararEditarOperacion(botonEditar.dataset.id);
  }

  if (botonEliminar) {
    document.getElementById('accion-eliminar').value = 'eliminar_operacion';
    document.getElementById('id_registro_eliminar').value = botonEliminar.dataset.id;
    document.getElementById('texto-confirmacion-eliminar').innerHTML =
      `¿Confirma que quiere eliminar <b>${botonEliminar.dataset.descripcion}</b>?`;
    if (typeof abrirPanelEliminar === 'function') abrirPanelEliminar();
  }
});

// El IVA se recalcula al cambiar el monto o la alicuota
document.getElementById('monto_neto')?.addEventListener('input', calcularPreviewIva);
document.getElementById('alicuota')?.addEventListener('change', calcularPreviewIva);

// Accesibles desde los onclick del HTML
window.prepararNuevaOperacion = prepararNuevaOperacion;
window.prepararEditarEmpresa = prepararEditarEmpresa;
window.prepararEliminarEmpresa = prepararEliminarEmpresa;
