/**
 * -----------------------------------------------------------------------------
 * 1. UTILIDADES GENERALES (BÚSQUEDA Y PAGINACIÓN)
 * -----------------------------------------------------------------------------
 */

// Selecciono los elementos del DOM que voy a usar para la búsqueda
const inputBusqueda = document.getElementById('buscar-cliente');
const contenedorTabla = document.getElementById('tabla-clientes-container');

/**
 * Creo esta función para realizar las búsquedas de clientes mediante AJAX.
 * Si recibe una URL (como al hacer click en la paginación), usa esa.
 * Si no, construye la URL con el valor del input de búsqueda.
 * @param {string|null} urlString - URL opcional para la paginación.
 */
const buscar = (urlString = null) => {
  if (!inputBusqueda || !contenedorTabla) return;

  const q = inputBusqueda.value;
  let url;
  
  if (urlString) {
    url = new URL(urlString, window.location.origin);
  } else {
    url = new URL(window.location.href);
    url.searchParams.set('q', q);
    url.searchParams.delete('page');
  }

  // Realizo la petición fetch indicando que es XMLHttpRequest
  fetch(url, {
    headers: {
      'X-Requested-With': 'XMLHttpRequest',
    },
  })
    .then((response) => response.text())
    .then((html) => {
      // Actualizo el contenedor con la nueva tabla
      contenedorTabla.innerHTML = html;
      
      // Actualizo la URL en la barra del navegador sin recargar la página
      window.history.pushState({}, '', url);
      
      // Vuelvo a vincular los eventos a los nuevos botones de paginación
      vincularPaginacion();
    })
    .catch((error) => console.error('Error en la búsqueda:', error));
};

/**
 * Creo esta función para atrapar los clicks en los botones de paginación
 * y evitar que recarguen la página entera, usando AJAX en su lugar.
 */
const vincularPaginacion = () => {
  if (!contenedorTabla) return;
  const linksPaginacion = contenedorTabla.querySelectorAll('.paginacion-botones a');
  
  linksPaginacion.forEach((link) => {
    link.addEventListener('click', (e) => {
      e.preventDefault();
      buscar(link.href);
    });
  });
};

// Si existen los elementos, agrego los event listeners iniciales
if (inputBusqueda) {
  inputBusqueda.addEventListener('input', () => buscar());
}
vincularPaginacion();

/**
 * -----------------------------------------------------------------------------
 * 2. FORMATO DE CUIT Y FACTURACIÓN
 * -----------------------------------------------------------------------------
 */

const checkboxFactura = document.getElementById('factura');
const campoCuit = document.getElementById('campo-cuit');
const inputCuit = document.getElementById('cuit');

/**
 * Creo esta función para mostrar u ocultar el campo de CUIT 
 * dependiendo de si el checkbox de facturación está marcado.
 */
const actualizarCuit = () => {
  if (checkboxFactura && campoCuit && inputCuit) {
    const facturacionActiva = checkboxFactura.checked;
    campoCuit.style.display = facturacionActiva ? 'flex' : 'none';
    
    // Si la facturación está activa, el CUIT es estrictamente obligatorio
    if (facturacionActiva) {
      inputCuit.setAttribute('required', 'required');
    } else {
      inputCuit.removeAttribute('required');
      // Opcional: limpiar el CUIT si se desactiva la facturación
      // inputCuit.value = ''; 
    }
  }
};

if (checkboxFactura && campoCuit) {
  checkboxFactura.addEventListener('change', actualizarCuit);
  actualizarCuit(); 
}

// Solo permito números en el CUIT mientras el usuario escribe
if (inputCuit) {
  inputCuit.addEventListener('input', (e) => {
    // Elimino todo lo que no sea un número dejando puramente dígitos
    e.target.value = e.target.value.replace(/\D/g, '');
  });
}

/**
 * -----------------------------------------------------------------------------
 * 3. CONTROLADORES DE PANELES (NUEVO/EDITAR) Y REDIRECCIONES
 * -----------------------------------------------------------------------------
 */

/**
 * Creo esta función para redireccionar a la vista de detalles del cliente
 * al hacer doble click en una fila.
 * @param {string|number} id - El ID del cliente
 */
const irAInformacionCliente = (id) => {
  window.location.href = `/informacion_clientes/${id}/`;
};

/**
 * Creo esta función para limpiar y configurar el panel lateral 
 * cuando el usuario quiere registrar un nuevo cliente.
 */
const prepararPanelNuevoCliente = () => {
  // Cambio los textos del panel a su estado original para la creación
  document.querySelector('#slide-over-panel h3').innerText = 'Nuevo Cliente';
  document.querySelector('#slide-over-panel .texto-cabecera p').innerText = 'Ingrese los datos para el registro';
  document.querySelector('.boton-primario').innerText = 'Guardar Cliente';
  document.querySelector('.icono-contenedor span').innerText = 'person_add';

  // Limpio el formulario y me aseguro de vaciar el ID oculto
  document.getElementById('form-cliente').reset();
  document.getElementById('id_cliente').value = '';
  
  // Verifico el estado del campo CUIT y abro el panel
  actualizarCuit();
  if (typeof abrirSlideOver === 'function') abrirSlideOver();
};

/**
 * Creo esta función para obtener los datos de un cliente y rellenar 
 * el panel lateral para poder editarlo.
 * @param {string|number} id - El ID del cliente a editar
 */
const prepararPanelEditarCliente = (id) => {
  // Pido los datos del cliente a mi API interna
  fetch(`/api/clientes/${id}/`)
    .then((response) => response.json())
    .then((cliente) => {
      // Actualizo los textos del panel para indicar que es una edición
      document.querySelector('#slide-over-panel h3').innerText = 'Editar Cliente';
      document.querySelector('#slide-over-panel .texto-cabecera p').innerText = 'Modifique los datos del perfil';
      document.querySelector('.boton-primario').innerText = 'Actualizar Cliente';
      document.querySelector('.icono-contenedor span').innerText = 'edit_note';

      // Relleno los campos del formulario con la información recibida
      document.getElementById('id_cliente').value = cliente.id;
      document.getElementById('nombre').value = cliente.nombre;
      document.getElementById('apellido').value = cliente.apellido;
      document.getElementById('telefono').value = cliente.telefono;
      document.getElementById('localidad').value = cliente.localidad;
      document.getElementById('direccion').value = cliente.direccion;
      
      // El CUIT se muestra en crudo (solo números) de la BD
      document.getElementById('cuit').value = cliente.cuit || '';
      
      document.getElementById('factura').checked = cliente.factura;

      // Ajusto la visibilidad del CUIT y abro el panel
      actualizarCuit();
      if (typeof abrirSlideOver === 'function') abrirSlideOver();
    })
    .catch((error) => {
      console.error(error);
      if (typeof notificarErrorModal === 'function') {
        notificarErrorModal('Error al cargar los datos del cliente');
      }
    });
};

/**
 * -----------------------------------------------------------------------------
 * 4. DELEGACIÓN DE EVENTOS (CLICKS EN LA TABLA)
 * -----------------------------------------------------------------------------
 */

/**
 * Agrego un event listener general al documento para atrapar los clicks
 * en los botones de editar o eliminar dentro de la tabla.
 */
document.addEventListener('click', (e) => {
  const botonEditar = e.target.closest('.boton-icono.editar');
  const botonEliminar = e.target.closest('.boton-icono.eliminar');

  if (botonEditar) {
    const id = botonEditar.dataset.id;
    prepararPanelEditarCliente(id);
  }

  if (botonEliminar) {
    const id = botonEliminar.dataset.id;
    const nombre = botonEliminar.dataset.nombre;

    // Relleno los datos en el modal de confirmación de eliminación
    document.getElementById('id_eliminar').value = id;
    document.getElementById('texto-confirmacion-eliminar').innerHTML = `¿Confirma que quiere eliminar al cliente <b>${nombre}</b>?`;

    // Abro el modal
    if (typeof abrirPanelEliminar === 'function') abrirPanelEliminar();
  }
});

// Autocapitalizar la primera letra al escribir en campos de nombre y apellido
const inputsNombres = document.querySelectorAll('input[name="nombre"], input[name="apellido"]');
inputsNombres.forEach(input => {
  input.addEventListener('input', (e) => {
    let valor = e.target.value;
    if (valor.length > 0) {
      e.target.value = valor.charAt(0).toUpperCase() + valor.slice(1);
    }
  });
});

// Hago accesibles las funciones globales que el HTML necesita usar mediante atributos onclick
window.prepararPanelNuevoCliente = prepararPanelNuevoCliente;