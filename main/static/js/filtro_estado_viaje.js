/**
 * -----------------------------------------------------------------------------
 * FILTRO DE ESTADO DEL VIAJE (PILDORA CON MENU DESPLEGABLE)
 * -----------------------------------------------------------------------------
 * Reemplaza a las tres pildoras sueltas (Todos / En curso / Finalizado) por una
 * sola pildora que abre un menu. Al elegir una opcion escribe el valor en el input
 * hidden #filtro-estado (que lee viajes.js) y avisa por el evento
 * 'filtroestado:cambio' para que se dispare la busqueda AJAX.
 */
(function () {
  const cont = document.getElementById('filtro-estado-viaje');
  const trigger = document.getElementById('filtro-estado-trigger');
  const menu = document.getElementById('filtro-estado-menu');
  const label = document.getElementById('filtro-estado-label');
  const hidden = document.getElementById('filtro-estado');
  if (!cont || !trigger || !menu || !label) return;

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

    // Refleja el estado en el trigger y en el input hidden que lee viajes.js.
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
