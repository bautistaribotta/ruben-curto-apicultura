/**
 * -----------------------------------------------------------------------------
 * SELECTOR DE ENTIDAD (modal reutilizable, chip -> modal)
 * Agnostico de la vista: administra la apertura/cierre del modal, el filtro por
 * texto, la navegacion con teclado y el atrapado de foco. Al elegir una opcion
 * dispara el evento 'selector-entidad:elegir' sobre el contenedor, con
 * detail { id, principal }; cada vista lo engancha a su propia logica.
 *
 * La lista usa delegacion de eventos, asi que sobrevive a que una vista reemplace
 * los <li> por AJAX sin volver a inicializar nada.
 *
 * API global:
 *   abrirSelectorEntidad(idOrEl)
 *   cerrarSelectorEntidad(idOrEl)
 * -----------------------------------------------------------------------------
 */
(function () {
  // Guarda por contenedor el elemento que tenia el foco antes de abrir, para
  // devolverselo al cerrar.
  const focoPrevio = new WeakMap();

  function itemsVisibles(cont) {
    return Array.from(cont.querySelectorAll('.selent-item')).filter((el) => !el.hidden);
  }

  function resaltar(cont, indice) {
    const input = cont.querySelector('.selent__input');
    const visibles = itemsVisibles(cont);

    cont.querySelectorAll('.selent-item').forEach((el) => {
      el.classList.remove('resaltada', 'resaltado');
      el.setAttribute('aria-selected', 'false');
    });

    if (indice < 0 || indice >= visibles.length) {
      cont.dataset.resaltado = '-1';
      if (input) input.setAttribute('aria-activedescendant', '');
      return;
    }

    const el = visibles[indice];
    el.classList.add('resaltado');
    el.setAttribute('aria-selected', 'true');
    el.scrollIntoView({ block: 'nearest' });
    if (input && el.id) input.setAttribute('aria-activedescendant', el.id);
    cont.dataset.resaltado = String(indice);
  }

  function filtrar(cont) {
    const input = cont.querySelector('.selent__input');
    const termino = (input ? input.value : '').trim().toLowerCase();
    const items = cont.querySelectorAll('.selent-item');

    let visibles = 0;
    items.forEach((el) => {
      const coincide = (el.dataset.busqueda || '').includes(termino);
      el.hidden = !coincide;
      if (coincide) visibles++;
    });

    const sinResultados = cont.querySelector('.selent__sin-resultados');
    if (sinResultados) sinResultados.hidden = visibles !== 0 || items.length === 0;

    resaltar(cont, -1);
  }

  function elegir(cont, item) {
    if (!item) return;
    cont.dispatchEvent(
      new CustomEvent('selector-entidad:elegir', {
        bubbles: true,
        detail: { id: item.dataset.id, principal: item.dataset.principal || '' },
      })
    );
    cerrar(cont);
  }

  function abrir(cont) {
    if (!cont) return;
    focoPrevio.set(cont, document.activeElement);
    cont.classList.add('abierto');
    document.body.style.overflow = 'hidden';

    const input = cont.querySelector('.selent__input');
    if (input) {
      input.value = '';
      filtrar(cont);
      input.focus();
    }
  }

  function cerrar(cont) {
    if (!cont) return;
    cont.classList.remove('abierto');
    document.body.style.overflow = 'auto';

    const previo = focoPrevio.get(cont);
    if (previo && typeof previo.focus === 'function') previo.focus();
    focoPrevio.delete(cont);
  }

  function resolver(idOrEl) {
    return typeof idOrEl === 'string' ? document.getElementById(idOrEl) : idOrEl;
  }

  function inicializar(cont) {
    const input = cont.querySelector('.selent__input');
    const lista = cont.querySelector('.selent__lista');

    // Filtro por texto
    if (input) {
      input.addEventListener('input', () => filtrar(cont));

      input.addEventListener('keydown', (evento) => {
        const visibles = itemsVisibles(cont);
        const actual = parseInt(cont.dataset.resaltado || '-1', 10);

        if (evento.key === 'ArrowDown') {
          evento.preventDefault();
          if (visibles.length) resaltar(cont, (actual + 1) % visibles.length);
        } else if (evento.key === 'ArrowUp') {
          evento.preventDefault();
          if (visibles.length) resaltar(cont, (actual - 1 + visibles.length) % visibles.length);
        } else if (evento.key === 'Enter') {
          evento.preventDefault();
          if (actual >= 0) elegir(cont, visibles[actual]);
          else if (visibles.length === 1) elegir(cont, visibles[0]);
        }
      });
    }

    // Delegacion sobre la lista: sobrevive al reemplazo de items por AJAX
    if (lista) {
      lista.addEventListener('click', (evento) => {
        const item = evento.target.closest('.selent-item');
        if (item) elegir(cont, item);
      });
      lista.addEventListener('mousemove', (evento) => {
        const item = evento.target.closest('.selent-item');
        if (!item) return;
        const visibles = itemsVisibles(cont);
        const indice = visibles.indexOf(item);
        if (indice !== -1 && indice !== parseInt(cont.dataset.resaltado || '-1', 10)) {
          resaltar(cont, indice);
        }
      });
    }

    // Cerrar por fondo o por cualquier control marcado
    cont.querySelectorAll('[data-selent-cerrar]').forEach((el) => {
      el.addEventListener('click', () => cerrar(cont));
    });

    // Escape para cerrar y Tab para atrapar el foco dentro del panel
    cont.addEventListener('keydown', (evento) => {
      if (!cont.classList.contains('abierto')) return;

      if (evento.key === 'Escape') {
        evento.preventDefault();
        cerrar(cont);
        return;
      }

      if (evento.key === 'Tab') {
        const panel = cont.querySelector('.selent__panel');
        if (!panel) return;
        const focusables = panel.querySelectorAll(
          'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
        );
        const habilitados = Array.from(focusables).filter((el) => !el.disabled && el.offsetParent !== null);
        if (!habilitados.length) return;

        const primero = habilitados[0];
        const ultimo = habilitados[habilitados.length - 1];

        if (evento.shiftKey && document.activeElement === primero) {
          evento.preventDefault();
          ultimo.focus();
        } else if (!evento.shiftKey && document.activeElement === ultimo) {
          evento.preventDefault();
          primero.focus();
        }
      }
    });
  }

  // API global para abrir/cerrar desde las vistas
  window.abrirSelectorEntidad = (idOrEl) => abrir(resolver(idOrEl));
  window.cerrarSelectorEntidad = (idOrEl) => cerrar(resolver(idOrEl));

  document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.selent').forEach(inicializar);
  });
})();
