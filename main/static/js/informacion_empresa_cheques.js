/**
 * -----------------------------------------------------------------------------
 * INFORMACION EMPRESA / SOCIEDAD (CHEQUES)
 * Alta/edicion/eliminacion de cheques y de cuentas corrientes.
 * Reutiliza abrirSlideOver / cerrarSlideOver / abrirPanelEliminar de paneles.js
 * y leerMiles / ponerValorMiles de formato_miles.js.
 *
 * El cheque vive en el slide-over principal (#contenedor-slide-over); la cuenta
 * corriente en el segundo (#contenedor-slide-over-cuenta). El banco de un cheque
 * solo filtra, del lado del cliente, las cuentas corrientes de la empresa: no se
 * envia al servidor (el cheque se ata a la cuenta, que ya lleva su banco).
 * -----------------------------------------------------------------------------
 */

const DIAS_VENCIMIENTO_CHEQUE = 30;

const hoyISO = () => {
  const hoy = new Date();
  const mes = String(hoy.getMonth() + 1).padStart(2, '0');
  const dia = String(hoy.getDate()).padStart(2, '0');
  return `${hoy.getFullYear()}-${mes}-${dia}`;
};

// Suma dias a una fecha ISO (yyyy-mm-dd) trabajando en hora local, sin arrastrar
// desfasajes de zona horaria que corran el dia.
const sumarDias = (iso, dias) => {
  if (!iso) return '';
  const [anio, mes, dia] = iso.split('-').map(Number);
  const fecha = new Date(anio, mes - 1, dia);
  fecha.setDate(fecha.getDate() + Number(dias));
  const m = String(fecha.getMonth() + 1).padStart(2, '0');
  const d = String(fecha.getDate()).padStart(2, '0');
  return `${fecha.getFullYear()}-${m}-${d}`;
};

const diasEntre = (isoDesde, isoHasta) => {
  if (!isoDesde || !isoHasta) return null;
  const [ay, am, ad] = isoDesde.split('-').map(Number);
  const [by, bm, bd] = isoHasta.split('-').map(Number);
  const a = new Date(ay, am - 1, ad);
  const b = new Date(by, bm - 1, bd);
  return Math.round((b - a) / 86400000);
};

const formatearFechaISO = (iso) => {
  if (!iso) return '—';
  const [anio, mes, dia] = iso.split('-');
  return `${dia}/${mes}/${anio}`;
};

// Catalogo de cuentas corrientes de la empresa, tomado una sola vez del DOM: de
// aca se arman el select de banco y el de cuenta, sin pegarle al servidor.
const selectCuentaCheque = document.getElementById('cheque-cuenta');
const cuentasData = selectCuentaCheque
  ? Array.from(selectCuentaCheque.options).map((opcion) => ({
      value: opcion.value,
      banco: opcion.dataset.banco,
      bancoNombre: opcion.dataset.bancoNombre,
      label: opcion.textContent,
    }))
  : [];

/** Arma el select de banco con los bancos distintos de las cuentas de la empresa. */
const construirBancosCheque = () => {
  const selectBanco = document.getElementById('cheque-banco');
  if (!selectBanco) return;

  const vistos = new Set();
  selectBanco.innerHTML = '';
  cuentasData.forEach((cuenta) => {
    if (vistos.has(cuenta.banco)) return;
    vistos.add(cuenta.banco);
    const opcion = document.createElement('option');
    opcion.value = cuenta.banco;
    opcion.textContent = cuenta.bancoNombre;
    selectBanco.appendChild(opcion);
  });
};

/** Repuebla el select de cuenta con las cuentas del banco elegido. */
const filtrarCuentasPorBanco = (bancoId, cuentaSeleccionada = null) => {
  if (!selectCuentaCheque) return;
  selectCuentaCheque.innerHTML = '';
  cuentasData
    .filter((cuenta) => cuenta.banco === String(bancoId))
    .forEach((cuenta) => {
      const opcion = document.createElement('option');
      opcion.value = cuenta.value;
      opcion.dataset.banco = cuenta.banco;
      opcion.dataset.bancoNombre = cuenta.bancoNombre;
      opcion.textContent = cuenta.label;
      selectCuentaCheque.appendChild(opcion);
    });
  if (cuentaSeleccionada) selectCuentaCheque.value = cuentaSeleccionada;
};

/** Vencimiento en vivo: 30 dias despues de la fecha de cobro. */
const actualizarVencimiento = () => {
  const cobro = document.getElementById('cheque-fecha-cobro');
  const salida = document.getElementById('preview-vencimiento-valor');
  if (!cobro || !salida) return;
  salida.textContent = cobro.value
    ? formatearFechaISO(sumarDias(cobro.value, DIAS_VENCIMIENTO_CHEQUE))
    : '—';
};

/** Aplica el plazo (30/60/90) sobre la fecha de emision para calcular la de cobro. */
const aplicarPlazoCheque = () => {
  const plazo = document.getElementById('cheque-plazo');
  const emision = document.getElementById('cheque-fecha-emision');
  const cobro = document.getElementById('cheque-fecha-cobro');
  if (!plazo || !emision || !cobro) return;
  if (plazo.value !== 'otra' && emision.value) {
    cobro.value = sumarDias(emision.value, plazo.value);
  }
  actualizarVencimiento();
};

const actualizarContadorConcepto = () => {
  const concepto = document.getElementById('cheque-concepto');
  const conteo = document.getElementById('cheque-concepto-conteo');
  if (concepto && conteo) conteo.textContent = concepto.value.length;
};

/**
 * Aviso cuando la empresa todavia no tiene cuentas corrientes: un cheque cuelga
 * de una cuenta, asi que sin cuentas no se puede cargar. En vez de un boton
 * deshabilitado (que no explica el porque), el boton queda activo y este modal
 * guia a crear la cuenta primero.
 */
const abrirModalSinCuenta = () => {
  document.getElementById('contenedor-modal-aviso').classList.add('abierto');
  document.body.style.overflow = 'hidden';
};

const cerrarModalSinCuenta = () => {
  document.getElementById('contenedor-modal-aviso').classList.remove('abierto');
  document.body.style.overflow = 'auto';
};

/** Desde el aviso, encadena a la creacion de la cuenta corriente. */
const crearCuentaDesdeAviso = () => {
  cerrarModalSinCuenta();
  prepararNuevaCuenta();
};

/** Abre el panel para cargar un nuevo cheque. */
const prepararNuevoCheque = () => {
  // Sin cuentas corrientes no hay de donde colgar el cheque: aviso y freno aca.
  if (!cuentasData.length) {
    abrirModalSinCuenta();
    return;
  }

  document.getElementById('titulo-cheque').textContent = 'Nuevo cheque';
  document.getElementById('subtitulo-cheque').textContent = 'Registra un cheque a pagar';
  document.getElementById('boton-guardar-cheque').textContent = 'Guardar cheque';

  const form = document.getElementById('form-cheque');
  if (form) form.reset();
  document.getElementById('accion-cheque').value = 'nuevo_cheque';
  document.getElementById('id-registro-cheque').value = '';

  construirBancosCheque();
  const selectBanco = document.getElementById('cheque-banco');
  if (selectBanco && selectBanco.options.length) {
    filtrarCuentasPorBanco(selectBanco.value);
  }

  document.getElementById('cheque-fecha-emision').value = hoyISO();
  document.getElementById('cheque-plazo').value = '30';
  aplicarPlazoCheque();
  actualizarContadorConcepto();

  if (typeof abrirSlideOver === 'function') abrirSlideOver();
};

/** Abre el panel de edicion precargado con los datos de un cheque. */
const prepararEditarCheque = (id) => {
  fetch(`/api/cheques/${id}/`)
    .then((response) => response.json())
    .then((cheque) => {
      document.getElementById('titulo-cheque').textContent = 'Editar cheque';
      document.getElementById('subtitulo-cheque').textContent = 'Modifica los datos del cheque';
      document.getElementById('boton-guardar-cheque').textContent = 'Actualizar cheque';

      document.getElementById('accion-cheque').value = 'editar_cheque';
      document.getElementById('id-registro-cheque').value = cheque.id;
      document.getElementById('cheque-numero').value = cheque.numero || '';

      construirBancosCheque();
      const selectBanco = document.getElementById('cheque-banco');
      if (selectBanco) selectBanco.value = cheque.id_banco;
      filtrarCuentasPorBanco(cheque.id_banco, cheque.id_cuenta_corriente);

      document.getElementById('cheque-fecha-emision').value = cheque.fecha_emision;
      document.getElementById('cheque-fecha-cobro').value = cheque.fecha_cobro;

      // Si el plazo coincide con 30/60/90 lo reflejo; si no, "Otra fecha".
      const dias = diasEntre(cheque.fecha_emision, cheque.fecha_cobro);
      document.getElementById('cheque-plazo').value = [30, 60, 90].includes(dias) ? String(dias) : 'otra';

      document.getElementById('cheque-concepto').value = cheque.concepto || '';
      actualizarContadorConcepto();

      const inputImporte = document.getElementById('cheque-importe');
      if (typeof ponerValorMiles === 'function') {
        ponerValorMiles(inputImporte, cheque.importe);
      } else {
        inputImporte.value = cheque.importe;
      }

      actualizarVencimiento();

      if (typeof abrirSlideOver === 'function') abrirSlideOver();
    })
    .catch((error) => {
      console.error(error);
      if (typeof abrirModalError === 'function') {
        abrirModalError('Error al cargar los datos del cheque');
      }
    });
};

/**
 * -----------------------------------------------------------------------------
 * CUENTAS CORRIENTES (segundo slide-over)
 * -----------------------------------------------------------------------------
 */
const prepararNuevaCuenta = () => {
  document.getElementById('titulo-cuenta').textContent = 'Nueva cuenta corriente';
  document.getElementById('subtitulo-cuenta').textContent = 'Registra una cuenta en un banco';
  document.getElementById('boton-guardar-cuenta').textContent = 'Guardar cuenta';

  const form = document.getElementById('form-cuenta');
  if (form) form.reset();
  document.getElementById('accion-cuenta').value = 'nueva_cuenta';
  document.getElementById('id-registro-cuenta').value = '';

  if (typeof abrirSlideOver === 'function') abrirSlideOver('contenedor-slide-over-cuenta');
};

const prepararEditarCuenta = (boton) => {
  document.getElementById('titulo-cuenta').textContent = 'Editar cuenta corriente';
  document.getElementById('subtitulo-cuenta').textContent = 'Modifica los datos de la cuenta';
  document.getElementById('boton-guardar-cuenta').textContent = 'Actualizar cuenta';

  document.getElementById('accion-cuenta').value = 'editar_cuenta';
  document.getElementById('id-registro-cuenta').value = boton.dataset.id;
  document.getElementById('cuenta-banco').value = boton.dataset.banco;
  document.getElementById('cuenta-numero').value = boton.dataset.numero || '';

  if (typeof abrirSlideOver === 'function') abrirSlideOver('contenedor-slide-over-cuenta');
};

const prepararEliminarCuenta = (boton) => {
  document.getElementById('accion-eliminar').value = 'eliminar_cuenta';
  document.getElementById('id_registro_eliminar').value = boton.dataset.id;
  document.getElementById('texto-confirmacion-eliminar').innerHTML =
    `¿Confirma que quiere eliminar <b>${boton.dataset.descripcion}</b>? ` +
    'Sus cheques dejarán de contar en el total a pagar.';
  if (typeof abrirPanelEliminar === 'function') abrirPanelEliminar();
};

/**
 * -----------------------------------------------------------------------------
 * ACCIONES SOBRE LA EMPRESA (editar nombre / eliminar)
 * La empresa es la misma entidad que en IVA: la baja logica la oculta de ambas
 * secciones, asi que el aviso lo dice para que no sorprenda.
 * -----------------------------------------------------------------------------
 */
const prepararEditarEmpresa = () => {
  const boton = document.querySelector('.boton-accion.boton-editar');
  document.getElementById('nombre-empresa').value = boton.dataset.nombre || '';
  if (typeof abrirSlideOver === 'function') abrirSlideOver('contenedor-slide-over-empresa');
};

const prepararEliminarEmpresa = () => {
  // El mismo modal sirve para cheques, cuentas y empresa: solo cambia la accion
  // y el texto. La empresa sale del id de la URL, asi que no hace falta id_registro.
  document.getElementById('accion-eliminar').value = 'eliminar_empresa';
  document.getElementById('id_registro_eliminar').value = '';
  document.getElementById('texto-confirmacion-eliminar').innerHTML =
    'Se dará de baja la empresa y dejará de aparecer tanto en Cheques como en IVA. ' +
    'Se conservan sus cheques y operaciones. ¿Confirma?';
  if (typeof abrirPanelEliminar === 'function') abrirPanelEliminar();
};

const prepararEliminarCheque = (boton) => {
  document.getElementById('accion-eliminar').value = 'eliminar_cheque';
  document.getElementById('id_registro_eliminar').value = boton.dataset.id;
  document.getElementById('texto-confirmacion-eliminar').innerHTML =
    `¿Confirma que quiere eliminar <b>${boton.dataset.descripcion}</b>?`;
  if (typeof abrirPanelEliminar === 'function') abrirPanelEliminar();
};

/**
 * -----------------------------------------------------------------------------
 * MODAL DE DETALLE DEL CHEQUE
 * La tabla muestra solo lo justo (cobrado, numero, cuenta, cobro, importe); toda
 * la info del cheque vive aca, y desde aca se edita o elimina. Los datos vienen
 * del mismo endpoint que la edicion (/api/cheques/<id>/), ya con los campos
 * formateados para mostrar.
 * -----------------------------------------------------------------------------
 */
let chequeDetalleActual = null;

/** Pone la pildora de estado (cobrado gana sobre vencido gana sobre pendiente). */
const pintarEstadoCheque = (cobrado, vencido) => {
  const pill = document.getElementById('det-cheque-estado');
  pill.classList.remove('det-cheque__estado--cobrado', 'det-cheque__estado--vencido',
    'det-cheque__estado--pendiente');
  if (cobrado) {
    pill.textContent = 'Cobrado';
    pill.classList.add('det-cheque__estado--cobrado');
  } else if (vencido) {
    pill.textContent = 'Vencido';
    pill.classList.add('det-cheque__estado--vencido');
  } else {
    pill.textContent = 'Pendiente';
    pill.classList.add('det-cheque__estado--pendiente');
  }
};

const abrirDetalleCheque = (id) => {
  fetch(`/api/cheques/${id}/`)
    .then((response) => response.json())
    .then((cheque) => {
      chequeDetalleActual = cheque;
      document.getElementById('det-cheque-titulo').textContent = cheque.numero
        ? `Cheque N.º ${cheque.numero}`
        : 'Cheque sin número';
      pintarEstadoCheque(cheque.cobrado, cheque.vencido);
      document.getElementById('det-cheque-importe').textContent = `$${cheque.importe_txt}`;
      document.getElementById('det-cheque-cuenta').textContent =
        `${cheque.banco_nombre} · N.º ${cheque.cuenta_numero}`;
      document.getElementById('det-cheque-emision').textContent = cheque.fecha_emision_txt;
      document.getElementById('det-cheque-cobro').textContent = cheque.fecha_cobro_txt;
      document.getElementById('det-cheque-vencimiento').textContent = cheque.vencimiento_txt;
      document.getElementById('det-cheque-concepto').textContent = cheque.concepto || '—';

      document.getElementById('contenedor-modal-cheque').classList.add('abierto');
      document.body.style.overflow = 'hidden';
    })
    .catch((error) => {
      console.error(error);
      if (typeof abrirModalError === 'function') {
        abrirModalError('Error al cargar el detalle del cheque');
      }
    });
};

const cerrarDetalleCheque = () => {
  document.getElementById('contenedor-modal-cheque').classList.remove('abierto');
  document.body.style.overflow = 'auto';
};

// Editar desde el detalle: cierro el detalle y abro el slide-over de edicion, que
// vuelve a pedir el cheque al servidor (mismo id).
document.getElementById('det-cheque-editar')?.addEventListener('click', () => {
  const id = chequeDetalleActual && chequeDetalleActual.id;
  cerrarDetalleCheque();
  if (id) prepararEditarCheque(id);
});

// Eliminar desde el detalle SIN modal de confirmacion: se mantiene apretado 2s y
// recien ahi se envia el borrado. Mismo gesto que #boton-confirmar-eliminar
// (paneles.js): al arrancar el hold cargo la accion y el id del cheque abierto en
// el formulario de eliminacion compartido, y al completarse lo envio. Soltar antes
// cancela. El texto pasa a "Mantenga presionado..." mientras se sostiene.
(() => {
  const boton = document.getElementById('det-cheque-eliminar');
  if (!boton) return;
  const texto = boton.querySelector('.det-cheque__eliminar-texto');
  const etiqueta = texto.textContent;
  let cuentaRegresiva;

  const arrancarBorrado = (evento) => {
    if (evento.type === 'mousedown' && evento.button !== 0) return;
    // En el celular, mantener apretado abre el menu del navegador si no lo freno
    if (evento.type === 'touchstart') evento.preventDefault();

    const cheque = chequeDetalleActual;
    if (!cheque) return;
    document.getElementById('accion-eliminar').value = 'eliminar_cheque';
    document.getElementById('id_registro_eliminar').value = cheque.id;

    boton.classList.add('manteniendo');
    texto.textContent = 'Mantenga presionado...';
    cuentaRegresiva = setTimeout(() => {
      document.getElementById('formulario-eliminar').submit();
    }, 2000);
  };

  const soltarBorrado = () => {
    clearTimeout(cuentaRegresiva);
    boton.classList.remove('manteniendo');
    texto.textContent = etiqueta;
  };

  boton.addEventListener('mousedown', arrancarBorrado);
  boton.addEventListener('mouseup', soltarBorrado);
  boton.addEventListener('mouseleave', soltarBorrado);
  boton.addEventListener('touchstart', arrancarBorrado, { passive: false });
  boton.addEventListener('touchend', soltarBorrado);
  boton.addEventListener('touchcancel', soltarBorrado);
})();

// Escape cierra el detalle (el resto de los modales tienen su propio manejo).
document.addEventListener('keydown', (evento) => {
  if (evento.key === 'Escape'
      && document.getElementById('contenedor-modal-cheque')?.classList.contains('abierto')) {
    cerrarDetalleCheque();
  }
});

/**
 * -----------------------------------------------------------------------------
 * CASILLA DE COBRADO (reusa pago_viaje.js para el fetch)
 * pago_viaje.js hace el POST y emite 'pago:cambiado'. Aca, solo para las casillas
 * de cheque (la respuesta trae total_empresa_txt), actualizo lo que depende del
 * cobro sin recargar: el estilo de la fila, el badge de la columna Cobro y los dos
 * totales (el de la empresa y el de la cuenta), que ya no cuentan el cobrado.
 * -----------------------------------------------------------------------------
 */
document.addEventListener('pago:cambiado', (evento) => {
  const { casilla, datos } = evento.detail;
  if (!casilla || datos.total_empresa_txt === undefined) return;

  const fila = casilla.closest('tr');
  if (fila) {
    fila.classList.toggle('cheque-fila--cobrado', Boolean(datos.cobrado));
    // Un cobrado no puede seguir mostrandose como vencido
    if (datos.cobrado) fila.classList.remove('cheque-fila--vencido');

    const celdaCobro = fila.querySelector('.cheque-cobro');
    if (celdaCobro) {
      const fechaHTML = celdaCobro.querySelector('.op-fecha').outerHTML;
      let sub;
      if (datos.cobrado) {
        sub = '<span class="cheque-badge cheque-badge--cobrado">Cobrado</span>';
      } else if (celdaCobro.dataset.vencido === '1') {
        sub = '<span class="cheque-badge cheque-badge--vencido">Vencido</span>';
        fila.classList.add('cheque-fila--vencido');
      } else {
        sub = `<span class="cheque-vence">Vence ${celdaCobro.dataset.vence}</span>`;
      }
      celdaCobro.innerHTML = fechaHTML + sub;
    }
  }

  const totalEmpresa = document.querySelector('.resumen-cheques__valor');
  if (totalEmpresa) totalEmpresa.textContent = `$${datos.total_empresa_txt}`;

  const celdaCuenta = document.querySelector(
    `.tabla-cuentas tr[data-cuenta="${datos.id_cuenta}"] .cuenta-a-pagar`);
  if (celdaCuenta) celdaCuenta.textContent = `$${datos.total_cuenta_txt}`;
});

/**
 * -----------------------------------------------------------------------------
 * LISTENERS DE LOS CAMPOS DEL FORMULARIO DE CHEQUE
 * -----------------------------------------------------------------------------
 */
document.getElementById('cheque-banco')?.addEventListener('change', (e) => {
  filtrarCuentasPorBanco(e.target.value);
});

document.getElementById('cheque-plazo')?.addEventListener('change', aplicarPlazoCheque);
document.getElementById('cheque-fecha-emision')?.addEventListener('change', aplicarPlazoCheque);

// Si el usuario edita la fecha de cobro a mano, el plazo pasa a "Otra fecha".
document.getElementById('cheque-fecha-cobro')?.addEventListener('input', () => {
  const plazo = document.getElementById('cheque-plazo');
  if (plazo) plazo.value = 'otra';
  actualizarVencimiento();
});

document.getElementById('cheque-concepto')?.addEventListener('input', actualizarContadorConcepto);

// El filtro de fechas es agnostico: dispara 'filtrofechas:cambio' y aca lo
// traducimos a una recarga server-side, volviendo a la primera pagina. El estado
// aplicado (desde/hasta) ya vive en los data-* del contenedor #filtro-fechas.
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
window.prepararNuevoCheque = prepararNuevoCheque;
window.prepararEditarCheque = prepararEditarCheque;
window.prepararNuevaCuenta = prepararNuevaCuenta;
window.prepararEditarCuenta = prepararEditarCuenta;
window.prepararEliminarCuenta = prepararEliminarCuenta;
window.prepararEliminarCheque = prepararEliminarCheque;
window.prepararEditarEmpresa = prepararEditarEmpresa;
window.prepararEliminarEmpresa = prepararEliminarEmpresa;
window.cerrarModalSinCuenta = cerrarModalSinCuenta;
window.crearCuentaDesdeAviso = crearCuentaDesdeAviso;
window.abrirDetalleCheque = abrirDetalleCheque;
window.cerrarDetalleCheque = cerrarDetalleCheque;
