/**
 * -----------------------------------------------------------------------------
 * FILTRO DE FECHA REUTILIZABLE (chip + popover)
 * Reciclado del filtro de Deudas. Es agnostico de la vista: administra el
 * popover y guarda el estado APLICADO en los data-desde/data-hasta del
 * contenedor #filtro-fechas (fuente de verdad). Al aplicar o limpiar dispara el
 * evento 'filtrofechas:cambio' en document; cada vista lo engancha a su propia
 * busqueda AJAX y lee esos data-* para armar la URL.
 * -----------------------------------------------------------------------------
 */
document.addEventListener('DOMContentLoaded', () => {
  const cont = document.getElementById('filtro-fechas');
  if (!cont) return;

  const trigger = document.getElementById('filtro-fechas-trigger');
  const label = document.getElementById('filtro-fechas-label');
  const pop = document.getElementById('filtro-fechas-pop');
  if (!trigger || !label || !pop) return;

  const segOpts = pop.querySelectorAll('.ff-seg__opt');
  const inputDia = document.getElementById('filtro-fechas-dia');
  const inputDesde = document.getElementById('filtro-fechas-desde');
  const inputHasta = document.getElementById('filtro-fechas-hasta');
  const btnAplicar = document.getElementById('filtro-fechas-aplicar');
  const btnLimpiar = document.getElementById('filtro-fechas-limpiar');

  // ISO (yyyy-mm-dd) -> dd/mm/yyyy y version corta dd/mm.
  const fmt = (iso) => { const [y, m, d] = iso.split('-'); return `${d}/${m}/${y}`; };
  const fmtCorto = (iso) => { const [, m, d] = iso.split('-'); return `${d}/${m}`; };

  // Mismo criterio de etiqueta que el server: un dia, rango cerrado o rango
  // abierto con un solo extremo.
  const armarLabel = (desde, hasta) => {
    if (desde && hasta && desde === hasta) return fmt(desde);
    if (desde && hasta) return `${fmtCorto(desde)} – ${fmt(hasta)}`;
    if (desde) return `Desde ${fmt(desde)}`;
    if (hasta) return `Hasta ${fmt(hasta)}`;
    return 'Fechas';
  };

  const modoActivo = () => {
    const opt = pop.querySelector('.ff-seg__opt.is-active');
    return opt ? opt.dataset.modo : 'dia';
  };

  const setModo = (modo) => {
    segOpts.forEach((o) => o.classList.toggle('is-active', o.dataset.modo === modo));
    pop.querySelectorAll('.ff-panel').forEach((p) => {
      p.hidden = p.dataset.panel !== modo;
    });
  };

  // Crea o quita la "x" para limpiar dentro del chip segun haya filtro activo.
  const actualizarClear = (activo) => {
    let clearEl = trigger.querySelector('.ff-clear');
    if (activo && !clearEl) {
      clearEl = document.createElement('span');
      clearEl.className = 'material-symbols-outlined ff-clear';
      clearEl.id = 'filtro-fechas-clear';
      clearEl.setAttribute('role', 'button');
      clearEl.setAttribute('tabindex', '0');
      clearEl.setAttribute('aria-label', 'Quitar filtro de fechas');
      clearEl.textContent = 'close';
      trigger.appendChild(clearEl);
    } else if (!activo && clearEl) {
      clearEl.remove();
    }
  };

  // Vuelca el estado aplicado al chip (label, activo, boton limpiar) y a los
  // data-* que leen las vistas.
  const setEstado = (desde, hasta) => {
    cont.dataset.desde = desde || '';
    cont.dataset.hasta = hasta || '';
    const activo = Boolean(desde || hasta);
    label.textContent = armarLabel(desde, hasta);
    trigger.classList.toggle('is-active', activo);
    actualizarClear(activo);
  };

  const abrir = () => { pop.hidden = false; trigger.setAttribute('aria-expanded', 'true'); };
  const cerrar = () => { pop.hidden = true; trigger.setAttribute('aria-expanded', 'false'); };
  const toggle = () => (pop.hidden ? abrir() : cerrar());

  // Avisa a la vista que el filtro cambio; ella dispara su busqueda AJAX.
  const notificar = () => document.dispatchEvent(new CustomEvent('filtrofechas:cambio'));

  const aplicar = () => {
    let desde = '';
    let hasta = '';
    if (modoActivo() === 'dia') {
      desde = inputDia.value;
      hasta = inputDia.value;
    } else {
      desde = inputDesde.value;
      hasta = inputHasta.value;
    }
    // Normalizo el rango invertido para que el label coincida con el server.
    if (desde && hasta && desde > hasta) {
      [desde, hasta] = [hasta, desde];
    }
    setEstado(desde, hasta);
    cerrar();
    notificar();
  };

  const limpiar = () => {
    if (inputDia) inputDia.value = '';
    if (inputDesde) inputDesde.value = '';
    if (inputHasta) inputHasta.value = '';
    setEstado('', '');
    cerrar();
    notificar();
  };

  // Rehidrato el popover con el estado que vino del server: infiero el modo a
  // partir de si las dos fechas coinciden (un dia) o no (rango).
  const dIni = cont.dataset.desde;
  const hIni = cont.dataset.hasta;
  if (dIni && hIni && dIni === hIni) {
    setModo('dia');
    if (inputDia) inputDia.value = dIni;
  } else if (dIni || hIni) {
    setModo('rango');
    if (inputDesde) inputDesde.value = dIni;
    if (inputHasta) inputHasta.value = hIni;
  } else {
    setModo('dia');
  }

  // El chip abre/cierra el popover; si el click cae en la "x", limpia en su lugar.
  trigger.addEventListener('click', (e) => {
    if (e.target.closest('.ff-clear')) {
      e.stopPropagation();
      limpiar();
      return;
    }
    toggle();
  });

  segOpts.forEach((opt) => opt.addEventListener('click', () => setModo(opt.dataset.modo)));

  if (btnAplicar) btnAplicar.addEventListener('click', aplicar);
  if (btnLimpiar) btnLimpiar.addEventListener('click', limpiar);

  // Enter dentro de cualquier input del popover aplica.
  pop.querySelectorAll('.ff-campo__input').forEach((inp) => {
    inp.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        aplicar();
      }
    });
  });

  // Cierro al hacer click fuera del filtro o con Escape.
  document.addEventListener('click', (e) => {
    if (!pop.hidden && !cont.contains(e.target)) cerrar();
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && !pop.hidden) {
      cerrar();
      trigger.focus();
    }
  });
});
