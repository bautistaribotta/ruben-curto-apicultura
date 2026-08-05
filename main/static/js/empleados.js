/**
 * -----------------------------------------------------------------------------
 * BUSQUEDA Y PAGINACION DE EMPLEADOS (AJAX)
 * -----------------------------------------------------------------------------
 * Replica el patron de clientes.js: busqueda en tiempo real con debounce
 * y paginacion sin recarga de pagina.
 */

const inputBusquedaEmpleado = document.getElementById('buscar-empleado');
const contenedorTablaEmpleados = document.getElementById('tabla-empleados-container');

/**
 * Realiza la busqueda de empleados mediante AJAX.
 * Si recibe una URL (paginacion), la usa directamente.
 * Si no, construye la URL con el valor del input de busqueda.
 */
const buscarEmpleado = (urlString = null) => {
  if (!inputBusquedaEmpleado || !contenedorTablaEmpleados) return;

  const q = inputBusquedaEmpleado.value;
  let url;

  if (urlString) {
    url = new URL(urlString, window.location.origin);
  } else {
    url = new URL(window.location.href);
    url.searchParams.set('q', q);
    url.searchParams.delete('page');
  }

  fetch(url, {
    headers: {
      'X-Requested-With': 'XMLHttpRequest',
    },
  })
    .then((response) => response.text())
    .then((html) => {
      contenedorTablaEmpleados.innerHTML = html;
      window.history.pushState({}, '', url);
      vincularPaginacionEmpleados();
    })
    .catch((error) => console.error('Error en la busqueda:', error));
};

/**
 * Vincula los clicks de paginacion para que usen AJAX
 * en lugar de recargar la pagina entera.
 */
const vincularPaginacionEmpleados = () => {
  if (!contenedorTablaEmpleados) return;
  const linksPaginacion = contenedorTablaEmpleados.querySelectorAll('.paginacion-botones a');

  linksPaginacion.forEach((link) => {
    link.addEventListener('click', (e) => {
      e.preventDefault();
      buscarEmpleado(link.getAttribute('href'));
    });
  });
};

// Debounce de 300ms para no disparar una peticion por cada tecla
let timerBusquedaEmpleado;
if (inputBusquedaEmpleado) {
  inputBusquedaEmpleado.addEventListener('input', () => {
    clearTimeout(timerBusquedaEmpleado);
    timerBusquedaEmpleado = setTimeout(() => buscarEmpleado(), 300);
  });
}

// Vinculo la paginacion al cargar la pagina
vincularPaginacionEmpleados();

/**
 * -----------------------------------------------------------------------------
 * CONTROLADORES DE PANELES (NUEVO/EDITAR/ELIMINAR)
 * -----------------------------------------------------------------------------
 */

const prepararPanelNuevoEmpleado = () => {
  document.querySelector('#slide-over-panel h3').innerText = 'Nuevo Empleado';
  document.querySelector('#slide-over-panel .texto-cabecera p').innerText = 'Ingrese los datos para el registro';
  document.querySelector('.boton-primario').innerText = 'Guardar Empleado';
  document.querySelector('.icono-contenedor span').innerText = 'person_add';

  document.getElementById('form-empleado').reset();
  document.getElementById('id_empleado').value = '';

  if (typeof abrirSlideOver === 'function') abrirSlideOver();
};

const prepararPanelEditarEmpleado = (id) => {
  // Pido los datos del empleado a la API interna y relleno el formulario
  fetch(`/api/empleados/${id}/`)
    .then((response) => response.json())
    .then((empleado) => {
      document.querySelector('#slide-over-panel h3').innerText = 'Editar Empleado';
      document.querySelector('#slide-over-panel .texto-cabecera p').innerText = 'Modifique los datos del empleado';
      document.querySelector('.boton-primario').innerText = 'Actualizar Empleado';
      document.querySelector('.icono-contenedor span').innerText = 'edit_note';

      document.getElementById('id_empleado').value = empleado.id;
      document.getElementById('nombre').value = empleado.nombre;
      document.getElementById('apellido').value = empleado.apellido;

      if (typeof abrirSlideOver === 'function') abrirSlideOver();
    })
    .catch((error) => {
      console.error(error);
      if (typeof abrirModalError === 'function') {
        abrirModalError('Error al cargar los datos del empleado');
      }
    });
};

const prepararPanelEliminarEmpleado = (id, nombre) => {
  document.getElementById('id_eliminar').value = id;
  // El perfil comparte este panel con el borrado de pagos, que cambia la accion;
  // la devuelvo a 'eliminar' para no borrar un pago en vez del empleado.
  const campoAccion = document.getElementById('accion-eliminar');
  if (campoAccion) campoAccion.value = 'eliminar';
  document.getElementById('texto-confirmacion-eliminar').innerText = `¿Está seguro que quiere eliminar al empleado ${nombre}?`;
  if (typeof abrirPanelEliminar === 'function') abrirPanelEliminar();
};

// Delegacion de eventos en la tabla para botones generados dinamicamente (AJAX)
if (contenedorTablaEmpleados) {
  contenedorTablaEmpleados.addEventListener('click', (e) => {
    const btnEditar = e.target.closest('.boton-icono.editar');
    const btnEliminar = e.target.closest('.boton-icono.eliminar');

    if (btnEditar) {
      e.preventDefault();
      prepararPanelEditarEmpleado(btnEditar.dataset.id);
    } else if (btnEliminar) {
      e.preventDefault();
      prepararPanelEliminarEmpleado(btnEliminar.dataset.id, btnEliminar.dataset.nombre);
    }
  });
}

// Hago accesible la funcion que el HTML llama desde el atributo onclick inline
window.prepararPanelNuevoEmpleado = prepararPanelNuevoEmpleado;
