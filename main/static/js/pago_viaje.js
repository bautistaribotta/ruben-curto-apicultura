/**
 * -----------------------------------------------------------------------------
 * CASILLA DE COBRO DE LAS TABLAS DE VIAJES (reparto y cereal)
 * Marca o desmarca el pago de un viaje sin recargar la pagina.
 *
 * El listener va delegado en document a proposito: el buscador, el filtro de
 * fechas y la paginacion reemplazan el <tbody> entero por AJAX, asi que las
 * casillas que vienen en el HTML nuevo no existian al cargar la pagina.
 * -----------------------------------------------------------------------------
 */

/**
 * Devuelve el token CSRF de la cookie (mismo patron que operacion_modales.js).
 */
const obtenerCsrfPago = () => {
  const cookie = document.cookie.split('; ').find((c) => c.startsWith('csrftoken='));
  return cookie ? cookie.split('=')[1] : '';
};

document.addEventListener('change', (evento) => {
  const casilla = evento.target;
  if (!casilla.classList || !casilla.classList.contains('pago-check')) return;

  const url = casilla.dataset.pagoUrl;
  if (!url) return;

  // Nombre de la entidad para el mensaje ("Reparto" / "Viaje"), lo pone el template
  const entidad = casilla.dataset.pagoEntidad || 'Viaje';
  const marcado = casilla.checked;

  // Bloqueo la casilla mientras viaja el pedido: evita dobles clicks que dejen
  // la vista y la base contando distinto.
  casilla.disabled = true;

  const cuerpo = new URLSearchParams({ pagado: marcado ? '1' : '0' });

  fetch(url, {
    method: 'POST',
    headers: {
      'X-CSRFToken': obtenerCsrfPago(),
      'X-Requested-With': 'XMLHttpRequest',
      'Content-Type': 'application/x-www-form-urlencoded',
    },
    body: cuerpo.toString(),
  })
    .then((respuesta) => {
      if (!respuesta.ok) {
        // El 403 (sin permiso) trae su propio mensaje; el resto cae en el generico
        return respuesta
          .json()
          .catch(() => ({}))
          .then((datos) => {
            throw new Error(datos.error || 'No se pudo actualizar el estado de pago.');
          });
      }
      return respuesta.json();
    })
    .then((datos) => {
      // Me quedo con lo que confirmo el servidor, no con lo que muestra la casilla
      casilla.checked = Boolean(datos.pagado);
      casilla.disabled = false;
      notificarExito(datos.pagado
        ? `${entidad} marcado como pagado.`
        : `${entidad} marcado como pendiente.`);
    })
    .catch((error) => {
      // Vuelvo la casilla a su estado anterior: la tabla no puede mostrar un cobro
      // que la base no registro.
      casilla.checked = !marcado;
      casilla.disabled = false;
      notificarErrorModal(error.message);
    });
});
