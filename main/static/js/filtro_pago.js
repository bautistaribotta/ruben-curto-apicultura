/**
 * -----------------------------------------------------------------------------
 * FILTRO DE ESTADO DE COBRO (segmentado Por cobrar / Cobradas / Todas)
 * Cablea el segmentado .filtro-pago de una vista de viajes: al elegir un estado
 * marca el segmento activo y dispara 'filtropago:cambio' sobre document (mismo
 * patron que filtro_fechas.js / filtros_entidad.js); cada vista lo engancha a su
 * busqueda AJAX.
 *
 * El estado elegido vive en la clase is-active del boton, que sobrevive a los
 * refrescos AJAX porque el control esta fuera de la region que se reemplaza.
 *
 * API global:
 *   aplicarFiltroPago(url) -> vuelca el estado activo en el searchParam 'pago' de
 *                             una URL (para la busqueda y para la paginacion).
 * -----------------------------------------------------------------------------
 */
(function () {
  const control = document.getElementById('filtro-pago');
  if (!control) return;

  const opciones = control.querySelectorAll('.filtro-pago__opt');

  const activar = (boton) => {
    opciones.forEach((opt) => {
      const activo = opt === boton;
      opt.classList.toggle('is-active', activo);
      opt.setAttribute('aria-pressed', activo ? 'true' : 'false');
    });
    document.dispatchEvent(new CustomEvent('filtropago:cambio'));
  };

  opciones.forEach((opt) => {
    opt.addEventListener('click', () => {
      // Sin efecto si ya es el activo: evita una busqueda AJAX redundante.
      if (opt.classList.contains('is-active')) return;
      activar(opt);
    });
  });

  // Vuelca el estado activo en la URL. La usan la busqueda y la paginacion, para
  // que el filtro sobreviva a "Anterior"/"Siguiente".
  window.aplicarFiltroPago = (url) => {
    const activo = control.querySelector('.filtro-pago__opt.is-active');
    const valor = activo ? activo.dataset.pago : 'cobrar';
    // 'cobrar' es el default del backend: no ensucio la URL con el valor por defecto.
    if (valor && valor !== 'cobrar') {
      url.searchParams.set('pago', valor);
    } else {
      url.searchParams.delete('pago');
    }
  };
})();
