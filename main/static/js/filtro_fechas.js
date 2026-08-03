/**
 * -----------------------------------------------------------------------------
 * FILTRO DE FECHA REUTILIZABLE (chip + popover)
 * Reciclado del filtro de Deudas. Es agnostico de la vista: administra el
 * popover y guarda el estado APLICADO en los data-desde/data-hasta del
 * contenedor #filtro-fechas (fuente de verdad). Al aplicar o limpiar dispara el
 * evento 'filtrofechas:cambio' en document; cada vista lo engancha a su propia
 * busqueda AJAX y lee esos data-* para armar la URL.
 *
 * Tres modos posibles (dia, mes y rango) y cada vista elige cuales muestra al
 * incluir la plantilla. Los tres terminan en lo mismo: un desde y un hasta. El
 * mes no es un parametro aparte, es el rango del 1 al ultimo dia.
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
  const inputMes = document.getElementById('filtro-fechas-mes');
  const inputDesde = document.getElementById('filtro-fechas-desde');
  const inputHasta = document.getElementById('filtro-fechas-hasta');
  const btnAplicar = document.getElementById('filtro-fechas-aplicar');
  const btnLimpiar = document.getElementById('filtro-fechas-limpiar');

  // Modo por defecto: el primero que la vista haya pedido, no siempre "dia".
  const modoInicial = segOpts.length ? segOpts[0].dataset.modo : 'dia';

  const NOMBRES_MES = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio',
                       'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'];

  // ISO (yyyy-mm-dd) -> dd/mm/yyyy y version corta dd/mm.
  const fmt = (iso) => { const [y, m, d] = iso.split('-'); return `${d}/${m}/${y}`; };
  const fmtCorto = (iso) => { const [, m, d] = iso.split('-'); return `${d}/${m}`; };

  // Ultimo dia de un mes. El dia 0 del mes siguiente es el ultimo del anterior,
  // asi que los años bisiestos salen solos.
  const ultimoDia = (anio, mes) => new Date(anio, mes, 0).getDate();

  // Si el rango es un mes entero devuelve "yyyy-mm"; si no, null. Sirve tanto
  // para etiquetarlo por su nombre como para rehidratar el popover en modo mes.
  const comoMes = (desde, hasta) => {
    if (!desde || !hasta) return null;
    const [ad, md, dd] = desde.split('-').map(Number);
    const [ah, mh, dh] = hasta.split('-').map(Number);
    if (ad !== ah || md !== mh) return null;
    if (dd !== 1 || dh !== ultimoDia(ad, md)) return null;
    return desde.slice(0, 7);
  };

  // Mismo criterio de etiqueta que el server: mes entero, un dia, rango cerrado
  // o rango abierto con un solo extremo.
  //
  // El nombre del mes solo se usa donde el modo existe. En las vistas que no lo
  // ofrecen, un rango que casualmente cubre un mes entero se sigue etiquetando
  // como rango, que es lo que renderiza el server y lo que ya venian mostrando.
  const armarLabel = (desde, hasta) => {
    const mes = inputMes ? comoMes(desde, hasta) : null;
    if (mes) {
      const [anio, numero] = mes.split('-').map(Number);
      const nombre = NOMBRES_MES[numero - 1];
      return `${nombre.charAt(0).toUpperCase()}${nombre.slice(1)} ${anio}`;
    }
    if (desde && hasta && desde === hasta) return fmt(desde);
    if (desde && hasta) return `${fmtCorto(desde)} – ${fmt(hasta)}`;
    if (desde) return `Desde ${fmt(desde)}`;
    if (hasta) return `Hasta ${fmt(hasta)}`;
    return 'Fechas';
  };

  const modoActivo = () => {
    const opt = pop.querySelector('.ff-seg__opt.is-active');
    return opt ? opt.dataset.modo : modoInicial;
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
    const modo = modoActivo();

    if (modo === 'dia') {
      desde = inputDia.value;
      hasta = inputDia.value;
    } else if (modo === 'mes') {
      // El mes se expande a sus dos extremos: el server no sabe de meses, solo
      // de rangos, y asi "julio" y "del 1 al 31 de julio" son la misma consulta.
      if (inputMes.value) {
        const [anio, numero] = inputMes.value.split('-').map(Number);
        desde = `${inputMes.value}-01`;
        hasta = `${inputMes.value}-${String(ultimoDia(anio, numero)).padStart(2, '0')}`;
      }
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
    if (inputMes) inputMes.value = '';
    if (inputDesde) inputDesde.value = '';
    if (inputHasta) inputHasta.value = '';
    setEstado('', '');
    cerrar();
    notificar();
  };

  // Rehidrato el popover con el estado que vino del server, infiriendo el modo
  // del rango: un mes entero si coincide con sus extremos, un dia si las dos
  // fechas son la misma, y rango en cualquier otro caso. El mes se prueba
  // primero porque tambien cumple la condicion de rango.
  const dIni = cont.dataset.desde;
  const hIni = cont.dataset.hasta;
  const mesIni = comoMes(dIni, hIni);

  if (mesIni && inputMes) {
    setModo('mes');
    inputMes.value = mesIni;
  } else if (dIni && hIni && dIni === hIni && inputDia) {
    setModo('dia');
    inputDia.value = dIni;
  } else if (dIni || hIni) {
    setModo('rango');
    if (inputDesde) inputDesde.value = dIni;
    if (inputHasta) inputHasta.value = hIni;
  } else {
    setModo(modoInicial);
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
