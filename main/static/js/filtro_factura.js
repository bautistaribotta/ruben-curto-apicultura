/**
 * -----------------------------------------------------------------------------
 * FILTRO POR NUMERO DE FACTURA (pildora -> modal con input de texto)
 * A diferencia de los chips de entidad (que eligen de una lista), la factura es
 * texto libre: la pildora abre un modal donde se tipea el numero. El estado
 * aplicado vive en data-valor del chip, fuera de la region que reemplaza el AJAX,
 * asi sobrevive a los refrescos.
 *
 * Al aplicar o limpiar dispara 'filtrofactura:cambio' sobre document (mismo patron
 * que filtro_fechas.js / filtros_entidad.js); la vista lo engancha a su busqueda.
 *
 * API global:
 *   aplicarFiltroFactura(url) -> vuelca el numero aplicado en el searchParam
 *                                'factura' de una URL (para la busqueda y la paginacion).
 * -----------------------------------------------------------------------------
 */
(function () {
  const chip = document.getElementById('filtro-factura');
  if (!chip) return;

  const modal = document.getElementById('filtro-factura-modal');
  const trigger = document.getElementById('filtro-factura-trigger');
  const label = document.getElementById('filtro-factura-label');
  const form = document.getElementById('filtro-factura-form');
  const input = document.getElementById('filtro-factura-input');
  const btnLimpiar = document.getElementById('filtro-factura-limpiar');
  if (!modal || !trigger || !label || !form || !input) return;

  const ETIQUETA = 'Factura';

  const emitirCambio = () =>
    document.dispatchEvent(new CustomEvent('filtrofactura:cambio'));

  const abrirModal = () => {
    modal.classList.add('abierto');
    trigger.setAttribute('aria-expanded', 'true');
    // Arranco el input con el valor aplicado y el foco puesto para tipear de una.
    input.value = chip.dataset.valor || '';
    input.focus();
    input.select();
  };

  const cerrarModal = () => {
    modal.classList.remove('abierto');
    trigger.setAttribute('aria-expanded', 'false');
  };

  // Crea o quita la "x" del chip segun haya filtro aplicado.
  const actualizarClear = (activo) => {
    let clearEl = document.getElementById('filtro-factura-clear');
    if (activo && !clearEl) {
      clearEl = document.createElement('span');
      clearEl.className = 'material-symbols-outlined filtro-entidad__clear';
      clearEl.id = 'filtro-factura-clear';
      clearEl.setAttribute('role', 'button');
      clearEl.setAttribute('tabindex', '0');
      clearEl.setAttribute('aria-label', 'Quitar filtro de factura');
      clearEl.textContent = 'close';
      trigger.appendChild(clearEl);
    } else if (!activo && clearEl) {
      clearEl.remove();
    }
  };

  // Vuelca el numero aplicado al chip (label, activo, boton limpiar) y a data-valor.
  const setEstado = (valor) => {
    chip.dataset.valor = valor || '';
    const activo = Boolean(valor);
    label.textContent = activo ? `${ETIQUETA} ${valor}` : ETIQUETA;
    trigger.classList.toggle('is-active', activo);
    actualizarClear(activo);
  };

  const limpiar = () => {
    setEstado('');
    input.value = '';
    cerrarModal();
    emitirCambio();
  };

  // El chip abre el modal; si el click cae en la "x", limpia en su lugar.
  trigger.addEventListener('click', (e) => {
    if (e.target.closest('.filtro-entidad__clear')) {
      e.stopPropagation();
      limpiar();
      return;
    }
    abrirModal();
  });

  // La "x" es un span con role=button: Enter/Espacio tambien limpian.
  trigger.addEventListener('keydown', (e) => {
    if (e.target.closest('.filtro-entidad__clear') && (e.key === 'Enter' || e.key === ' ')) {
      e.preventDefault();
      e.stopPropagation();
      limpiar();
    }
  });

  // Aplicar: normalizo a solo digitos (el input ya lo restringe con pattern, pero
  // por las dudas), aplico y cierro. Vacio equivale a limpiar el filtro.
  form.addEventListener('submit', (e) => {
    e.preventDefault();
    const valor = (input.value || '').trim();
    setEstado(valor);
    cerrarModal();
    emitirCambio();
  });

  if (btnLimpiar) btnLimpiar.addEventListener('click', limpiar);

  // Cerrar con el fondo, la "x" del panel o Escape.
  modal.querySelectorAll('[data-filfac-cerrar]').forEach((el) => {
    el.addEventListener('click', cerrarModal);
  });
  modal.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && modal.classList.contains('abierto')) {
      e.preventDefault();
      cerrarModal();
    }
  });

  // Vuelca el filtro aplicado en la URL. La usan la busqueda y la paginacion.
  window.aplicarFiltroFactura = (url) => {
    const valor = chip.dataset.valor || '';
    if (valor) {
      url.searchParams.set('factura', valor);
    } else {
      url.searchParams.delete('factura');
    }
  };
})();
