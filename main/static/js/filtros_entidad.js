/**
 * -----------------------------------------------------------------------------
 * FILTROS POR ENTIDAD (chip -> modal selector_entidad)
 * Cablea de forma generica todos los chips .filtro-entidad de una vista: abren su
 * modal, aplican la eleccion y limpian con la "x". El estado aplicado (id + nombre)
 * vive en los data-* de cada chip, que sobreviven a los refrescos AJAX porque los
 * chips estan fuera de la region que se reemplaza.
 *
 * Al cambiar cualquier filtro dispara el evento 'filtroentidad:cambio' sobre document
 * (mismo patron que filtro_fechas.js); cada vista lo engancha a su busqueda AJAX.
 *
 * API global:
 *   aplicarFiltrosEntidad(url)  -> vuelca los filtros aplicados en los searchParams de
 *                                  una URL (para la busqueda y para la paginacion).
 * -----------------------------------------------------------------------------
 */
(function () {
  const emitirCambio = () =>
    document.dispatchEvent(new CustomEvent('filtroentidad:cambio'));

  function cablearChip(chip) {
    const modal = document.getElementById(chip.dataset.modal || '');
    const trigger = chip.querySelector('.filtro-entidad__trigger');
    const label = chip.querySelector('.filtro-entidad__label');
    if (!modal || !trigger || !label) return;

    const etiqueta = chip.dataset.etiqueta || 'Filtro';
    const ariaLimpiar = `Quitar filtro de ${etiqueta.toLowerCase()}`;

    // Crea o quita la "x" para limpiar dentro del chip segun haya filtro elegido.
    const actualizarClear = (activo) => {
      let clearEl = trigger.querySelector('.filtro-entidad__clear');
      if (activo && !clearEl) {
        clearEl = document.createElement('span');
        clearEl.className = 'material-symbols-outlined filtro-entidad__clear';
        clearEl.setAttribute('role', 'button');
        clearEl.setAttribute('tabindex', '0');
        clearEl.setAttribute('aria-label', ariaLimpiar);
        clearEl.textContent = 'close';
        trigger.appendChild(clearEl);
      } else if (!activo && clearEl) {
        clearEl.remove();
      }
    };

    // Vuelca el estado elegido al chip (label, activo, boton limpiar) y a los data-*.
    const setEstado = (id, nombre) => {
      chip.dataset.filtroId = id || '';
      chip.dataset.filtroNombre = nombre || '';
      const activo = Boolean(id);
      label.textContent = activo ? nombre : etiqueta;
      trigger.classList.toggle('is-active', activo);
      actualizarClear(activo);
    };

    const limpiar = () => {
      setEstado('', '');
      emitirCambio();
    };

    // El chip abre el modal; si el click cae en la "x", limpia en su lugar (la "x"
    // vive dentro del boton, asi que un solo handler cubre ambos casos).
    trigger.addEventListener('click', (e) => {
      if (e.target.closest('.filtro-entidad__clear')) {
        e.stopPropagation();
        limpiar();
        return;
      }
      if (typeof window.abrirSelectorEntidad === 'function') {
        window.abrirSelectorEntidad(modal);
      }
    });

    // La "x" es un span con role=button: Enter/Espacio tambien limpian.
    trigger.addEventListener('keydown', (e) => {
      if (e.target.closest('.filtro-entidad__clear') && (e.key === 'Enter' || e.key === ' ')) {
        e.preventDefault();
        e.stopPropagation();
        limpiar();
      }
    });

    // El modal avisa la eleccion; aplico el filtro con la entidad elegida.
    modal.addEventListener('selector-entidad:elegir', (e) => {
      setEstado(e.detail.id, e.detail.principal);
      emitirCambio();
    });
  }

  // Vuelca los filtros aplicados en la URL. La usan tanto la busqueda como la
  // paginacion, para que los filtros sobrevivan a "Anterior"/"Siguiente".
  window.aplicarFiltrosEntidad = (url) => {
    document.querySelectorAll('.filtro-entidad').forEach((chip) => {
      const param = chip.dataset.param;
      if (!param) return;
      const valor = chip.dataset.filtroId || '';
      if (valor) {
        url.searchParams.set(param, valor);
      } else {
        url.searchParams.delete(param);
      }
    });
  };

  document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.filtro-entidad').forEach(cablearChip);
  });
})();
