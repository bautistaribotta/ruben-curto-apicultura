/**
 * -----------------------------------------------------------------------------
 * FILTRO DE ESTADO (PILDORA CON MENU DESPLEGABLE)
 * -----------------------------------------------------------------------------
 * Una sola pildora que abre un menu con los estados posibles, en vez de una
 * pildora suelta por estado. Es generica: la usan Viajes (En curso / Finalizado)
 * y Marcos (Con cera / Intermedio / Apolillado); el markup de las opciones lo
 * pone el partial de cada vista.
 *
 * Al elegir una opcion deja el valor en data-estado del contenedor y, si la vista
 * declara un input hidden con data-hidden, tambien lo escribe ahi (asi lo lee
 * viajes.js). Despues avisa por el evento 'filtroestado:cambio' para que cada
 * vista dispare su busqueda AJAX.
 */
(function () {
  const cont = document.querySelector('.filtro-estado');
  if (!cont) return;

  const trigger = cont.querySelector('.filtro-estado__trigger');
  const menu = cont.querySelector('.filtro-estado__menu');
  const label = cont.querySelector('.filtro-estado__label');
  const hidden = document.getElementById(cont.dataset.hidden || '');
  if (!trigger || !menu || !label) return;

  const opciones = () => Array.from(menu.querySelectorAll('.filtro-estado__opt'));
  const estaAbierto = () => !menu.hidden;

  const abrir = () => {
    menu.hidden = false;
    trigger.setAttribute('aria-expanded', 'true');
    cont.classList.add('is-open');
    const sel = menu.querySelector('.filtro-estado__opt.is-selected') || opciones()[0];
    if (sel) sel.focus();
  };

  const cerrar = ({ foco = false } = {}) => {
    menu.hidden = true;
    trigger.setAttribute('aria-expanded', 'false');
    cont.classList.remove('is-open');
    if (foco) trigger.focus();
  };

  const elegir = (opt) => {
    const estado = opt.dataset.estado;

    // Marca visual de la opcion elegida dentro del menu.
    opciones().forEach((o) => {
      const activo = o === opt;
      o.classList.toggle('is-selected', activo);
      o.setAttribute('aria-selected', activo ? 'true' : 'false');
    });

    // Refleja el estado en el trigger, en el data-* del contenedor y, si la vista
    // lo declaro, en su input hidden.
    label.textContent = estado || 'Todos';
    trigger.classList.toggle('is-active', Boolean(estado));
    cont.dataset.estado = estado;
    if (hidden) hidden.value = estado;

    cerrar({ foco: true });
    document.dispatchEvent(new CustomEvent('filtroestado:cambio'));
  };

  trigger.addEventListener('click', () => {
    if (estaAbierto()) cerrar({ foco: true }); else abrir();
  });

  // Abrir el menu con teclado desde el trigger.
  trigger.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowDown' || e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      abrir();
    }
  });

  menu.addEventListener('click', (e) => {
    const opt = e.target.closest('.filtro-estado__opt');
    if (opt) elegir(opt);
  });

  // Teclado sobre las opciones: flechas para moverse, Enter/Espacio para elegir.
  menu.addEventListener('keydown', (e) => {
    const items = opciones();
    const idx = items.indexOf(document.activeElement);
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      (items[idx + 1] || items[0]).focus();
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      (items[idx - 1] || items[items.length - 1]).focus();
    } else if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      if (items[idx]) elegir(items[idx]);
    } else if (e.key === 'Escape') {
      e.preventDefault();
      cerrar({ foco: true });
    } else if (e.key === 'Tab') {
      cerrar();
    }
  });

  // Cierra al hacer clic fuera de la pildora.
  document.addEventListener('click', (e) => {
    if (estaAbierto() && !cont.contains(e.target)) cerrar();
  });
})();
